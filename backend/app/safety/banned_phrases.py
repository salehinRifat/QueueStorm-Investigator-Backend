import re

_BANGLA_CREDENTIAL = [
    "otp দিন", "ওটিপি দিন", "পিন দিন", "পাসওয়ার্ড দিন",
    "পিন নম্বর দিন", "পিন নাম্বার দিন",
    "আপনার পিন", "আপনার ওটিপি", "আপনার পাসওয়ার্ড",
]

_BANGLA_REFUND = [
    "আমরা ফেরত দেব", "টাকা ফেরত দেওয়া হবে", "টাকা ফেরত দিব",
    "টাকা ফেরত পাবেন", "আপনার টাকা ফেরত", "রিফান্ড দেওয়া হবে",
    "রিফান্ড দেব", "ফেরত দেয়া হবে",
]

_BANGLA_UNBLOCK = [
    "অ্যাকাউন্ট আনব্লক হবে", "আপনার একাউন্ট খুলে দেওয়া হবে",
    "অ্যাকাউন্ট খুলে দেওয়া হবে", "একাউন্ট আনব্লক",
]

_BANGLISH_CREDENTIAL = [
    "apnar otp din", "apnar pin din", "apnar password din",
    "your pin din", "your otp din",
]

_BANGLISH_REFUND = [
    "amra refund dibo", "taka ferot paben", "taka ferot dibo",
    "refund paben", "taka ferot deve",
]

_BANGLISH_MISC = [
    "etai official number", "ei number e call korun",
    "this is official number", "call this number",
    "contact this agent",
]

_EN_CREDENTIAL = [
    r"\bshare\s+(?:your\s+)?(?:otp|pin|password)\b",
    r"\b(?:otp|pin|password)\s*(?:number\s*)?\s*share\b",
    r"\benter\s+(?:your\s+)?(?:pin|otp|password)\b",
    r"\b(?:give|provide)\s+(?:us\s+)?(?:your\s+)?(?:pin|otp|password)\b",
]

_EN_REFUND = [
    r"\bwe\s+will\s+refund\b",
    r"\byour\s+(?:money|amount|funds|taka)\s+will\s+be\s+returned\b",
    r"\b(?:refund|reversal)\s+will\s+be\s+processed\b",
    r"\bwe\s+will\s+reverse\b",
    r"\b(?:your\s+)?(?:account\s+)?(?:will\s+be\s+)?(?:refunded|reversed)\b",
]

_EN_UNBLOCK = [
    r"\baccount\s+will\s+be\s+unblocked\b",
    r"\byour\s+account\s+will\s+be\s+reactivated\b",
    r"\baccount\s+(?:unblock|reactivate)\s+will\s+(?:be\s+)?done\b",
]

_EN_THIRD_PARTY = [
    r"\bcontact\s+(?:this|an?)\s+(?:number|agent|person)\b",
    r"\bcall\s+(?:this|an?)\s+(?:number|agent|person)\b",
    r"\breach\s+out\s+to\s+(?:this|an?)\s+(?:number|agent)\b",
]

_CREDENTIAL_SAFE = "We never ask for your PIN, OTP, or password. Please contact support through official channels."

_REFUND_SAFE = "Any eligible amount will be returned through official channels."

_GENERIC_SAFE = "If you have any concerns, please contact support through official channels."


def _build_patterns() -> list[tuple[re.Pattern, str]]:
    patterns: list[tuple[re.Pattern, str]] = []

    for raw in _EN_CREDENTIAL:
        patterns.append((re.compile(raw, re.IGNORECASE), _CREDENTIAL_SAFE))
    for raw in _EN_REFUND:
        patterns.append((re.compile(raw, re.IGNORECASE), _REFUND_SAFE))
    for raw in _EN_UNBLOCK:
        patterns.append((re.compile(raw, re.IGNORECASE), _GENERIC_SAFE))
    for raw in _EN_THIRD_PARTY:
        patterns.append((re.compile(raw, re.IGNORECASE), _GENERIC_SAFE))

    for raw in _BANGLA_CREDENTIAL:
        patterns.append((re.compile(re.escape(raw), re.IGNORECASE), _CREDENTIAL_SAFE))
    for raw in _BANGLA_REFUND:
        patterns.append((re.compile(re.escape(raw), re.IGNORECASE), _REFUND_SAFE))
    for raw in _BANGLA_UNBLOCK:
        patterns.append((re.compile(re.escape(raw), re.IGNORECASE), _GENERIC_SAFE))

    for raw in _BANGLISH_CREDENTIAL:
        patterns.append((re.compile(re.escape(raw), re.IGNORECASE), _CREDENTIAL_SAFE))
    for raw in _BANGLISH_REFUND:
        patterns.append((re.compile(re.escape(raw), re.IGNORECASE), _REFUND_SAFE))
    for raw in _BANGLISH_MISC:
        patterns.append((re.compile(re.escape(raw), re.IGNORECASE), _GENERIC_SAFE))

    return patterns


BANNED_PHRASES: list[tuple[re.Pattern, str]] = _build_patterns()
