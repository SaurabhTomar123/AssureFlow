from datetime import date
import re
from typing import Any
from src.db.session import SessionLocal
from src.db.models import Shop, Bill, ComplianceIssueModel, Employee
from src.agents.bill_reader import BillReaderAgent
from src.agents.gst_checker import GSTCheckerAgent
from src.agents.follow_up import FollowUpAgent
from src.agents.return_preparer import ReturnPreparerAgent
from src.agents.junior_ca import JuniorCAAgent
from src.agents.store_manager import StoreManagerAgent
from src.inventory.service import restock_inventory_from_bill
from src.staff.service import mark_attendance
from src.notifications.alert_engine import get_proactive_store_alerts


class SwitchWebhookRouter:
    def __init__(self):
        self.bill_reader = BillReaderAgent()
        self.gst_checker = GSTCheckerAgent()
        self.follow_up = FollowUpAgent()
        self.return_preparer = ReturnPreparerAgent()
        self.junior_ca = JuniorCAAgent()
        self.store_manager = StoreManagerAgent()

    def handle_message(
        self,
        room_name: str,
        user_name: str,
        text: str,
        attachment_path: str = None,
    ) -> list[dict[str, Any]]:
        responses = []
        db = SessionLocal()

        try:
            if room_name.startswith("shop-"):
                shop = db.query(Shop).filter(Shop.id == room_name).first()
                if not shop:
                    return [{"room": room_name, "text": f"Error: Shop {room_name} is not registered."}]

                if attachment_path:
                    lang = "hi" if any(w in text.lower() for w in ["namaste", "bhai", "karo", "yeh", "dekho"]) else "en"
                    read_res = self.bill_reader.process_document(attachment_path, language=lang)
                    responses.append({
                        "room": room_name,
                        "sender": "bill-reader",
                        "text": read_res["confirmation_message"],
                    })

                    check_res = self.gst_checker.check_compliance(
                        bill_data=read_res["extracted_data"],
                        buyer_gstin=shop.gstin,
                    )

                    if check_res["simple_issues"]:
                        for issue in check_res["simple_issues"]:
                            alert = self.follow_up.generate_owner_alert(
                                bill_data=read_res["extracted_data"],
                                issue_data=issue,
                                language=lang,
                            )
                            responses.append({
                                "room": room_name,
                                "sender": "follow-up",
                                "text": alert,
                            })

                    if check_res["serious_issues"]:
                        for issue in check_res["serious_issues"]:
                            ca_alert = self.return_preparer.format_ca_alert(
                                shop_name=shop.name,
                                bill_data=read_res["extracted_data"],
                                issue_data=issue,
                            )
                            responses.append({
                                "room": "ca-office",
                                "sender": "return-preparer",
                                "text": ca_alert["ca_message"],
                            })

                elif text.strip().upper() == "OK":
                    latest_bill = (
                        db.query(Bill)
                        .filter(Bill.shop_id == shop.id)
                        .order_by(Bill.created_at.desc())
                        .first()
                    )
                    if latest_bill:
                        latest_bill.is_confirmed_by_owner = True
                        db.commit()
                        responses.append({
                            "room": room_name,
                            "sender": "bill-reader",
                            "text": f"Invoice #{latest_bill.bill_number} confirmed and added to GST processing queue.",
                        })

                        restock_res = restock_inventory_from_bill(latest_bill.id, db)
                        if restock_res:
                            announcement = self.store_manager.format_auto_restock_announcement(
                                restocked_items=restock_res,
                                invoice_number=latest_bill.bill_number,
                                supplier_name=latest_bill.supplier_name,
                            )
                            responses.append({
                                "room": room_name,
                                "sender": "store-manager",
                                "text": announcement,
                            })

                elif text.strip().startswith("/status"):
                    bills = db.query(Bill).filter(Bill.shop_id == shop.id).all()
                    clean_c = sum(1 for b in bills if b.status == "clean")
                    flagged_c = sum(1 for b in bills if b.status == "flagged_issue")
                    responses.append({
                        "room": room_name,
                        "sender": "follow-up",
                        "text": f"Shop Status for {shop.name}:\nTotal Bills Sent: {len(bills)}\nClean: {clean_c}\nPending/Flagged: {flagged_c}",
                    })

                elif bool(re.search(r"\b(/khata|/accounts|khata|accounts)\b", text.strip().lower())):
                    lang = "hi" if any(w in text.lower() for w in ["dikhao", "batao", "mera", "kya"]) else "en"
                    khata_text = self.junior_ca.handle_khata_request(shop.id, db, language=lang)
                    responses.append({
                        "room": room_name,
                        "sender": "junior-ca",
                        "text": khata_text,
                    })

                elif bool(re.search(r"\b(/tax_savings|/savings|tax bachat|tax save)\b", text.strip().lower())):
                    lang = "hi" if any(w in text.lower() for w in ["kaise", "bachayein", "batao", "salah"]) else "en"
                    savings_text = self.junior_ca.handle_tax_savings_request(shop.id, db, language=lang)
                    responses.append({
                        "room": room_name,
                        "sender": "junior-ca",
                        "text": savings_text,
                    })

                elif text.strip().startswith("/presumptive"):
                    parts = text.strip().split()
                    turnover = float(parts[1]) if len(parts) > 1 else 5000000.0
                    digital_pct = float(parts[2]) if len(parts) > 2 else 80.0
                    presump_text = self.junior_ca.handle_presumptive_tax_request(
                        annual_turnover=turnover,
                        digital_pct=digital_pct,
                    )
                    responses.append({
                        "room": room_name,
                        "sender": "junior-ca",
                        "text": presump_text,
                    })

                elif text.strip().startswith("/stock"):
                    stock_text = self.store_manager.format_stock_overview(shop.id, db)
                    responses.append({
                        "room": room_name,
                        "sender": "store-manager",
                        "text": stock_text,
                    })

                elif text.strip().startswith("/reorder"):
                    reorder_text = self.store_manager.format_reorder_alert(shop.id, db)
                    responses.append({
                        "room": room_name,
                        "sender": "store-manager",
                        "text": reorder_text,
                    })

                elif text.strip().startswith("/attendance"):
                    today = date.today().isoformat()
                    att_text = self.store_manager.format_shift_summary(shop.id, today, db)
                    responses.append({
                        "room": room_name,
                        "sender": "store-manager",
                        "text": att_text,
                    })

                elif text.strip().startswith("/checkin"):
                    parts = text.strip().split()
                    today = date.today().isoformat()
                    staff_name = parts[1] if len(parts) > 1 else "Ramesh"
                    checkin_msg = self.store_manager.handle_checkin_command(
                        shop_id=shop.id,
                        staff_name=staff_name,
                        date_str=today,
                        db=db,
                    )
                    responses.append({
                        "room": room_name,
                        "sender": "store-manager",
                        "text": checkin_msg,
                    })

                elif text.strip().startswith("/payroll"):
                    parts = text.strip().split()
                    today = date.today()
                    year = today.year
                    month = today.month
                    if len(parts) > 1 and "-" in parts[1]:
                        y_str, m_str = parts[1].split("-")[:2]
                        try:
                            year = int(y_str)
                            month = int(m_str)
                        except ValueError:
                            pass
                    payroll_text = self.store_manager.format_payroll_report(shop.id, month, year, db)
                    responses.append({
                        "room": room_name,
                        "sender": "store-manager",
                        "text": payroll_text,
                    })

                elif text.strip().startswith("/shift_summary"):
                    today = date.today().isoformat()
                    shift_text = self.store_manager.format_shift_summary(shop.id, today, db)
                    responses.append({
                        "room": room_name,
                        "sender": "store-manager",
                        "text": shift_text,
                    })

                elif text.strip().startswith("/alerts"):
                    alert_data = get_proactive_store_alerts(shop.id, db)
                    lines = [
                        f"Proactive Store & Compliance Alerts for {shop.name}:",
                        "----------------------------------------",
                        f"Status: {alert_data['status']} | Active Alerts: {alert_data['total_active_alerts']}",
                        "",
                    ]
                    for g_alert in alert_data["gst_deadline_alerts"]:
                        lines.append(f"- [GST Deadline Alert]: {g_alert['message']}")
                    for s_alert in alert_data["inventory_alerts"][:4]:
                        lines.append(f"- [Low Stock Warning]: {s_alert['message']}")
                    if not alert_data["gst_deadline_alerts"] and not alert_data["inventory_alerts"]:
                        lines.append("No critical issues or inventory deficits found. Store running smoothly.")
                    lines.append("----------------------------------------")
                    responses.append({
                        "room": room_name,
                        "sender": "follow-up",
                        "text": "\n".join(lines),
                    })

                else:
                    low_text = text.strip().lower()
                    lang = "hi" if any(w in low_text for w in ["namaste", "bhai", "karo", "yeh", "dekho", "kya", "kaise", "dikhao", "batao", "aaj", "kitna"]) else "en"

                    if any(w in low_text for w in ["reorder", "procure", "khatam", "order"]):
                        reorder_text = self.store_manager.format_reorder_alert(shop.id, db, language=lang)
                        responses.append({
                            "room": room_name,
                            "sender": "store-manager",
                            "text": reorder_text,
                        })
                    elif any(w in low_text for w in ["stock", "maal", "inventory", "goods", "items", "catalog"]):
                        stock_text = self.store_manager.format_stock_overview(shop.id, db, language=lang)
                        responses.append({
                            "room": room_name,
                            "sender": "store-manager",
                            "text": stock_text,
                        })
                    elif any(w in low_text for w in ["khata", "accounts", "hisaab", "kharch", "outflow", "expense"]):
                        khata_text = self.junior_ca.handle_khata_request(shop.id, db, language=lang)
                        responses.append({
                            "room": room_name,
                            "sender": "junior-ca",
                            "text": khata_text,
                        })
                    elif any(w in low_text for w in ["tax", "bachat", "save", "savings", "depreciation", "80c"]):
                        tax_text = self.junior_ca.handle_tax_savings_request(shop.id, db, language=lang)
                        responses.append({
                            "room": room_name,
                            "sender": "junior-ca",
                            "text": tax_text,
                        })
                    elif any(w in low_text for w in ["attendance", "hazri", "present", "shift", "karmchari", "staff"]):
                        today_str = date.today().isoformat()
                        shift_text = self.store_manager.format_shift_summary(shop.id, today_str, db, language=lang)
                        responses.append({
                            "room": room_name,
                            "sender": "store-manager",
                            "text": shift_text,
                        })
                    elif any(w in low_text for w in ["payroll", "salary", "vetan", "tankhwah", "wages"]):
                        today_dt = date.today()
                        payroll_text = self.store_manager.format_payroll_report(shop.id, today_dt.month, today_dt.year, db, language=lang)
                        responses.append({
                            "room": room_name,
                            "sender": "store-manager",
                            "text": payroll_text,
                        })
                    else:
                        open_ans = self.junior_ca.answer_open_tax_query(text.strip(), language=lang)
                        responses.append({
                            "room": room_name,
                            "sender": "junior-ca",
                            "text": open_ans,
                        })

            elif room_name == "ca-office":
                cleaned_text = text.strip()

                if cleaned_text.startswith("/approve"):
                    parts = cleaned_text.split()
                    if len(parts) > 1:
                        bill_id = parts[1]
                        bill = db.query(Bill).filter(Bill.id == bill_id).first()
                        if bill:
                            bill.status = "ca_approved"
                            for iss in bill.issues:
                                iss.ca_action = "approved"
                            db.commit()
                            responses.append({
                                "room": "ca-office",
                                "sender": "return-preparer",
                                "text": f"Bill #{bill.bill_number} ({bill.supplier_name}) approved by CA. Retained for ITC.",
                            })

                elif cleaned_text.startswith("/reject"):
                    parts = cleaned_text.split()
                    if len(parts) > 1:
                        bill_id = parts[1]
                        bill = db.query(Bill).filter(Bill.id == bill_id).first()
                        if bill:
                            bill.status = "ca_rejected"
                            for iss in bill.issues:
                                iss.ca_action = "rejected"
                            db.commit()
                            responses.append({
                                "room": "ca-office",
                                "sender": "return-preparer",
                                "text": f"Bill #{bill.bill_number} rejected by CA. Disallowed from GSTR-3B.",
                            })

                elif cleaned_text.startswith("/ask_supplier"):
                    parts = cleaned_text.split()
                    if len(parts) > 1:
                        bill_id = parts[1]
                        bill = db.query(Bill).filter(Bill.id == bill_id).first()
                        if bill:
                            issue = bill.issues[0] if bill.issues else None
                            explanation = issue.explanation if issue else "Discrepancy"
                            draft = self.return_preparer.format_ca_alert(
                                shop_name=bill.shop.name if bill.shop else "Shop",
                                bill_data={"bill_number": bill.bill_number, "supplier_name": bill.supplier_name, "total_amount": bill.total_amount, "bill_date": bill.bill_date},
                                issue_data={"explanation": explanation, "rupee_value_at_risk": bill.cgst_amount + bill.sgst_amount + bill.igst_amount},
                            )["inquiry_draft"]
                            responses.append({
                                "room": "ca-office",
                                "sender": "return-preparer",
                                "text": f"Supplier Inquiry Notice Drafted for #{bill.bill_number}:\n\n{draft}",
                            })

                elif cleaned_text.startswith("/dashboard"):
                    shops = db.query(Shop).all()
                    lines = ["Monthly Multi-Shop CA Dashboard:"]
                    for s in shops:
                        bills = db.query(Bill).filter(Bill.shop_id == s.id).all()
                        clean_c = sum(1 for b in bills if b.status in ["clean", "ca_approved"])
                        flagged_c = sum(1 for b in bills if b.status == "flagged_issue")
                        lines.append(f"- {s.name} ({s.gstin}): {len(bills)} total bills | {clean_c} ready | {flagged_c} open flags")
                    responses.append({
                        "room": "ca-office",
                        "sender": "return-preparer",
                        "text": "\n".join(lines),
                    })

                elif cleaned_text.startswith("/summary"):
                    parts = cleaned_text.split()
                    shop_id = parts[1] if len(parts) > 1 else "shop-sharma-kirana"
                    shop = db.query(Shop).filter(Shop.id == shop_id).first()
                    if shop:
                        bills = db.query(Bill).filter(Bill.shop_id == shop.id).all()
                        clean_c = sum(1 for b in bills if b.status in ["clean", "ca_approved"])
                        issues = db.query(ComplianceIssueModel).filter(ComplianceIssueModel.shop_id == shop.id).all()
                        open_issues = [i for i in issues if i.ca_action == "pending"]
                        eligible = [b for b in bills if b.status in ["clean", "ca_approved"]]
                        cgst = sum(b.cgst_amount for b in eligible)
                        sgst = sum(b.sgst_amount for b in eligible)
                        igst = sum(b.igst_amount for b in eligible)
                        summary_text = self.return_preparer.format_month_end_summary({
                            "shop_name": shop.name,
                            "shop_gstin": shop.gstin,
                            "clean_bills": clean_c,
                            "open_issues_count": len(open_issues),
                            "itc_at_risk": sum(i.rupee_value_at_risk for i in open_issues),
                            "eligible_itc": {"cgst": cgst, "sgst": sgst, "igst": igst, "total": cgst + sgst + igst},
                        })
                        responses.append({
                            "room": "ca-office",
                            "sender": "return-preparer",
                            "text": summary_text,
                        })

            return responses
        finally:
            db.close()

