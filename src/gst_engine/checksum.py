ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MODULUS = len(ALPHABET)


def calculate_gstin_check_digit(gstin_14: str) -> str:
    cleaned = gstin_14.strip().upper()
    if len(cleaned) != 14:
        raise ValueError("Input must be exactly 14 characters long")

    total = 0
    factor = 1

    for char in cleaned:
        if char not in ALPHABET:
            raise ValueError(f"Invalid character '{char}' in GSTIN base")
        code_point = ALPHABET.index(char)
        product = factor * code_point
        digit = (product // MODULUS) + (product % MODULUS)
        total += digit
        factor = 2 if factor == 1 else 1

    remainder = total % MODULUS
    check_code_point = (MODULUS - remainder) % MODULUS
    return ALPHABET[check_code_point]


def validate_gstin_checksum(gstin: str) -> bool:
    cleaned = gstin.strip().upper()
    if len(cleaned) != 15:
        return False
    try:
        expected = calculate_gstin_check_digit(cleaned[:14])
        return cleaned[14] == expected
    except ValueError:
        return False


def generate_valid_gstin(state_code: str, pan: str, entity_num: str = "1") -> str:
    state_code = state_code.zfill(2)
    pan = pan.strip().upper()
    base = f"{state_code}{pan}{entity_num}Z"
    check_digit = calculate_gstin_check_digit(base)
    return f"{base}{check_digit}"
