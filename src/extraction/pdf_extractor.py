from pathlib import Path
import pymupdf


def extract_text_from_pdf(pdf_path: str) -> str:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = pymupdf.open(str(path))
    full_text = []

    for page in doc:
        full_text.append(page.get_text())

    doc.close()
    return "\n".join(full_text)


def is_scanned_pdf(pdf_path: str) -> bool:
    text = extract_text_from_pdf(pdf_path)
    return len(text.strip()) < 30

