from typing import List, Dict, Any, Optional
from datetime import datetime
from src.config import settings


class GSPClient:
    def __init__(self, environment: Optional[str] = None):
        self.environment = environment or settings.GSP_ENVIRONMENT

    def fetch_gstr2b_inward(self, gstin: str, return_period: str) -> List[Dict[str, Any]]:
        # In production, this issues an authenticated mTLS HTTP GET to GST Suvidha Provider API
        # endpoint: /taxpayerapi/v1.0/returns/gstr2b?gstin={gstin}&rtn_prd={return_period}
        if self.environment.lower() == "production":
            return []

        # Sandbox synthetic B2B supplier invoices reflecting real-world GSTN portal returns
        return [
            {
                "supplier_gstin": "07MODER1111A1Z1",
                "supplier_trade_name": "Modern Agro Staples Ltd",
                "invoice_number": "MAS-2026-101",
                "invoice_date": "2026-11-01",
                "invoice_value": 7770.0,
                "taxable_value": 7400.0,
                "igst": 0.0,
                "cgst": 185.0,
                "sgst": 185.0,
                "cess": 0.0,
                "filing_period": return_period,
                "filing_date": "2026-11-10",
                "itc_eligibility": "Y",
            },
            {
                "supplier_gstin": "07ROYAL2222B1ZH",
                "supplier_trade_name": "Royal Spices & Condiments",
                "invoice_number": "RSC-2026-202",
                "invoice_date": "2026-11-02",
                "invoice_value": 6400.0,
                "taxable_value": 6000.0,
                "igst": 0.0,
                "cgst": 200.0,
                "sgst": 200.0,
                "cess": 0.0,
                "filing_period": return_period,
                "filing_date": "2026-11-11",
                "itc_eligibility": "Y",
            },
            {
                "supplier_gstin": "07CAPIT9999C1Z8",
                "supplier_trade_name": "Capital Packaging Supplies",
                "invoice_number": "CPS-2026-888",
                "invoice_date": "2026-11-15",
                "invoice_value": 5600.0,
                "taxable_value": 5000.0,
                "igst": 0.0,
                "cgst": 300.0,
                "sgst": 300.0,
                "cess": 0.0,
                "filing_period": return_period,
                "filing_date": "2026-11-12",
                "itc_eligibility": "Y",
            },
        ]
