"""Excel export from the frozen manifest. Runs in the CPU subprocess pool.

Every untrusted value is written as a text cell, never a formula (values starting with =, +, -, @,
tab or CR stay literal text). Workbook properties are fixed so the same snapshot gives the same content.
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

FIXED_TIME = datetime(2026, 1, 1, 0, 0, 0)


def _text(ws: Any, row: int, col: int, value: Any) -> None:
    cell = ws.cell(row=row, column=col)
    cell.value = "" if value is None else str(value)
    cell.data_type = "s"


def _sheet(wb: Any, title: str, header: list[str], rows: list[list[Any]]) -> None:
    ws = wb.create_sheet(title)
    for col, name in enumerate(header, 1):
        _text(ws, 1, col, name)
    for r, row in enumerate(rows, 2):
        for c, value in enumerate(row, 1):
            _text(ws, r, c, value)


def build_workbook(manifest_json: str) -> bytes:
    from openpyxl import Workbook

    m = json.loads(manifest_json)
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Assure Flow"
    wb.properties.created = FIXED_TIME
    wb.properties.modified = FIXED_TIME
    status = "PARTIAL" if m["partial"] else "COMPLETE"
    summary = [
        ["Shop", f"{m['shop']['name']} ({m['shop']['gstin']})"],
        ["Period", m["period"]],
        ["Status", status],
        ["Rule profiles", ", ".join(m["rule_profiles"])],
        *[[f"Total {k}", v] for k, v in sorted(m["totals"].items())],
        *[[f"Count {k}", v] for k, v in sorted(m["counts"].items())],
        ["Note", m["itc_wording"]],
    ]
    _sheet(wb, "Summary", ["Item", "Value"], summary)
    inc = m["included"]
    _sheet(
        wb,
        "Included",
        [
            "Case",
            "Rev",
            "Supplier",
            "Supplier GSTIN",
            "Invoice no.",
            "Date",
            "POS",
            "Taxable",
            "CGST",
            "SGST",
            "IGST",
            "Cess",
            "Round-off",
            "Total",
            "Document SHA-256",
        ],
        [
            [
                e["case_ref"],
                e["revision"]["revision_no"],
                e["revision"]["supplier_name"],
                e["revision"]["supplier_gstin"],
                e["revision"]["invoice_number"],
                e["revision"]["invoice_date"],
                e["revision"]["place_of_supply"],
                e["revision"]["taxable_total"],
                e["revision"]["cgst_total"],
                e["revision"]["sgst_total"],
                e["revision"]["igst_total"],
                e["revision"]["cess_total"],
                e["revision"]["round_off"],
                e["revision"]["invoice_total"],
                e["evidence"]["document_sha256"],
            ]
            for e in inc
        ],
    )
    _sheet(
        wb,
        "Lines",
        [
            "Case",
            "Line",
            "Description",
            "HSN/SAC",
            "Qty",
            "Unit price",
            "Taxable",
            "CGST %",
            "SGST %",
            "IGST %",
            "CGST",
            "SGST",
            "IGST",
        ],
        [
            [
                e["case_ref"],
                li["line_no"],
                li["description"],
                li["hsn_sac"],
                li["qty"],
                li["unit_price"],
                li["taxable_value"],
                li["cgst_rate"],
                li["sgst_rate"],
                li["igst_rate"],
                li["cgst_amount"],
                li["sgst_amount"],
                li["igst_amount"],
            ]
            for e in inc
            for li in e["revision"]["lines"]
        ],
    )
    _sheet(
        wb,
        "Checks",
        ["Case", "Run", "Rule", "Version", "Outcome", "Severity", "Message", "Difference"],
        [
            [
                e["case_ref"],
                e["check_run"]["run_seq"],
                r["rule_id"],
                r["version"],
                r["outcome"],
                r["severity"],
                r["message"],
                r["difference"],
            ]
            for e in inc
            for r in e["check_run"]["results"]
        ],
    )
    _sheet(
        wb,
        "Decisions",
        ["Case", "Decision", "Action", "Reason", "Actor"],
        [[e["case_ref"], d["id"], d["action"], d["reason"], d["actor"]] for e in inc for d in e["decisions"]],
    )
    _sheet(wb, "Excluded", ["Case", "Reason"], [[x["case_ref"], x["reason"]] for x in m["excluded"]])
    _sheet(wb, "Held", ["Case", "Status", "Why"], [[x["case_ref"], x["status"], x["why"]] for x in m["held"]])
    _sheet(wb, "Unassigned", ["Case", "Status"], [[x["case_ref"], x["status"]] for x in m["unassigned"]])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()



def build_purchase_workbook(pack_json: str) -> bytes:
    """U2 purchase pack: Summary, Order, Delivery, Purchase checks and Assigned work sheets."""
    from openpyxl import Workbook

    p = json.loads(pack_json)
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "Assure Flow"
    wb.properties.created = FIXED_TIME
    wb.properties.modified = FIXED_TIME
    r = p["readiness"]
    _sheet(
        wb,
        "Summary",
        ["Item", "Value"],
        [
            ["Record", r["ref"]],
            ["Status", r["status"]],
            ["Amount", f"{r['amount']} {r['currency']}"],
            ["Due date", r["due_date"] or "unknown"],
            ["Due date source", r["due_source"]],
            ["Order", p["order"]["ref"]],
            ["Invoice case", p["invoice"]["case_ref"]],
            ["Reviewed by", r["reviewed_by"]],
            ["Authorized by", r["authorized_by"]],
            ["Content hash", r["content_hash"]],
            ["Note", p["wording"]],
        ],
    )
    _sheet(
        wb,
        "Order",
        ["Line", "Description", "Ordered", "Unit", "Unit price (excl. tax)"],
        [[x["line_id"], x["description"], x["ordered_qty"], x["unit"], x["unit_price"]] for x in p["order"]["lines"]],
    )
    _sheet(
        wb,
        "Delivery",
        ["Report", "Version", "Line", "Received", "Unit", "Confirmed by", "Confirmed at"],
        [
            [d["ref"], d["version"], x["line_id"], x["received_qty"], x["unit"], d["confirmed_by"], d["confirmed_at"]]
            for d in p["deliveries"]
            for x in d["lines"]
        ],
    )
    _sheet(
        wb,
        "Purchase checks",
        ["Line", "Description", "Ordered", "Received", "Billed", "Outstanding", "Unit"],
        [
            [x["line_id"], x["description"], x["ordered"], x["received"], x["billed"], x["outstanding"], x["unit"]]
            for x in p["match"]["lines"]
        ]
        + [["Finding", f["rule"], f["severity"], f["message"], "", "", ""] for f in p["match"]["findings"]],
    )
    _sheet(
        wb,
        "Assigned work",
        ["Task", "Assignee", "Due", "Status", "Reason", "History"],
        [
            [t["ref"], t["assignee"], t["due"], t["status"], t["reason"], " | ".join(t["history"])]
            for t in p["tasks"]
        ],
    )
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

def read_cells(xlsx: bytes) -> dict[str, list[list[Any]]]:
    """Cell values per sheet; used to prove re-exports are identical in content."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(xlsx))
    return {ws.title: [[c.value for c in row] for row in ws.iter_rows()] for ws in wb.worksheets}
