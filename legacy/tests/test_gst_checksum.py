import pytest
from src.gst_engine.checksum import (
    calculate_gstin_check_digit,
    validate_gstin_checksum,
    generate_valid_gstin,
)


def test_calculate_gstin_check_digit_known_samples():
    base = "09AAAUP8175A1Z"
    digit = calculate_gstin_check_digit(base)
    assert len(digit) == 1
    assert digit in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    full = base + digit
    assert validate_gstin_checksum(full) is True


def test_validate_gstin_checksum_invalid():
    base = "07AAAAA0000A1Z"
    correct_digit = calculate_gstin_check_digit(base)

    wrong_digit = "0" if correct_digit != "0" else "1"
    corrupted_gstin = base + wrong_digit
    assert validate_gstin_checksum(corrupted_gstin) is False


def test_generate_valid_gstin():
    gstin = generate_valid_gstin(state_code="07", pan="ABCDE1234F", entity_num="1")
    assert len(gstin) == 15
    assert gstin.startswith("07ABCDE1234F1Z")
    assert validate_gstin_checksum(gstin) is True


def test_validate_gstin_checksum_invalid_lengths():
    assert validate_gstin_checksum("SHORT") is False
    assert validate_gstin_checksum("1234567890123456") is False

