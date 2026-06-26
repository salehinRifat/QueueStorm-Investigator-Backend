import re

BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

AMOUNT_PATTERNS = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:taka|টাকা|BDT|bdt|৳)", re.IGNORECASE),
    re.compile(r"(?:taka|টাকা|BDT|bdt|৳)\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(?:amount|টাকা|bal[ae]nce)\s*(?:of\s*)?(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:taka|টাকা)", re.IGNORECASE),
]


def normalize_bangla_digits(text: str) -> str:
    result = text.translate(BANGLA_DIGITS)
    result = re.sub(r"[৳]", "", result)
    return result.strip()


def extract_amount(text: str) -> float | None:
    normalized = normalize_bangla_digits(text)
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(normalized)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue

    plain_numbers = re.findall(r"(?<!\d)(\d{3,})(?!\d)", normalized)
    if plain_numbers:
        return float(plain_numbers[0])

    return None


def fuzzy_amount_match(claimed: float, actual: float, tolerance: float = 0.02) -> bool:
    if actual <= 0:
        return False
    diff = abs(claimed - actual)
    return diff <= tolerance * max(actual, 1) or diff <= 5.0
