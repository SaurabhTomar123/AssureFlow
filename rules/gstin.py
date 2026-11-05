"""GSTIN structure and ISO/IEC 7064 Mod 36 check character. Reports "structure passed", never "registered"."""

from __future__ import annotations

import re

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MODULUS = len(ALPHABET)
PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
VALID_STATE_CODES = {f"{n:02d}" for n in range(1, 39)} | {"97", "99"}


def check_character(first14: str) -> str:
    total = 0
    factor = 1
    for char in first14.upper():
        code = ALPHABET.index(char)
        product = factor * code
        total += product // MODULUS + product % MODULUS
        factor = 2 if factor == 1 else 1
    return ALPHABET[(MODULUS - total % MODULUS) % MODULUS]


def make_gstin(state_code: str, pan: str, entity: str = "1") -> str:
    base = f"{state_code.zfill(2)}{pan.upper()}{entity}Z"
    return base + check_character(base)


def structure_problem(gstin: str | None) -> str | None:
    """None when the structure passes; otherwise a short reason."""
    if not gstin:
        return "missing"
    value = gstin.strip().upper()
    if len(value) != 15:
        return "length is not 15"
    if not PATTERN.match(value):
        return "format does not match the GSTIN pattern"
    if value[:2] not in VALID_STATE_CODES:
        return "unknown state code"
    if check_character(value[:14]) != value[14]:
        return "check character does not match"
    return None
