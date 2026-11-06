import re
from typing import Optional

GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")

INDIAN_STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}


def validate_gstin_format(gstin: Optional[str]) -> tuple[bool, str]:
    if not gstin:
        return False, "GSTIN is missing"

    cleaned = gstin.strip().upper()
    if len(cleaned) != 15:
        return False, f"GSTIN length is {len(cleaned)}, expected 15 characters"

    if not GSTIN_REGEX.match(cleaned):
        return False, "GSTIN does not match official format standard"

    state_code = cleaned[:2]
    if state_code not in INDIAN_STATE_CODES:
        return False, f"State code '{state_code}' is not a recognized Indian state"

    return True, ""


def validate_tax_type(
    supplier_gstin: str,
    buyer_gstin: str,
    cgst: float,
    sgst: float,
    igst: float,
) -> tuple[bool, str]:
    supplier_state = supplier_gstin[:2].strip()
    buyer_state = buyer_gstin[:2].strip()

    is_intrastate = supplier_state == buyer_state

    if is_intrastate:
        if igst > 0.05:
            return False, (
                f"Intrastate transaction ({supplier_state} -> {buyer_state}) "
                f"cannot have IGST (charged {igst:.2f}). Must charge CGST and SGST."
            )
        if abs(cgst - sgst) > 0.50:
            return False, f"CGST ({cgst:.2f}) and SGST ({sgst:.2f}) must be equal for intrastate supply."
        if cgst <= 0.01 and sgst <= 0.01 and (cgst + sgst + igst) > 0:
            return False, "Intrastate transaction requires CGST and SGST."
    else:
        if cgst > 0.05 or sgst > 0.05:
            return False, (
                f"Interstate transaction ({supplier_state} -> {buyer_state}) "
                f"must charge IGST only. Found CGST: {cgst:.2f}, SGST: {sgst:.2f}."
            )
        if igst <= 0.01 and (cgst + sgst + igst) > 0:
            return False, "Interstate transaction requires IGST."

    return True, ""


def validate_math_totals(
    taxable_amount: float,
    cgst: float,
    sgst: float,
    igst: float,
    total_amount: float,
    items: Optional[list[dict]] = None,
) -> tuple[bool, str]:
    computed_total = taxable_amount + cgst + sgst + igst
    diff = abs(computed_total - total_amount)

    if diff > 1.50:
        return False, (
            f"Tax and taxable total mismatch: taxable ({taxable_amount:.2f}) + "
            f"taxes ({cgst + sgst + igst:.2f}) = {computed_total:.2f}, but invoice total is {total_amount:.2f}."
        )

    if items:
        sum_items_taxable = sum(item.get("taxable_value", 0.0) for item in items)
        if abs(sum_items_taxable - taxable_amount) > 1.50:
            return False, (
                f"Sum of item taxable values ({sum_items_taxable:.2f}) does not match "
                f"invoice taxable amount ({taxable_amount:.2f})."
            )

    return True, ""


def check_duplicate_bill(
    supplier_gstin: str,
    bill_number: str,
    existing_bills: list[dict],
    current_bill_id: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    norm_supplier = supplier_gstin.strip().upper()
    norm_bill_num = bill_number.strip().upper()

    for bill in existing_bills:
        if current_bill_id and bill.get("id") == current_bill_id:
            continue
        if (
            bill.get("supplier_gstin", "").strip().upper() == norm_supplier
            and bill.get("bill_number", "").strip().upper() == norm_bill_num
        ):
            return True, bill.get("id")

    return False, None

