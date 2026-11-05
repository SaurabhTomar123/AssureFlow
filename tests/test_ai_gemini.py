from src.ai.gemini_client import (
    is_gemini_available,
    get_gemini_api_key,
    generate_conversational_advice,
    extract_bill_with_gemini_vision,
)


def test_gemini_client_fallback_when_unconfigured():
    # In test environment without GEMINI_API_KEY, fallback should be clean and not raise
    avail = is_gemini_available()
    assert isinstance(avail, bool)

    advice = generate_conversational_advice("What is Section 44AD?", language="en")
    # If no key, returns None gracefully
    if not avail:
        assert advice is None


def test_gemini_vision_fallback_on_missing_file():
    res = extract_bill_with_gemini_vision("non_existent_file.pdf")
    assert res is None

