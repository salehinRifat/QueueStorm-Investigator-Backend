import re
from app.models.response import TicketOut
from app.safety.banned_phrases import BANNED_PHRASES

_MAX_ITERATIONS = 5

_NEGATION_GUARD = re.compile(
    r"\b(?:do\s+not|don't|does\s+not|doesn't|never|should\s+not|shouldn't)\s+"
    r"(?:share|enter|give|provide)\b",
    re.IGNORECASE,
)


def scrub_reply(text: str) -> tuple[str, str, bool]:
    """Scan text for banned phrases and rewrite offending sentences.

    Protects negated credential phrases (e.g. "do not share your PIN")
    from being falsely flagged before applying banned-pattern regexes.

    Returns (original_text, cleaned_text, was_modified).
    """
    if not text:
        return text, text, False

    # Phase 1: protect negated credential phrases
    placeholders: dict[str, str] = {}

    def _protect(m: re.Match) -> str:
        key = f"\x00PROTECT_{len(placeholders)}\x00"
        placeholders[key] = m.group()
        return key

    protected = _NEGATION_GUARD.sub(_protect, text)

    # Phase 2: apply banned phrase patterns
    modified = False
    result = protected
    for pattern, replacement in BANNED_PHRASES:
        for _ in range(_MAX_ITERATIONS):
            new_text = pattern.sub(replacement, result, count=1)
            if new_text == result:
                break
            result = new_text
            modified = True

    # Phase 3: restore protected phrases
    for key, val in placeholders.items():
        result = result.replace(key, val)

    return text, result, modified


def check_safety(output: TicketOut) -> TicketOut:
    """Run safety scrub on customer_reply and recommended_next_action.

    Returns a new TicketOut with scrubbed fields and forced human_review if modified.
    """
    result = output.model_copy(deep=True)

    _, reply_scrubbed, reply_modified = scrub_reply(result.customer_reply)
    _, action_scrubbed, action_modified = scrub_reply(result.recommended_next_action)

    if reply_modified:
        result.customer_reply = reply_scrubbed

    if action_modified:
        result.recommended_next_action = action_scrubbed

    if reply_modified or action_modified:
        result.human_review_required = True
        if result.reason_codes is None:
            result.reason_codes = []
        if "safety_override" not in result.reason_codes:
            result.reason_codes.append("safety_override")

    return result
