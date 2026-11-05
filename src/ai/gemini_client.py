import os
import json
from pathlib import Path
from typing import Optional, Any
from src.config import settings

_CLIENT = None


def get_gemini_api_key() -> Optional[str]:
    key = getattr(settings, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY")
    if key and len(key.strip()) > 5:
        return key.strip()
    return None


def is_gemini_available() -> bool:
    return get_gemini_api_key() is not None


def get_gemini_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    api_key = get_gemini_api_key()
    if not api_key:
        return None

    try:
        from google import genai
        _CLIENT = genai.Client(api_key=api_key)
        return _CLIENT
    except Exception:
        return None


def generate_conversational_advice(
    prompt: str,
    system_instruction: Optional[str] = None,
    language: str = "en",
) -> Optional[str]:
    client = get_gemini_client()
    if not client:
        return None

    try:
        sys_inst = system_instruction or (
            "You are MunimJi, an expert Junior Chartered Accountant and store advisor for Indian small shop owners. "
            "Explain Indian tax rules (GST, Section 44AD, Section 32, Section 80C) simply, respectfully, and practically. "
            "Always state rupee amounts accurately. Do not use emojis."
        )
        if language == "hi":
            sys_inst += " Respond naturally in conversational Hindi/Hinglish as spoken by Indian accountants."

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"system_instruction": sys_inst, "temperature": 0.2},
        )
        return response.text.strip() if response and response.text else None
    except Exception:
        return None


def extract_bill_with_gemini_vision(file_path: str) -> Optional[dict[str, Any]]:
    client = get_gemini_client()
    if not client:
        return None

    path = Path(file_path)
    if not path.exists():
        return None

    try:
        from google.genai import types

        with open(path, "rb") as f:
            file_bytes = f.read()

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            mime_type = "application/pdf"
        elif suffix in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        else:
            mime_type = "image/png"

        extraction_prompt = (
            "Extract structured invoice data from this Indian tax invoice. "
            "Return strictly valid JSON with no markdown wrapping or preamble, matching this exact schema:\n"
            "{\n"
            '  "supplier_name": "Supplier Entity Name",\n'
            '  "supplier_gstin": "15-digit alphanumeric GSTIN or null",\n'
            '  "bill_number": "Invoice number string",\n'
            '  "bill_date": "YYYY-MM-DD",\n'
            '  "taxable_amount": 0.0,\n'
            '  "cgst_amount": 0.0,\n'
            '  "sgst_amount": 0.0,\n'
            '  "igst_amount": 0.0,\n'
            '  "total_amount": 0.0,\n'
            '  "items": [\n'
            '    {\n'
            '      "description": "Item Description",\n'
            '      "hsn": "HSN Code",\n'
            '      "qty": 1.0,\n'
            '      "rate": 0.0,\n'
            '      "tax_rate": 5.0,\n'
            '      "taxable_value": 0.0,\n'
            '      "total": 0.0\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                extraction_prompt,
            ],
            config={"temperature": 0.1},
        )

        if not response or not response.text:
            return None

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        parsed = json.loads(raw_text.strip())
        parsed["is_blurry"] = False
        return parsed
    except Exception:
        return None
