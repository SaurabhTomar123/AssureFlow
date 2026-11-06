from datetime import date
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
    today = date.today()
    shift = get_daily_shift_summary(shop_id, today.isoformat(), db)
    payroll = calculate_monthly_payroll(shop_id, today.month, today.year, db)
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

    <!-- Analytics & Data Visualization Row -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-slate-950 p-6 rounded-xl border border-slate-800">
        <h2 class="font-bold text-lg text-white mb-4">Cash Outflow & Expense Allocation</h2>
        <div class="h-64 flex items-center justify-center">
          <canvas id="expenseChart"></canvas>
        </div>
      </div>
      <div class="bg-slate-950 p-6 rounded-xl border border-slate-800">
        <h2 class="font-bold text-lg text-white mb-4">GST Input Tax Credit Health</h2>
        <div class="h-64 flex items-center justify-center">
          <canvas id="itcChart"></canvas>
        </div>
      </div>
    </div>
  </main>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    const expCtx = document.getElementById('expenseChart');
    if (expCtx) {{
      new Chart(expCtx, {{
        type: 'doughnut',
        data: {{
          labels: ['Inventory Purchases', 'Operating Expenses', 'Capital Equipment'],
          datasets: [{{
            data: [
              {metrics.get('financial_summary', {}).get('total_purchases', 0.0) if 'financial_summary' in metrics else 0.0},
              {metrics.get('financial_summary', {}).get('total_operating_expenses', 0.0) if 'financial_summary' in metrics else 0.0},
              {metrics.get('financial_summary', {}).get('total_capital_investments', 0.0) if 'financial_summary' in metrics else 0.0}
            ],
            backgroundColor: ['#6366f1', '#10b981', '#f59e0b'],
            borderWidth: 0
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }}
          }}
        }}
      }});
    }}

    const itcCtx = document.getElementById('itcChart');
    if (itcCtx) {{
      new Chart(itcCtx, {{
        type: 'bar',
        data: {{
          labels: ['Eligible ITC', 'Disputed ITC at Risk'],
          datasets: [{{
            label: 'Amount in INR',
            data: [
              {metrics.get('gst_compliance', {}).get('eligible_itc', 0.0)},
              {metrics.get('gst_compliance', {}).get('itc_at_risk', 0.0)}
            ],
            backgroundColor: ['#10b981', '#f43f5e'],
            borderRadius: 6
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }}
          }},
          scales: {{
            x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ display: false }} }},
            y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#1e293b' }} }}
          }}
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return html


@router.get("/switch-simulator", response_class=HTMLResponse)
def get_switch_war_room_simulator():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>MunimJi — Switch Multi-Room Multi-Agent War Room Simulator</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #f1f5f9; padding: 16px; }
    header { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
    h1 { font-size: 20px; font-weight: 700; color: #38bdf8; }
    .tagline { font-size: 13px; color: #94a3b8; }
    .controls-panel { background: #131d31; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    .control-label { font-size: 13px; font-weight: 600; color: #cbd5e1; }
    button.sim-btn { background: #1e293b; border: 1px solid #334155; color: #f8fafc; padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
    button.sim-btn:hover { background: #2563eb; border-color: #3b82f6; }
    button.sim-btn.active { background: #2563eb; }
    .rooms-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
    .room-card { background: #111827; border: 1px solid #1f2937; border-radius: 8px; display: flex; flex-direction: column; height: 680px; overflow: hidden; }
    .room-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; }
    .room-title { font-size: 15px; font-weight: 600; }
    .room-badge { font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
    .room-sharma { border-top: 3px solid #3b82f6; }
    .room-sharma .room-title { color: #60a5fa; }
    .room-sharma .room-badge { background: #1e3a8a; color: #93c5fd; }
    .room-ca { border-top: 3px solid #a855f7; }
    .room-ca .room-title { color: #c084fc; }
    .room-ca .room-badge { background: #4c1d95; color: #d8b4fe; }
    .room-vendor { border-top: 3px solid #10b981; }
    .room-vendor .room-title { color: #34d399; }
    .room-vendor .room-badge { background: #064e3b; color: #6ee7b7; }
    .room-meta { font-size: 12px; color: #64748b; padding: 6px 16px; background: #0f172a; border-bottom: 1px solid #1e293b; }
    .messages-container { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
    .msg { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; font-size: 13px; line-height: 1.4; }
    .msg-header { display: flex; justify-content: space-between; margin-bottom: 6px; }
    .msg-sender { font-weight: 600; font-size: 12px; }
    .sender-user { color: #f59e0b; }
    .sender-bill-reader { color: #38bdf8; }
    .sender-store-manager { color: #34d399; }
    .sender-gst-checker { color: #f43f5e; }
    .sender-return-preparer { color: #c084fc; }
    .sender-vendor-concierge { color: #10b981; }
    .sender-vendor { color: #fbbf24; }
    .msg-time { font-size: 11px; color: #64748b; }
    .msg-content { white-space: pre-wrap; font-family: inherit; }
    .mention { color: #38bdf8; font-weight: 600; }
    .highlight-success { border-left: 3px solid #10b981; }
    .highlight-warning { border-left: 3px solid #f59e0b; }
    .highlight-danger { border-left: 3px solid #f43f5e; }
    .highlight-kacha { border-left: 3px solid #e11d48; background: #261219; }
    .room-footer { padding: 12px 16px; background: #0f172a; border-top: 1px solid #1e293b; display: flex; gap: 8px; }
    .room-input { flex: 1; background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px 12px; color: #fff; font-size: 13px; }
    .send-btn { background: #2563eb; border: none; color: white; padding: 8px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>MunimJi — Switch Multi-Room War-Room Simulator</h1>
      <div class="tagline">Autonomous Multi-Agent Collaboration across Isolated Boundary Channels</div>
    </div>
    <div style="font-size: 12px; color: #64748b;">Switch Architecture v2.0</div>
  </header>

  <div class="controls-panel">
    <span class="control-label">One-Click Demonstration Beats:</span>
    <button class="sim-btn" onclick="runBeatCleanBill()">1. Clean Kirana Bill & Restock</button>
    <button class="sim-btn" onclick="runBeatKachaSlip()">2. Kacha Counter Slip (Smart Sieve)</button>
    <button class="sim-btn" onclick="runBeatSeriousDefect()">3. Interstate Defect (CA Escalation)</button>
    <button class="sim-btn" onclick="runBeatVendorDispute()">4. Bot-to-Bot Vendor Dispute</button>
    <button class="sim-btn" onclick="runBeatVoiceNote()">5. Wispr Voice Note (Hinglish)</button>
    <button class="sim-btn" onclick="runBeatSmartInventory()">6. Smart Inventory (FEFO & RTV)</button>
    <button class="sim-btn" onclick="runBeatSmartAccounting()">7. Smart Accounting (P&L & Runway)</button>
    <button class="sim-btn" onclick="runBeatSmartHR()">8. Smart HR (Crew Punch & Payout)</button>
    <button class="sim-btn" onclick="resetSimulator()" style="margin-left:auto; background:#334155;">Reset</button>
  </div>

  <div class="rooms-grid">
    <!-- Room 1: Shop Sharma Kirana -->
    <div class="room-card room-sharma">
      <div class="room-header">
        <span class="room-title">shop-sharma-kirana</span>
        <span class="room-badge">PRIVATE ROOM</span>
      </div>
      <div class="room-meta">Participants: Shop Owner Sharma, @bill-reader, @store-manager, @junior-ca, @follow-up</div>
      <div class="messages-container" id="shop-messages">
        <div class="msg highlight-success">
          <div class="msg-header">
            <span class="msg-sender sender-bill-reader">@bill-reader</span>
            <span class="msg-time">09:00 AM</span>
          </div>
          <div class="msg-content">MunimJi Shop Intake online. Drop purchase bills, camera receipts, or voice notes.</div>
        </div>
      </div>
      <div class="room-footer">
        <input type="text" id="shop-input" class="room-input" placeholder="Message shop-sharma-kirana..." onkeydown="if(event.key==='Enter')sendShopMsg()">
        <button class="send-btn" onclick="sendShopMsg()">Send</button>
      </div>
    </div>

    <!-- Room 2: CA Office -->
    <div class="room-card room-ca">
      <div class="room-header">
        <span class="room-title">ca-office</span>
        <span class="room-badge">SHARED AUDIT</span>
      </div>
      <div class="room-meta">Participants: Chartered Accountant, @gst-checker, @return-preparer</div>
      <div class="messages-container" id="ca-messages">
        <div class="msg">
          <div class="msg-header">
            <span class="msg-sender sender-return-preparer">@return-preparer</span>
            <span class="msg-time">09:00 AM</span>
          </div>
          <div class="msg-content">CA Office Room active. Multi-client practice audit mode initialized.</div>
        </div>
      </div>
      <div class="room-footer">
        <input type="text" id="ca-input" class="room-input" placeholder="Execute CA commands (/approve, /reject, /ask_supplier)..." onkeydown="if(event.key==='Enter')sendCaMsg()">
        <button class="send-btn" onclick="sendCaMsg()">Send</button>
      </div>
    </div>

    <!-- Room 3: Vendor Dispute Desk -->
    <div class="room-card room-vendor">
      <div class="room-header">
        <span class="room-title">vendor-dispute-desk</span>
        <span class="room-badge">EXTERNAL BRIDGE</span>
      </div>
      <div class="room-meta">Participants: Supplier Billing Desk, @vendor-concierge (Tokenized Link)</div>
      <div class="messages-container" id="vendor-messages">
        <div class="msg">
          <div class="msg-header">
            <span class="msg-sender sender-vendor-concierge">@vendor-concierge</span>
            <span class="msg-time">09:00 AM</span>
          </div>
          <div class="msg-content">Vendor Dispute Concierge standing by for Rule 37A reconciliation dispatches.</div>
        </div>
      </div>
      <div class="room-footer">
        <input type="text" id="vendor-input" class="room-input" placeholder="Reply to dispute notice..." onkeydown="if(event.key==='Enter')sendVendorMsg()">
        <button class="send-btn" onclick="sendVendorMsg()">Send</button>
      </div>
    </div>
  </div>

  <script>
    function addMsg(roomId, senderClass, senderName, time, text, borderClass) {
      const container = document.getElementById(roomId);
      const div = document.createElement('div');
      div.className = 'msg ' + (borderClass || '');
      div.innerHTML = `
        <div class="msg-header">
          <span class="msg-sender ${senderClass}">${senderName}</span>
          <span class="msg-time">${time}</span>
        </div>
        <div class="msg-content">${text}</div>
      `;
      container.appendChild(div);
      container.scrollTop = container.scrollHeight;
    }

    function runBeatCleanBill() {
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '10:14 AM', '[Attached File: bill_01_clean_kirana_5pct.pdf]');
      setTimeout(() => {
        addMsg('shop-messages', 'sender-bill-reader', '@bill-reader', '10:14 AM',
          'Document Extracted: MAS-2026-101\\nSupplier: Modern Agro Staples Ltd (GSTIN: 07MODER1111A1Z1)\\nTaxable Value: INR 7,400.00 | CGST: INR 185.00 | SGST: INR 185.00\\nTotal: INR 7,770.00\\nReply OK to confirm details.', 'highlight-success');
      }, 500);
      setTimeout(() => {
        addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '10:15 AM', 'OK');
      }, 1200);
      setTimeout(() => {
        addMsg('shop-messages', 'sender-store-manager', '@store-manager', '10:15 AM',
          'Auto-Restock Complete: Inventory updated (+10 Aashirvaad Atta 10kg, +8 Fortune Rice 5kg).\\nMovements logged to stock ledger.', 'highlight-success');
      }, 1800);
    }

    function runBeatKachaSlip() {
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '10:20 AM', '[Attached File: kacha_counter_chit.pdf] "Ramu Mandi se 5 bori chana aaya bina bill ka"');
      setTimeout(() => {
        addMsg('shop-messages', 'sender-bill-reader', '@bill-reader', '10:20 AM',
          'KACHA SMART SIEVE ALERT:\\nClassified as INFORMAL ESTIMATE SLIP (No Supplier GSTIN).\\n- Quarantined from CA Tax Return Pool (Section 122 Audit Protection).\\n- Forwarded to @store-manager for internal inventory restock.\\n- Logged to /khata internal store expenses (INR 6,000.00).', 'highlight-kacha');
      }, 600);
      setTimeout(() => {
        addMsg('shop-messages', 'sender-store-manager', '@store-manager', '10:20 AM',
          'Internal Restock Complete: +5 Bori Desi Chana added to store catalog.\\nExcluded from GSTR-3B tax credit ledger.', 'highlight-success');
      }, 1300);
    }

    function runBeatSeriousDefect() {
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '10:30 AM', '[Attached File: bill_13_interstate_wrong_tax.pdf]');
      setTimeout(() => {
        addMsg('shop-messages', 'sender-bill-reader', '@bill-reader', '10:30 AM',
          'Extracted: INV-2026-013 (Gujarat Supplier to Delhi Shop).\\nTaxes: CGST INR 720.00 | SGST INR 720.00. Forwarding to deterministic auditor...', 'highlight-warning');
      }, 400);
      setTimeout(() => {
        addMsg('ca-messages', 'sender-gst-checker', '@gst-checker', '10:30 AM',
          'COMPLIANCE ESCALATION FROM [shop-sharma-kirana]:\\nBill #INV-2026-013 interstate supply charged CGST/SGST instead of IGST.\\nDisputed ITC: INR 1,440.00.\\nAction Required: /approve, /reject, or /ask_supplier.', 'highlight-danger');
      }, 900);
    }

    function runBeatVendorDispute() {
      addMsg('ca-messages', 'sender-user', 'Chartered Accountant', '10:35 AM', '/ask_supplier BILL-013');
      setTimeout(() => {
        addMsg('ca-messages', 'sender-return-preparer', '@return-preparer', '10:35 AM',
          'Generated Rule 37A Demand Notice. Dispatched tokenized dispute link to vendor billing desk.', 'highlight-warning');
      }, 500);
      setTimeout(() => {
        addMsg('vendor-messages', 'sender-vendor-concierge', '@vendor-concierge', '10:35 AM',
          'Incoming Dispute Ticket from Sharma Kirana:\\nBill #INV-2026-013 wrong tax classification. Disputed ITC: INR 1,440.00.\\nPlease select resolution: [1. Amend GSTR-1] [2. Issue Credit Note]', 'highlight-warning');
      }, 1000);
      setTimeout(() => {
        addMsg('vendor-messages', 'sender-vendor', 'Supplier Billing Team', '10:36 AM',
          'We acknowledge the error. Credit Note #CN-2026-9901 issued for INR 1,440.00 tax differential.');
      }, 1800);
      setTimeout(() => {
        addMsg('ca-messages', 'sender-return-preparer', '@return-preparer', '10:36 AM',
          'Dispute Resolved: Supplier issued Credit Note #CN-2026-9901. Tax credit pool adjusted.', 'highlight-success');
        addMsg('shop-messages', 'sender-follow-up', '@follow-up', '10:36 AM',
          'Vendor Dispute Notice Cleared: Modern Agro resolved tax differential via Credit Note #CN-2026-9901. Your ITC is safe.', 'highlight-success');
      }, 2500);
    }

    function runBeatVoiceNote() {
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '10:40 AM', '[Voice Note (Wispr Flow Transcribed)]: "Bhai 10 bori Aashirvaad Atta delivery aayi hai"');
      setTimeout(() => {
        addMsg('shop-messages', 'sender-store-manager', '@store-manager', '10:40 AM',
          'Voice Delivery Processed: Restocked 1 catalog item in inventory:\\n- Aashirvaad Atta: +10 units (New Total: 22.0 units).', 'highlight-success');
      }, 600);
    }

    function runBeatSmartInventory() {
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '11:00 AM', '/fefo_expiry_check');
      setTimeout(() => {
        addMsg('shop-messages', 'sender-store-manager', '@store-manager', '11:00 AM',
          'FEFO Horizon Audit:\\n- Batch BAT-EXP-001 (Amul Butter): Expired 5 days ago! Value at risk: INR 1,200.00.\\n- Generating Return-to-Vendor Debit Note #DN-RTV-20261105-EXP001 (Claim: INR 1,416.00 incl 18% GST reversal).\\n- Stock auto-deducted (-5 units). Supplier return notice dispatched.');
      }, 500);
      setTimeout(() => {
        addMsg('shop-messages', 'sender-store-manager', '@store-manager', '11:01 AM',
          'Dynamic Reorder Sheet (ADV Run-Rate):\\n- Tata Salt 1kg: ADV 2.0 units/day (4 days remaining). Optimal PO Draft: 22 units (INR 484.00) from preferred distributor.');
      }, 1200);
    }

    function runBeatSmartAccounting() {
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '11:15 AM', '/financials');
      setTimeout(() => {
        addMsg('shop-messages', 'sender-junior-ca', '@junior-ca', '11:15 AM',
          'Autonomous Double-Entry Financial Cockpit:\\n- Trial Balance: BALANCED (INR 121,000.00 Debits = INR 121,000.00 Credits)\\n- P&L: Revenue INR 25,000 | Opex INR 4,000 | Net Profit: INR 21,000.00\\n- Balance Sheet: Assets INR 121,000 = Liabilities INR 0 + Equity INR 121,000');
      }, 600);
      setTimeout(() => {
        addMsg('ca-messages', 'sender-return-preparer', '@return-preparer', '11:16 AM',
          'Treasury 30-Day Runway & Priority Queue:\\n- Working Capital: SAFE (Liquid reserves INR 125,000 vs Outflows INR 104,200)\\n- GST on the 20th: INR 14,200 | Projected Payroll: INR 45,000\\n- Payment Priority: Pay Reliable Distributor (INR 23,600) immediately (2B verified). HOLD Defaulting Wholesaler (INR 17,700) under Rule 37A.');
      }, 1400);
    }

    function runBeatSmartHR() {
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', '11:30 AM', '[Voice Checkin]: "Poori loading team present hai siwaye Mukesh ke, aur Chandan ko 1500 advance diya"');
      setTimeout(() => {
        addMsg('shop-messages', 'sender-store-manager', '@store-manager', '11:30 AM',
          'Smart Attendance & Advance Processed:\\n- 1-Click Crew Checkin: 2/3 floor workers PRESENT, Mukesh Driver marked ABSENT.\\n- Understaffing Alert: Morning shift needs 3 loaders, only 2 on duty!\\n- Udhari Advance: Logged INR 1,500.00 to Chandan Helper ledger.');
      }, 600);
      setTimeout(() => {
        addMsg('shop-messages', 'sender-store-manager', '@store-manager', '11:31 AM',
          'Bulk Payout Advice Batch #PAY-202611-SHAR generated:\\n- Chandan Helper: 10 days worked (INR 5,000) - Advance (INR 1,500) = Net Payable INR 3,500.00 (UPI: chandan@upi)\\n- Total Payroll Batch: INR 27,500.00 across 3 staff.\\n- Owner single-click approval required.');
      }, 1400);
      setTimeout(() => {
        addMsg('ca-messages', 'sender-return-preparer', '@return-preparer', '11:32 AM',
          'Dual-Authorization Sign-Off: Owner approved Payout Batch #PAY-202611-SHAR. Double-entry journal entry JE-20261105-PAYR recorded (Debit 5030 Wages INR 29,000, Credit 1020 Bank INR 27,500, Credit 2040 Advance INR 1,500).');
      }, 2200);
    }

    function resetSimulator() {
      document.getElementById('shop-messages').innerHTML = '';
      document.getElementById('ca-messages').innerHTML = '';
      document.getElementById('vendor-messages').innerHTML = '';
      addMsg('shop-messages', 'sender-bill-reader', '@bill-reader', '09:00 AM', 'MunimJi Shop Intake online. Drop purchase bills, camera receipts, or voice notes.', 'highlight-success');
      addMsg('ca-messages', 'sender-return-preparer', '@return-preparer', '09:00 AM', 'CA Office Room active. Multi-client practice audit mode initialized.');
      addMsg('vendor-messages', 'sender-vendor-concierge', '@vendor-concierge', '09:00 AM', 'Vendor Dispute Concierge standing by for Rule 37A reconciliation dispatches.');
    }

    function sendShopMsg() {
      const input = document.getElementById('shop-input');
      const val = input.value.trim();
      if (!val) return;
      addMsg('shop-messages', 'sender-user', 'Shop Owner Sharma', 'Now', val);
      input.value = '';
      setTimeout(() => {
        if (val.toLowerCase().includes('stock')) {
          addMsg('shop-messages', 'sender-store-manager', '@store-manager', 'Now', 'Catalog Health: 10 Total SKUs, 8 Healthy, 2 Depleted. Type /reorder for replenishment sheet.');
        } else if (val.toLowerCase().includes('khata')) {
          addMsg('shop-messages', 'sender-junior-ca', '@junior-ca', 'Now', 'Accounts Khata: Total Outflow INR 127,786.00 (Inventory INR 48,400 | Opex INR 54,400 | Assets INR 9,000).');
        } else {
          addMsg('shop-messages', 'sender-bill-reader', '@bill-reader', 'Now', 'Message received in shop-sharma-kirana: ' + val);
        }
      }, 500);
    }

    function sendCaMsg() {
      const input = document.getElementById('ca-input');
      const val = input.value.trim();
      if (!val) return;
      addMsg('ca-messages', 'sender-user', 'Chartered Accountant', 'Now', val);
      input.value = '';
      setTimeout(() => {
        addMsg('ca-messages', 'sender-return-preparer', '@return-preparer', 'Now', 'CA command executed: ' + val + '. Audit trail updated.');
      }, 500);
    }

    function sendVendorMsg() {
      const input = document.getElementById('vendor-input');
      const val = input.value.trim();
      if (!val) return;
      addMsg('vendor-messages', 'sender-vendor', 'Supplier Billing Desk', 'Now', val);
      input.value = '';
      setTimeout(() => {
        addMsg('vendor-messages', 'sender-vendor-concierge', '@vendor-concierge', 'Now', 'Vendor acknowledgment logged. Multi-room resolution dispatched.');
      }, 500);
    }
  </script>
</body>
</html>"""
    return html


