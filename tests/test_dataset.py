import json
from pathlib import Path
from src.gst_engine.validator import validate_bill_compliance

BASE_DIR = Path(__file__).resolve().parent.parent
GT_FILE = BASE_DIR / "synthetic_data" / "ground_truth.json"


def test_ground_truth_dataset_exists_and_valid():
    assert GT_FILE.exists()
    with open(GT_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    assert len(records) == 18

    for record in records:
        pdf_file = BASE_DIR / record["pdf_path"]
        img_file = BASE_DIR / record["img_path"]
        assert pdf_file.exists()
        assert img_file.exists()


def test_ground_truth_expected_issues():
    with open(GT_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    existing_history = []

    for record in records:
        is_blurry = "blurry" in record["filename"]
        bill_data = {
            "id": record["id"],
            "supplier_name": record["supplier_name"],
            "supplier_gstin": record["supplier_gstin"],
            "bill_number": record["invoice_number"],
            "bill_date": record["invoice_date"],
            "taxable_amount": record["taxable_amount"],
            "cgst_amount": record["cgst"],
            "sgst_amount": record["sgst"],
            "igst_amount": record["igst"],
            "total_amount": record["total_amount"],
            "items": record["items"],
            "is_blurry": is_blurry,
        }

        issues = validate_bill_compliance(
            bill_data=bill_data,
            buyer_gstin=record["buyer_gstin"],
            existing_bills=existing_history,
        )

        detected_issue_types = [i.issue_type for i in issues]

        if record["expected_status"] == "clean":
            assert len(detected_issue_types) == 0, f"Clean bill {record['id']} had issues: {detected_issue_types}"
        else:
            for expected_issue in record["expected_issues"]:
                assert expected_issue in detected_issue_types, (
                    f"Bill {record['id']} failed to flag expected issue {expected_issue}. "
                    f"Detected: {detected_issue_types}"
                )

        existing_history.append({
            "id": record["id"],
            "supplier_gstin": record["supplier_gstin"],
            "bill_number": record["invoice_number"],
        })
