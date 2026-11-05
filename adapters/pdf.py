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


def prepare_for_extraction(
    data: bytes,
    mime: str,
    page_from: int | None = None,
    page_to: int | None = None,
    dpi: int = 200,
    max_side: int = 2000,
) -> dict[str, Any]:
    """Per-page text-quality check (P1-06). Each page goes to the model as its text layer when the text is
    good, as an image when it is weak, and as both when a weak page still has some text (the model is told
    to prefer the image and lower confidence where they disagree). `page_from`/`page_to` (1-based,
    inclusive) restrict the document to one split invoice."""
    import pymupdf
    from PIL import Image

    pages: list[dict[str, Any]] = []
    if mime == "application/pdf":
        doc = pymupdf.open(stream=data, filetype="pdf")
        first = (page_from or 1) - 1
        last = (page_to or doc.page_count) - 1
        for index in range(first, last + 1):
            page = doc[index]
            text = page.get_text()
            entry: dict[str, Any] = {"page": index + 1, "text": None, "image": None}
            if _good_text(text):
                entry["text"] = text
            else:
                entry["image"] = _normalize(page.get_pixmap(dpi=dpi).tobytes("png"), max_side)
                if text.strip():
                    entry["text"] = text
            pages.append(entry)
    else:
        with Image.open(io.BytesIO(data)) as img:
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
        pages.append({"page": 1, "text": None, "image": _normalize(buf.getvalue(), max_side)})
    kinds = {
        ("text" if p["text"] and not p["image"] else "image" if not p["text"] else "both") for p in pages
    }
    mode = "text" if kinds == {"text"} else "vision" if kinds == {"image"} else "mixed"
    return {"mode": mode, "pages": pages, "page_from": page_from, "page_to": page_to}


def _good_text(text: str) -> bool:
    upper = text.upper()
    return len(text.strip()) >= MIN_TEXT_CHARS and any(anchor in upper for anchor in MATERIAL_ANCHORS)


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
