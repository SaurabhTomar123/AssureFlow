from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from src.db.session import get_db
from src.db.models import Shop, Bill, ComplianceIssueModel
from src.accounts.ledger import get_accounts_book
from src.advisory.tax_advisor import calculate_asset_depreciation_section_32, generate_proprietor_tax_savings_plan
from src.inventory.service import get_inventory_catalog, get_low_stock_report
from src.staff.service import list_employees, get_daily_shift_summary, calculate_monthly_payroll
from src.users.rbac import filter_dashboard_data_for_role

router = APIRouter(tags=["Visual Dashboard"])


@router.get("/api/dashboard/metrics/{shop_id}")
def get_dashboard_metrics(
    shop_id: str,
    role: str = Query("OWNER", description="Active role profile: OWNER, MANAGER, STAFF, CA"),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    bills = db.query(Bill).filter(Bill.shop_id == shop_id).all()
    clean_bills = sum(1 for b in bills if b.status in ["clean", "ca_approved"])
    flagged_bills = sum(1 for b in bills if b.status == "flagged_issue")

    eligible_bills = [b for b in bills if b.status in ["clean", "ca_approved"]]
    eligible_itc = sum((b.cgst_amount or 0.0) + (b.sgst_amount or 0.0) + (b.igst_amount or 0.0) for b in eligible_bills)

    issues = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.shop_id == shop_id).all()
    open_issues = [i for i in issues if i.ca_action == "pending"]
    itc_at_risk = sum(i.rupee_value_at_risk for i in open_issues)

    accounts = get_accounts_book(shop_id, db)
    depreciation = calculate_asset_depreciation_section_32(shop_id, db)
    personal_tax = generate_proprietor_tax_savings_plan()

    catalog = get_inventory_catalog(shop_id, db)
    low_stock = get_low_stock_report(shop_id, db)

    employees = list_employees(shop_id, db)
    shift = get_daily_shift_summary(shop_id, "2026-11-05", db)
    payroll = calculate_monthly_payroll(shop_id, 11, 2026, db)
    total_payroll = sum(p["net_payable"] for p in payroll)

    raw_data = {
        "shop_id": shop.id,
        "shop_name": shop.name,
        "shop_gstin": shop.gstin,
        "active_role": role.upper(),
        "financial_summary": {
            "total_purchases": accounts["breakdown"]["inventory_purchases"],
            "total_operating_expenses": accounts["breakdown"]["operating_expenses"],
            "total_capital_investments": accounts["breakdown"]["capital_assets"],
            "total_cash_outflow": accounts["total_cash_outflow"],
        },
        "gst_compliance": {
            "total_bills": len(bills),
            "clean_bills": clean_bills,
            "flagged_bills": flagged_bills,
            "eligible_itc": round(eligible_itc, 2),
            "itc_at_risk": round(itc_at_risk, 2),
            "open_issues_count": len(open_issues),
        },
        "tax_savings_advice": {
            "section_32_depreciation_writeoff": depreciation["total_depreciation_claimable"],
            "section_32_tax_saved": depreciation["estimated_income_tax_saved"],
            "personal_tax_potential_saved": personal_tax["total_potential_annual_tax_saved"],
            "combined_tax_savings": round(depreciation["estimated_income_tax_saved"] + personal_tax["total_potential_annual_tax_saved"], 2),
        },
        "inventory_status": {
            "total_skus": len(catalog),
            "low_stock_count": len(low_stock),
            "catalog": catalog[:10],
            "low_stock_alerts": low_stock,
        },
        "staff_attendance": {
            "total_employees": len(employees),
            "present_today": shift["present_count"],
            "absent_today": shift["absent_count"],
            "present_names": shift["present_staff"],
            "absent_names": shift["absent_staff"],
            "monthly_payroll_outflow": round(total_payroll, 2),
        },
    }

    return filter_dashboard_data_for_role(role, raw_data)


@router.get("/dashboard", response_class=HTMLResponse)
def render_visual_dashboard(
    shop_id: str = "shop-sharma-kirana",
    role: str = "OWNER",
    db: Session = Depends(get_db),
):
    metrics = get_dashboard_metrics(shop_id=shop_id, role=role, db=db)

    role_upper = role.upper()
    shop_name = metrics["shop_name"]
    gstin = metrics["shop_gstin"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MunimJi — Enterprise Store Cockpit</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen">
  <!-- Top Navigation Bar -->
  <header class="border-b border-slate-800 bg-slate-950 px-6 py-4 flex flex-wrap justify-between items-center gap-4">
    <div class="flex items-center gap-3">
      <div class="h-10 w-10 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-xl">M</div>
      <div>
        <h1 class="text-xl font-bold tracking-tight text-white">MunimJi Retail & Compliance Cockpit</h1>
        <p class="text-xs text-slate-400">{shop_name} | GSTIN: <span class="font-mono text-indigo-400">{gstin}</span></p>
      </div>
    </div>

    <!-- Live Role Switcher -->
    <div class="flex items-center gap-2 bg-slate-900 p-1 rounded-xl border border-slate-800">
      <span class="text-xs text-slate-400 px-2 font-medium">Viewing as:</span>
      <a href="/dashboard?shop_id={shop_id}&role=OWNER" class="px-3 py-1.5 rounded-lg text-xs font-semibold {'bg-indigo-600 text-white' if role_upper == 'OWNER' else 'text-slate-400 hover:text-white'}">Owner</a>
      <a href="/dashboard?shop_id={shop_id}&role=MANAGER" class="px-3 py-1.5 rounded-lg text-xs font-semibold {'bg-emerald-600 text-white' if role_upper == 'MANAGER' else 'text-slate-400 hover:text-white'}">Store Manager</a>
      <a href="/dashboard?shop_id={shop_id}&role=STAFF" class="px-3 py-1.5 rounded-lg text-xs font-semibold {'bg-amber-600 text-white' if role_upper == 'STAFF' else 'text-slate-400 hover:text-white'}">Staff</a>
      <a href="/dashboard?shop_id={shop_id}&role=CA" class="px-3 py-1.5 rounded-lg text-xs font-semibold {'bg-blue-600 text-white' if role_upper == 'CA' else 'text-slate-400 hover:text-white'}">CA Office</a>
    </div>
  </header>

  <main class="max-w-7xl mx-auto p-6 space-y-6">
    <!-- Active Permissions Banner -->
    <div class="p-3 bg-slate-800/60 rounded-lg border border-slate-700/50 flex items-center justify-between text-xs">
      <div>
        <span class="text-slate-400">Current Role Profile:</span>
        <span class="font-bold text-white ml-1">{role_upper}</span>
        <span class="text-slate-400 ml-4">Authorized Modules:</span>
        <span class="text-indigo-400 ml-1">{', '.join(metrics.get('accessible_features', ['All Access']))}</span>
      </div>
      <div class="text-emerald-400 font-mono">Switch Multi-Room Active</div>
    </div>

    <!-- Top KPI Row -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-slate-950 p-5 rounded-xl border border-slate-800">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Eligible Input Tax Credit</p>
        <p class="text-2xl font-bold text-emerald-400 mt-2">INR {metrics.get('gst_compliance', {}).get('eligible_itc', 0.0):,.2f}</p>
        <p class="text-xs text-slate-500 mt-1">{metrics.get('gst_compliance', {}).get('clean_bills', 0)} Clean Invoices Filed</p>
      </div>

      <div class="bg-slate-950 p-5 rounded-xl border border-slate-800">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Disputed ITC at Risk</p>
        <p class="text-2xl font-bold text-rose-400 mt-2">INR {metrics.get('gst_compliance', {}).get('itc_at_risk', 0.0):,.2f}</p>
        <p class="text-xs text-slate-500 mt-1">{metrics.get('gst_compliance', {}).get('open_issues_count', 0)} Open Compliance Flags</p>
      </div>

      <div class="bg-slate-950 p-5 rounded-xl border border-slate-800">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Inventory Health</p>
        <p class="text-2xl font-bold text-indigo-400 mt-2">{metrics.get('inventory_status', {}).get('total_skus', 0)} SKUs</p>
        <p class="text-xs text-amber-400 mt-1">{metrics.get('inventory_status', {}).get('low_stock_count', 0)} Items Below Reorder Level</p>
      </div>

      <div class="bg-slate-950 p-5 rounded-xl border border-slate-800">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Staff On Duty Today</p>
        <p class="text-2xl font-bold text-cyan-400 mt-2">{metrics.get('staff_attendance', {}).get('present_today', 0)} / {metrics.get('staff_attendance', {}).get('total_employees', 0)}</p>
        <p class="text-xs text-slate-500 mt-1">Monthly Payroll: INR {metrics.get('staff_attendance', {}).get('monthly_payroll_outflow', 0.0):,.2f}</p>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Left Card: Inventory & Reorders -->
      <div class="bg-slate-950 p-6 rounded-xl border border-slate-800 space-y-4">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
          <h2 class="font-bold text-lg text-white">Store Inventory & Stock Levels</h2>
          <span class="text-xs bg-indigo-950 text-indigo-300 border border-indigo-800 px-2.5 py-1 rounded-md">Auto-Restocked via Invoices</span>
        </div>

        <div class="space-y-3">
          {''.join(f'''
          <div class="p-3 bg-slate-900 rounded-lg border border-slate-800 flex justify-between items-center">
            <div>
              <p class="text-sm font-semibold text-white">{it['name']}</p>
              <p class="text-xs text-slate-500 font-mono">{it['sku']} | Cost: INR {it['cost_price']:.2f}</p>
            </div>
            <div class="text-right">
              <span class="text-xs font-bold px-2 py-0.5 rounded {'bg-rose-950 text-rose-300 border border-rose-800' if it['status'] == 'LOW_STOCK' else 'bg-emerald-950 text-emerald-300 border border-emerald-800'}">{it['status']}</span>
              <p class="text-sm font-bold text-white mt-1">{it['current_stock']} {it['unit']}</p>
            </div>
          </div>
          ''' for it in metrics.get('inventory_status', {}).get('catalog', [])[:5])}
        </div>
      </div>

      <!-- Right Card: Staff Attendance & Shift Briefing -->
      <div class="bg-slate-950 p-6 rounded-xl border border-slate-800 space-y-4">
        <div class="flex justify-between items-center border-b border-slate-800 pb-3">
          <h2 class="font-bold text-lg text-white">Staff Roster & Attendance Board</h2>
          <span class="text-xs bg-emerald-950 text-emerald-300 border border-emerald-800 px-2.5 py-1 rounded-md">Daily Shift Active</span>
        </div>

        <div class="space-y-3">
          <div class="p-3 bg-slate-900 rounded-lg border border-slate-800">
            <p class="text-xs text-slate-400 font-semibold uppercase">Present on Duty:</p>
            <p class="text-sm font-medium text-emerald-400 mt-1">{', '.join(metrics.get('staff_attendance', {}).get('present_names', ['None'])) or 'All checked in'}</p>
          </div>

          <div class="p-3 bg-slate-900 rounded-lg border border-slate-800">
            <p class="text-xs text-slate-400 font-semibold uppercase">Absent / Leave:</p>
            <p class="text-sm font-medium text-rose-400 mt-1">{', '.join(metrics.get('staff_attendance', {}).get('absent_names', [])) or 'Zero absences recorded'}</p>
          </div>

          {''.join(f'''
          <div class="p-4 bg-indigo-950/40 rounded-lg border border-indigo-900/60 mt-4">
            <p class="text-xs text-indigo-300 font-semibold uppercase">Junior CA Tax Savings Card (Section 32 & 44AD)</p>
            <p class="text-xl font-bold text-white mt-1">Save ~INR {metrics.get("tax_savings_advice", {}).get("combined_tax_savings", 0.0):,.2f}</p>
            <p class="text-xs text-slate-400 mt-1">Section 32 Asset Depreciation: Write off INR {metrics.get("tax_savings_advice", {}).get("section_32_depreciation_writeoff", 0.0):,.2f} on shop electronics & equipment.</p>
          </div>
          ''' if 'tax_savings_advice' in metrics else '')}
        </div>
      </div>
    </div>
  </main>
</body>
</html>"""
    return html
