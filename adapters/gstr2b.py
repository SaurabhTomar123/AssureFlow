"""Versioned GSTR-2B parsers (P6-02). Runs inside workers.cpu_pool. Amounts are returned as strings exactly
as printed and parsed to Decimal by the caller. Only B2B invoices are read; credit/debit notes and other
sections are counted as skipped (credit-note profiles are P6-06 and need CA-approved examples).
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

JSON_V1 = "gstr2b_json_v1"
XLSX_V1 = "gstr2b_xlsx_v1"

XLSX_HEADERS = {
    "gstin of supplier": "supplier_gstin",
    "trade/legal name": "supplier_name",
    "invoice number": "invoice_number",
    "invoice type": "invoice_type",
    "invoice date": "invoice_date",
    "invoice value": "invoice_value",
    "taxable value": "taxable",
    "integrated tax": "igst",
    "central tax": "cgst",
    "state/ut tax": "sgst",
    "cess": "cess",
    "itc availability": "itc_available",
}


def _iso(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"unreadable date {text!r}")


def _num(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return "0"
    return str(value).replace(",", "").replace("₹", "").strip()


def _period_from_rtnprd(rtnprd: str) -> str:
    """Portal return period MMYYYY -> YYYY-MM."""
    return f"{rtnprd[2:]}-{rtnprd[:2]}"


def parse(data: bytes, filename: str) -> dict[str, Any]:
    if data.lstrip()[:1] in (b"{", b"["):
        return _parse_json(data)
    if data[:2] == b"PK":
        return _parse_xlsx(data, filename)
    return {"error": "not a GSTR-2B JSON or Excel file"}


def _parse_json(data: bytes) -> dict[str, Any]:
    try:
        doc = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"error": f"invalid JSON ({type(exc).__name__})"}
    body = doc.get("data", doc)
    gstin = str(body.get("gstin") or "").upper()
    rtnprd = str(body.get("rtnprd") or "")
    if len(rtnprd) != 6 or not gstin:
        return {"error": "missing gstin or rtnprd (return period)"}
    docdata = body.get("docdata") or {}
    lines: list[dict[str, Any]] = []
    try:
        for supplier in docdata.get("b2b") or []:
            for inv in supplier.get("inv") or []:
                items = inv.get("items") or [inv]
                totals = {
                    k: str(sum((Decimal(_num(i.get(k))) for i in items), Decimal(0)))
                    for k in ("txval", "igst", "cgst", "sgst", "cess")
                }
                lines.append(
                    {
                        "supplier_gstin": str(supplier.get("ctin") or "").upper(),
                        "supplier_name": supplier.get("trdnm"),
                        "invoice_number": str(inv.get("inum") or ""),
                        "invoice_type": inv.get("typ") or "R",
                        "invoice_date": _iso(inv.get("dt")),
                        "invoice_value": _num(inv.get("val")),
                        "taxable": totals["txval"],
                        "igst": totals["igst"],
                        "cgst": totals["cgst"],
                        "sgst": totals["sgst"],
                        "cess": totals["cess"],
                        "itc_available": inv.get("itcavl"),
                    }
                )
    except (ValueError, InvalidOperation) as exc:
        return {"error": f"unreadable value ({exc})"}
    skipped = {
        k: sum(len(s.get("nt") or s.get("inv") or []) for s in v)
        for k, v in docdata.items()
        if k != "b2b" and v
    }
    return {
        "parser": JSON_V1,
        "gstin": gstin,
        "period": _period_from_rtnprd(rtnprd),
        "lines": lines,
        "skipped": skipped,
    }


def _cell(row: tuple[Any, ...], columns: dict[str, int], field: str) -> Any:
    col = columns.get(field)
    return row[col] if col is not None and col < len(row) else None


def _parse_xlsx(data: bytes, filename: str) -> dict[str, Any]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any unreadable workbook is a rejection reason
        return {"error": f"unreadable Excel ({type(exc).__name__})"}
    meta: dict[str, str] = {}
    if "Read me" in wb.sheetnames:
        for row in wb["Read me"].iter_rows(values_only=True):
            label = str(row[0] or "").strip().lower() if row else ""
            if label.startswith("gstin") and len(row) > 1:
                meta["gstin"] = str(row[1] or "").strip().upper()
            if label.startswith("tax period") and len(row) > 1:
                meta["period"] = str(row[1] or "").strip()
    if "B2B" not in wb.sheetnames:
        return {"error": "no B2B sheet"}
    rows = list(wb["B2B"].iter_rows(values_only=True))
    columns: dict[str, int] = {}
    start = 0
    for idx, row in enumerate(rows[:8]):
        for col, cell in enumerate(row):
            label = str(cell or "").strip().lower().replace("(₹)", "").strip()
            for key, field in XLSX_HEADERS.items():
                if label.startswith(key) and field not in columns:
                    columns[field] = col
        if {"supplier_gstin", "invoice_number", "taxable"} <= set(columns):
            start = idx + 1
            break
    missing = {"supplier_gstin", "invoice_number", "invoice_date", "taxable"} - set(columns)
    if missing:
        return {"error": f"B2B sheet is missing columns: {', '.join(sorted(missing))}"}
    lines = []
    try:
        for row in rows[start:]:
            if not row or not row[columns["supplier_gstin"]]:
                continue
            lines.append(
                {
                    "supplier_gstin": str(_cell(row, columns, "supplier_gstin")).strip().upper(),
                    "supplier_name": _cell(row, columns, "supplier_name"),
                    "invoice_number": str(_cell(row, columns, "invoice_number")).strip(),
                    "invoice_type": _cell(row, columns, "invoice_type") or "Regular",
                    "invoice_date": _iso(_cell(row, columns, "invoice_date")),
                    "invoice_value": _num(_cell(row, columns, "invoice_value")),
                    "taxable": _num(_cell(row, columns, "taxable")),
                    "igst": _num(_cell(row, columns, "igst")),
                    "cgst": _num(_cell(row, columns, "cgst")),
                    "sgst": _num(_cell(row, columns, "sgst")),
                    "cess": _num(_cell(row, columns, "cess")),
                    "itc_available": _cell(row, columns, "itc_available"),
                }
            )
    except ValueError as exc:
        return {"error": str(exc)}
    if not meta.get("gstin") or not meta.get("period"):
        return {"error": "Read me sheet must state the GSTIN and tax period"}
    period = meta["period"]
    if len(period) == 6 and period.isdigit():
        period = _period_from_rtnprd(period)
    return {"parser": XLSX_V1, "gstin": meta["gstin"], "period": period, "lines": lines, "skipped": {}}
