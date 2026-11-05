"""Document inspection and rendering. Every function here runs inside workers.cpu_pool (subprocess).

Magic-byte signature check: extensions and client MIME types are never trusted.
"""

from __future__ import annotations

import io
from typing import Any

SIGNATURES = {
    b"%PDF-": "application/pdf",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}

MATERIAL_ANCHORS = ("GSTIN", "INVOICE", "TOTAL")
MIN_TEXT_CHARS = 200


def sniff_mime(data: bytes) -> str | None:
    for magic, mime in SIGNATURES.items():
        if data.startswith(magic):
            return mime
    return None


def inspect_document(data: bytes, mime: str) -> dict[str, Any]:
    """Page count and validity. Encrypted or corrupt files return an error string."""
    import pymupdf

    if mime == "application/pdf":
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except (RuntimeError, ValueError) as exc:
            return {"error": f"corrupt PDF ({type(exc).__name__})"}
        if doc.needs_pass or doc.is_encrypted:
            return {"error": "the PDF is password-protected"}
        return {"pages": doc.page_count}
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        return {"error": f"unreadable image ({type(exc).__name__})"}
    return {"pages": 1}


def prepare_for_extraction(data: bytes, mime: str, dpi: int = 200, max_side: int = 2000) -> dict[str, Any]:
    """Per-page text-quality check. If any page fails it, the whole document goes to vision
    (hackathon cut of P1-06): every page is rendered to PNG. Otherwise the text layer is used."""
    import pymupdf
    from PIL import Image

    pages_text: list[str] = []
    images: list[bytes] = []
    if mime == "application/pdf":
        doc = pymupdf.open(stream=data, filetype="pdf")
        for page in doc.pages():
            pages_text.append(page.get_text())
        needs_vision = any(not _good_text(t) for t in pages_text)
        if needs_vision:
            for page in doc.pages():
                pix = page.get_pixmap(dpi=dpi)
                images.append(_normalize(pix.tobytes("png"), max_side))
        return {"mode": "vision" if needs_vision else "text", "pages_text": pages_text, "images": images}
    with Image.open(io.BytesIO(data)) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
    return {"mode": "vision", "pages_text": [], "images": [_normalize(buf.getvalue(), max_side)]}


def _good_text(text: str) -> bool:
    upper = text.upper()
    return len(text.strip()) >= MIN_TEXT_CHARS and all(anchor in upper for anchor in MATERIAL_ANCHORS)


def _normalize(png: bytes, max_side: int) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(png)) as source:
        rgb = source.convert("RGB")
    rgb.thumbnail((max_side, max_side))
    out = io.BytesIO()
    rgb.save(out, format="PNG", optimize=True)
    return out.getvalue()


def burn_cpu(seconds: float) -> int:
    """A genuinely CPU-blocking task used by the lane/timeout tests (P1-20, R10)."""
    import time

    end = time.perf_counter() + seconds
    n = 0
    while time.perf_counter() < end:
        n += sum(i * i for i in range(1000))
    return n
