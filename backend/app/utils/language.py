import re
from app.enums import Language

# Bangla-specific characters rarely or never used in Assamese/other Brahmic scripts
_BANGLA_UNIQUE = re.compile(r"[ৎংঃঁৗড়ঢ়য়]")

BANGLA_UNICODE = re.compile(r"[\u0980-\u09FF]")
BANGLA_DIGITS = re.compile(r"[০১২৩৪৫৬৭৮৯]")

_BANGLA_FINGERPRINT = re.compile(
    r"\b(?:"
    r"আমার|আপনার|আমি|তুমি|আমরা|তারা|এটা|ওটা|সেটা|"
    r"টাকা|পাঠিয়েছি|দিয়েছি|নিয়েছি|করেছি|হয়েছে|"
    r"এই|একটি|কোনো|কিছু|আছে|থেকে|জন্য|বলে|"
    r"সমস্যা|অ্যাকাউন্ট|লেনদেন|গ্রাহক|সাহায্য"
    r")\b"
)

_ENGLISH_STOP_WORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "i", "you", "he", "she", "it", "we", "they",
    "my", "your", "his", "her", "its", "our", "their",
    "this", "that", "these", "those",
    "in", "on", "at", "to", "for", "with", "by", "from",
    "and", "or", "but", "if", "so", "because",
    "have", "has", "had", "do", "does", "did",
    "not", "no", "will", "would", "can", "could", "should",
    "yes", "please", "help", "need", "want", "got",
}

_BANGLISH_INDICATORS: set[str] = {
    "apnar", "amra", "din", "koren", "hobe", "hyache",
    "bolben", "diben", "paben", "jan", "kono", "ami", "tumi",
    "kichu", "jodi", "kintu", "karon", "thakle", "hoy",
    "kore", "dite", "nite", "niye", "diye", "theke",
    "dilo", "dise", "chilo", "hoyche", "deben", "niben",
    "rakben", "pathaben", "bhebe", "mone", "lomba", "shomoy",
    "ektu", "ektai", "etai", "tokhon", "ekhon",
    "dibo", "hoyni", "hote", "korte", "bole", "lage",
    "dorkar", "lomba", "shomossa", "kono",
}


def detect_language(text: str) -> Language:
    if not text or not text.strip():
        return Language.en

    cleaned = re.sub(r"\s", "", text)
    if not cleaned:
        return Language.en

    bangla_chars = len(BANGLA_UNICODE.findall(text))
    total_non_ws = len(cleaned)
    ratio = bangla_chars / total_non_ws

    if ratio == 0:
        return Language.en

    # Count fingerprint matches
    fingerprint_matches = len(_BANGLA_FINGERPRINT.findall(text))

    # Check for unique Bangla characters (strong signal)
    has_unique = bool(_BANGLA_UNIQUE.search(text))

    if has_unique:
        return Language.bn

    if fingerprint_matches >= 2:
        return Language.bn

    if fingerprint_matches == 1 and ratio > 0.30:
        return Language.bn

    if ratio > 0.7:
        return Language.bn

    if fingerprint_matches >= 1 or ratio > 0.10:
        return Language.mixed

    return Language.en


def contains_bangla(text: str) -> bool:
    return bool(BANGLA_UNICODE.search(text))


def is_banglish(text: str) -> bool:
    if not text:
        return False

    words = text.lower().split()
    if len(words) < 3:
        return False

    has_english = bool(re.search(r"[a-z]", text.lower()))
    if not has_english:
        return False

    stop_count = sum(1 for w in words if w.strip(".,!?;:") in _ENGLISH_STOP_WORDS)
    stop_ratio = stop_count / len(words)

    if stop_ratio >= 0.30:
        return False

    indicator_count = sum(1 for w in words if w.strip(".,!?;:") in _BANGLISH_INDICATORS)
    return indicator_count / len(words) > 0.15


def contains_bangla_digits(text: str) -> bool:
    return bool(BANGLA_DIGITS.search(text))
