from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from src.db.models import (
    JournalEntry,
    JournalEntryLine,
    Bill,
    Shop,
    Employee,
    GSTR2BInwardRecord,
    BankTransaction,
)

CHART_OF_ACCOUNTS: Dict[str, Dict[str, str]] = {
    "1010": {"name": "Cash in Hand", "type": "ASSET"},
    "1020": {"name": "Bank Current Account", "type": "ASSET"},
    "1030": {"name": "Accounts Receivable", "type": "ASSET"},
    "1040": {"name": "Merchandise Inventory", "type": "ASSET"},
    "1050": {"name": "Input Tax Credit CGST", "type": "ASSET"},
    "1051": {"name": "Input Tax Credit SGST", "type": "ASSET"},
    "1052": {"name": "Input Tax Credit IGST", "type": "ASSET"},
    "2010": {"name": "Accounts Payable", "type": "LIABILITY"},
    "2020": {"name": "Output Tax Payable CGST", "type": "LIABILITY"},
    "2021": {"name": "Output Tax Payable SGST", "type": "LIABILITY"},
    "2022": {"name": "Output Tax Payable IGST", "type": "LIABILITY"},
    "2030": {"name": "Salary & Wages Payable", "type": "LIABILITY"},
    "2040": {"name": "Staff Advances Deductions Payable", "type": "LIABILITY"},
    "2050": {"name": "Statutory Taxes & Dues Payable", "type": "LIABILITY"},
    "3010": {"name": "Owner Capital & Retained Earnings", "type": "EQUITY"},
    "4010": {"name": "Merchandise Sales Revenue", "type": "REVENUE"},
    "4020": {"name": "Discounts & Other Income", "type": "REVENUE"},
    "5010": {"name": "Cost of Goods Sold", "type": "EXPENSE"},
    "5020": {"name": "Store Rent & Utilities", "type": "EXPENSE"},
    "5030": {"name": "Staff Salaries & Wages", "type": "EXPENSE"},
    "5040": {"name": "Freight & Logistics", "type": "EXPENSE"},
    "5050": {"name": "Depreciation Expense", "type": "EXPENSE"},
    "5060": {"name": "Loss on Inventory Shrinkage", "type": "EXPENSE"},
    "5070": {"name": "General Operating Expenses", "type": "EXPENSE"},
}


def create_journal_entry(
    shop_id: str,
    entry_date: str,
    reference_type: str,
    description: str,
    lines_data: List[Dict[str, Any]],
    reference_id: Optional[str] = None,
    db: Session = None,
) -> JournalEntry:
    total_debit = round(sum(float(line.get("debit", 0.0)) for line in lines_data), 2)
    total_credit = round(sum(float(line.get("credit", 0.0)) for line in lines_data), 2)

    if abs(total_debit - total_credit) > 0.01:
        raise ValueError(
            f"Unbalanced journal entry: Total Debit ({total_debit}) != Total Credit ({total_credit})"
        )

    entry_number = f"JE-{datetime.utcnow().strftime('%Y%m%d')}-{reference_type[:4].upper()}-{reference_id[:6] if reference_id else 'GEN'}"

    entry = JournalEntry(
        shop_id=shop_id,
        entry_number=entry_number,
        entry_date=entry_date,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        total_debit=total_debit,
        total_credit=total_credit,
    )
    db.add(entry)
    db.flush()

    for line in lines_data:
        code = line["account_code"]
        name = CHART_OF_ACCOUNTS.get(code, {}).get("name", line.get("account_name", "General Account"))
        db_line = JournalEntryLine(
            entry_id=entry.id,
            account_code=code,
            account_name=name,
            debit=round(float(line.get("debit", 0.0)), 2),
            credit=round(float(line.get("credit", 0.0)), 2),
            notes=line.get("notes"),
        )
        db.add(db_line)

    db.commit()
    db.refresh(entry)
    return entry


def record_bill_journal_entry(bill_id: str, db: Session) -> Optional[JournalEntry]:
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        return None

    existing = (
        db.query(JournalEntry)
        .filter(JournalEntry.shop_id == bill.shop_id, JournalEntry.reference_type == "BILL", JournalEntry.reference_id == bill.id)
        .first()
    )
    if existing:
        return existing

    lines = []
    taxable = round(bill.taxable_amount or 0.0, 2)
    lines.append({
        "account_code": "1040",
        "debit": taxable,
        "credit": 0.0,
        "notes": f"Merchandise purchase ({bill.supplier_name})",
    })

    cgst = getattr(bill, "cgst_amount", 0.0) or getattr(bill, "cgst", 0.0) or 0.0
    sgst = getattr(bill, "sgst_amount", 0.0) or getattr(bill, "sgst", 0.0) or 0.0
    igst = getattr(bill, "igst_amount", 0.0) or getattr(bill, "igst", 0.0) or 0.0
    bill_date = getattr(bill, "bill_date", None) or date.today().isoformat()

    if cgst > 0:
        lines.append({
            "account_code": "1050",
            "debit": round(cgst, 2),
            "credit": 0.0,
            "notes": "Input CGST credit",
        })
    if sgst > 0:
        lines.append({
            "account_code": "1051",
            "debit": round(sgst, 2),
            "credit": 0.0,
            "notes": "Input SGST credit",
        })
    if igst > 0:
        lines.append({
            "account_code": "1052",
            "debit": round(igst, 2),
            "credit": 0.0,
            "notes": "Input IGST credit",
        })

    total_amount = round(bill.total_amount or (taxable + cgst + sgst + igst), 2)
    lines.append({
        "account_code": "2010",
        "debit": 0.0,
        "credit": total_amount,
        "notes": f"Accounts payable to {bill.supplier_name}",
    })

    return create_journal_entry(
        shop_id=bill.shop_id,
        entry_date=bill_date,
        reference_type="BILL",
        reference_id=bill.id,
        description=f"Purchase Invoice #{bill.bill_number} from {bill.supplier_name}",
        lines_data=lines,
        db=db,
    )


def record_bank_disbursement_journal_entry(
    shop_id: str,
    amount: float,
    payee_name: str,
    reference_id: Optional[str] = None,
    entry_date: Optional[str] = None,
    db: Session = None,
) -> JournalEntry:
    amt = round(amount, 2)
    lines = [
        {"account_code": "2010", "debit": amt, "credit": 0.0, "notes": f"Settlement to {payee_name}"},
        {"account_code": "1020", "debit": 0.0, "credit": amt, "notes": f"Bank outward debit to {payee_name}"},
    ]
    return create_journal_entry(
        shop_id=shop_id,
        entry_date=entry_date or date.today().isoformat(),
        reference_type="BANK_DISBURSEMENT",
        reference_id=reference_id,
        description=f"Vendor disbursement to {payee_name}",
        lines_data=lines,
        db=db,
    )


def record_shrinkage_journal_entry(
    shop_id: str,
    sku: str,
    item_name: str,
    loss_amount: float,
    db: Session,
) -> JournalEntry:
    loss = round(loss_amount, 2)
    lines = [
        {"account_code": "5060", "debit": loss, "credit": 0.0, "notes": f"Inventory shrinkage for {sku}"},
        {"account_code": "1040", "debit": 0.0, "credit": loss, "notes": f"Stock adjustment markdown ({sku})"},
    ]
    return create_journal_entry(
        shop_id=shop_id,
        entry_date=date.today().isoformat(),
        reference_type="SHRINKAGE",
        reference_id=sku,
        description=f"Inventory audit loss for {sku} ({item_name})",
        lines_data=lines,
        db=db,
    )


def get_trial_balance(shop_id: str, db: Session) -> Dict[str, Any]:
    lines = (
        db.query(JournalEntryLine)
        .join(JournalEntry, JournalEntryLine.entry_id == JournalEntry.id)
        .filter(JournalEntry.shop_id == shop_id)
        .all()
    )

    balances: Dict[str, Dict[str, Any]] = {}
    for code, meta in CHART_OF_ACCOUNTS.items():
        balances[code] = {
            "account_code": code,
            "account_name": meta["name"],
            "account_type": meta["type"],
            "total_debit": 0.0,
            "total_credit": 0.0,
            "net_debit": 0.0,
            "net_credit": 0.0,
        }

    for ln in lines:
        if ln.account_code not in balances:
            balances[ln.account_code] = {
                "account_code": ln.account_code,
                "account_name": ln.account_name,
                "account_type": CHART_OF_ACCOUNTS.get(ln.account_code, {}).get("type", "EXPENSE"),
                "total_debit": 0.0,
                "total_credit": 0.0,
                "net_debit": 0.0,
                "net_credit": 0.0,
            }
        balances[ln.account_code]["total_debit"] += ln.debit
        balances[ln.account_code]["total_credit"] += ln.credit

    total_debits = 0.0
    total_credits = 0.0
    active_accounts = []

    for code, b in sorted(balances.items()):
        if b["total_debit"] > 0 or b["total_credit"] > 0:
            diff = b["total_debit"] - b["total_credit"]
            if diff >= 0:
                b["net_debit"] = round(diff, 2)
                b["net_credit"] = 0.0
                total_debits += diff
            else:
                b["net_debit"] = 0.0
                b["net_credit"] = round(abs(diff), 2)
                total_credits += abs(diff)
            active_accounts.append(b)

    total_debits = round(total_debits, 2)
    total_credits = round(total_credits, 2)
    is_balanced = abs(total_debits - total_credits) < 0.02

    return {
        "shop_id": shop_id,
        "as_of_date": date.today().isoformat(),
        "total_debits": total_debits,
        "total_credits": total_credits,
        "is_balanced": is_balanced,
        "active_account_count": len(active_accounts),
        "accounts": active_accounts,
    }


def get_profit_and_loss(shop_id: str, db: Session) -> Dict[str, Any]:
    lines = (
        db.query(JournalEntryLine)
        .join(JournalEntry, JournalEntryLine.entry_id == JournalEntry.id)
        .filter(JournalEntry.shop_id == shop_id)
        .all()
    )

    revenues = 0.0
    expenses = 0.0
    expense_breakdown = {}
    revenue_breakdown = {}

    for ln in lines:
        acc_type = CHART_OF_ACCOUNTS.get(ln.account_code, {}).get("type", "EXPENSE")
        acc_name = CHART_OF_ACCOUNTS.get(ln.account_code, {}).get("name", ln.account_name)

        if acc_type == "REVENUE":
            amt = ln.credit - ln.debit
            revenues += amt
            revenue_breakdown[acc_name] = revenue_breakdown.get(acc_name, 0.0) + amt
        elif acc_type == "EXPENSE":
            amt = ln.debit - ln.credit
            expenses += amt
            expense_breakdown[acc_name] = expense_breakdown.get(acc_name, 0.0) + amt

    net_profit = round(revenues - expenses, 2)

    return {
        "shop_id": shop_id,
        "period": f"{date.today().strftime('%B %Y')}",
        "total_revenue": round(revenues, 2),
        "total_expenses": round(expenses, 2),
        "net_profit": net_profit,
        "is_profitable": net_profit >= 0,
        "revenue_breakdown": {k: round(v, 2) for k, v in revenue_breakdown.items()},
        "expense_breakdown": {k: round(v, 2) for k, v in expense_breakdown.items()},
    }


def get_balance_sheet(shop_id: str, db: Session) -> Dict[str, Any]:
    tb = get_trial_balance(shop_id, db)
    pnl = get_profit_and_loss(shop_id, db)

    assets = []
    liabilities = []
    equity = []

    total_assets = 0.0
    total_liabilities = 0.0
    total_equity = 0.0

    for acc in tb["accounts"]:
        acc_type = acc["account_type"]
        val = acc["net_debit"] if acc["net_debit"] > 0 else -acc["net_credit"]

        if acc_type == "ASSET":
            total_assets += acc["net_debit"]
            assets.append({"code": acc["account_code"], "name": acc["account_name"], "amount": acc["net_debit"]})
        elif acc_type == "LIABILITY":
            total_liabilities += acc["net_credit"]
            liabilities.append({"code": acc["account_code"], "name": acc["account_name"], "amount": acc["net_credit"]})
        elif acc_type == "EQUITY":
            total_equity += acc["net_credit"]
            equity.append({"code": acc["account_code"], "name": acc["account_name"], "amount": acc["net_credit"]})

    retained_profit = pnl["net_profit"]
    total_equity_with_profit = round(total_equity + retained_profit, 2)
    equity.append({"code": "3999", "name": "Current Period Retained Earnings", "amount": retained_profit})

    return {
        "shop_id": shop_id,
        "as_of_date": date.today().isoformat(),
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "total_equity": total_equity_with_profit,
        "total_liabilities_and_equity": round(total_liabilities + total_equity_with_profit, 2),
        "is_balanced": abs(total_assets - (total_liabilities + total_equity_with_profit)) < 1.0,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
    }


def get_cash_flow_forecast(shop_id: str, db: Session) -> Dict[str, Any]:
    bank_txs = db.query(BankTransaction).filter(BankTransaction.shop_id == shop_id).all()
    if bank_txs:
        credits = sum(t.amount for t in bank_txs if t.transaction_type == "CREDIT")
        debits = sum(t.amount for t in bank_txs if t.transaction_type == "DEBIT")
        liquid_cash = max(credits - debits, 50000.0)
    else:
        liquid_cash = 125000.0

    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    unpaid_bills = [b for b in bills if b.status != "REJECTED"]
    total_ap_due = round(sum(b.total_amount for b in unpaid_bills[:6]), 2) if unpaid_bills else 35000.0

    employees = db.query(Employee).filter(Employee.shop_id == shop_id, Employee.is_active == True).all()
    projected_payroll = round(sum(e.base_rate for e in employees), 2) if employees else 45000.0

    total_cgst = sum(getattr(b, "cgst_amount", 0.0) or getattr(b, "cgst", 0.0) or 0.0 for b in unpaid_bills)
    total_sgst = sum(getattr(b, "sgst_amount", 0.0) or getattr(b, "sgst", 0.0) or 0.0 for b in unpaid_bills)
    eligible_itc = total_cgst + total_sgst
    projected_output_tax = round(eligible_itc * 1.35, 2)
    estimated_net_gst_payable = round(max(0.0, projected_output_tax - eligible_itc), 2)

    fixed_overheads = 20000.0

    total_projected_outflows_30d = round(total_ap_due + projected_payroll + estimated_net_gst_payable + fixed_overheads, 2)

    daily_sales_estimate = 4500.0
    projected_inflows_30d = round(daily_sales_estimate * 30, 2)

    net_cash_burn = total_projected_outflows_30d - projected_inflows_30d
    if net_cash_burn > 0:
        runway_days = round(liquid_cash / (net_cash_burn / 30.0), 1)
    else:
        runway_days = 999.0

    if liquid_cash < (estimated_net_gst_payable + projected_payroll):
        safety_index = "CRITICAL_DEFICIT"
        advice = f"Cash shortage warning: Liquid balance (Rs {liquid_cash}) cannot cover statutory GST on the 20th (Rs {estimated_net_gst_payable}) and payroll (Rs {projected_payroll}). Hold non-critical AP."
    elif liquid_cash < total_projected_outflows_30d:
        safety_index = "TIGHT"
        advice = f"Working capital is tight. Ensure retail collections of Rs {round(total_projected_outflows_30d - liquid_cash, 2)} are deposited before the 20th."
    else:
        safety_index = "SAFE"
        advice = f"Healthy working capital position. Projected liquid reserves remain positive across all scheduled 30-day obligations."

    return {
        "shop_id": shop_id,
        "as_of_date": date.today().isoformat(),
        "liquid_cash_balance": round(liquid_cash, 2),
        "total_projected_outflows_30d": total_projected_outflows_30d,
        "projected_inflows_30d": projected_inflows_30d,
        "outflow_breakdown": {
            "accounts_payable_due": total_ap_due,
            "projected_payroll": projected_payroll,
            "estimated_net_gst_payable": estimated_net_gst_payable,
            "fixed_overheads": fixed_overheads,
        },
        "net_cash_runway_days": runway_days,
        "safety_index": safety_index,
        "treasury_advisory": advice,
    }


def get_vendor_payment_priority_queue(shop_id: str, db: Session) -> List[Dict[str, Any]]:
    bills = db.query(Bill).filter(Bill.shop_id == shop_id, Bill.status != "REJECTED").all()
    queue = []

    for b in bills:
        gsp_record = (
            db.query(GSTR2BInwardRecord)
            .filter(GSTR2BInwardRecord.shop_id == shop_id, GSTR2BInwardRecord.invoice_number == b.bill_number)
            .first()
        )

        match_status = gsp_record.match_status if gsp_record else "NOT_FOUND_IN_GSTR2B"
        itc_status = gsp_record.itc_eligibility if gsp_record else "UNCONFIRMED"

        score = 50.0

        if match_status == "MATCHED":
            score += 40.0
            action = "PAY_IMMEDIATELY"
            reason = "Verified in GSTR-2B portal; claiming safe legal ITC."
        elif match_status == "UNRECORDED":
            score += 20.0
            action = "SCHEDULE_PAYMENT"
            reason = "Portal record exists; verify receipt before settlement."
        else:
            score -= 30.0
            action = "HOLD_PAYMENT_DEFAULT"
            reason = "Supplier missing in GSTR-2B! Withhold payment until vendor files GSTR-1 under Rule 37A."

        queue.append({
            "bill_id": b.id,
            "bill_number": b.bill_number,
            "supplier_name": b.supplier_name,
            "supplier_gstin": b.supplier_gstin,
            "invoice_date": getattr(b, "bill_date", None) or date.today().isoformat(),
            "total_amount": b.total_amount,
            "claimable_tax": round((getattr(b, "cgst_amount", 0.0) or 0.0) + (getattr(b, "sgst_amount", 0.0) or 0.0) + (getattr(b, "igst_amount", 0.0) or 0.0), 2),
            "portal_status": match_status,
            "itc_eligibility": itc_status,
            "priority_score": score,
            "recommended_action": action,
            "reason": reason,
        })

    queue.sort(key=lambda x: x["priority_score"], reverse=True)
    return queue
