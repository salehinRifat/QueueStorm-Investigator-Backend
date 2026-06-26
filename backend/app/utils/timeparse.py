import re
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser

BANGLA_TIME_WORDS = {
    "সকাল": (9, 0),
    "সকালে": (9, 0),
    "দুপুর": (13, 0),
    "দুপুরে": (13, 0),
    "বিকাল": (16, 0),
    "বিকেলে": (16, 0),
    "সন্ধ্যা": (19, 0),
    "সন্ধ্যায়": (19, 0),
    "রাত": (22, 0),
    "রাতে": (22, 0),
}

BANGLA_RELATIVE = {
    "আজ": 0,
    "আজকে": 0,
    "গতকাল": -1,
    "গতকাল": -1,
    "গত": -1,
    "পরশু": -2,
    "কালকে": 1,
}

ENGLISH_TIME_PATTERNS = [
    re.compile(r"(?:around|at|about)?\s*(\d{1,2})\s*(?::(\d{2}))?\s*(pm|am|PM|AM|PM|AM)", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*(pm|am|PM|AM)", re.IGNORECASE),
]


def _today_at(hour: int, minute: int = 0) -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_bangla_time(text: str) -> datetime | None:
    for word, offset_days in BANGLA_RELATIVE.items():
        if word in text:
            day = datetime.now(timezone.utc) + timedelta(days=offset_days)
            for bangla_word, (h, m) in BANGLA_TIME_WORDS.items():
                if bangla_word in text:
                    return day.replace(hour=h, minute=m, second=0, microsecond=0)
            return day.replace(hour=12, minute=0, second=0, microsecond=0)
    for bangla_word, (h, m) in BANGLA_TIME_WORDS.items():
        if bangla_word in text:
            return _today_at(h, m)
    return None


def extract_time(text: str) -> datetime | None:
    bangla_result = parse_bangla_time(text)
    if bangla_result:
        return bangla_result

    normalized = text.lower()

    for pattern in ENGLISH_TIME_PATTERNS:
        match = pattern.search(normalized)
        if match:
            groups = match.groups()
            hour = int(groups[0])
            minute = int(groups[1]) if groups[1] else 0
            ampm = groups[2].lower() if len(groups) > 2 and groups[2] else None
            if ampm:
                if ampm == "pm" and hour < 12:
                    hour += 12
                if ampm == "am" and hour == 12:
                    hour = 0
            return _today_at(hour, minute)

    today_ref = re.search(r"\btoday\b", normalized)
    yesterday_ref = re.search(r"\byesterday\b", normalized)
    if yesterday_ref:
        day = datetime.now(timezone.utc) - timedelta(days=1)
        return parse_time_of_day(normalized, day)

    if today_ref:
        return parse_time_of_day(normalized, datetime.now(timezone.utc))

    try:
        parsed = dateparser.parse(text, fuzzy=True, default=datetime.now(timezone.utc))
        if parsed:
            return parsed
    except (dateparser.ParserError, ValueError):
        pass

    return None


def parse_time_of_day(text: str, base_day: datetime) -> datetime:
    if re.search(r"\bmorning\b", text):
        return base_day.replace(hour=9, minute=0, second=0, microsecond=0)
    if re.search(r"\bafternoon\b", text):
        return base_day.replace(hour=14, minute=0, second=0, microsecond=0)
    if re.search(r"\bevening\b", text):
        return base_day.replace(hour=18, minute=0, second=0, microsecond=0)
    return base_day.replace(hour=12, minute=0, second=0, microsecond=0)


def time_decay_weight(hours_diff: float, half_life: float = 6.0) -> float:
    import math
    return math.exp(-abs(hours_diff) * math.log(2) / half_life)
