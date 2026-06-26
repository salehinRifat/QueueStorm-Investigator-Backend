import re
from app.models.response import TicketOut
from app.safety.banned_phrases import BANNED_PHRASES

_MAX_ITERATIONS = 5


def scrub_reply(text: str) -> tuple[str, bool]:
    """Scan text for banned phrases and rewrite offending sentences.

    Returns (cleaned_text, was_modified).
    """
    if not text:
        return text, False

    modified = False
    result = text

    for pattern, replacement in BANNED_PHRASES:
        for _ in range(_MAX_ITERATIONS):
            new_text = pattern.sub(replacement, result, count=1)
            if new_text == result:
                break
            result = new_text
            modified = True

    return result, modified


def check_safety(output: TicketOut) -> TicketOut:
    """Run safety scrub on customer_reply and recommended_next_action.

    Returns a new TicketOut with scrubbed fields and forced human_review if modified.
    """
    result = output.model_copy(deep=True)

    reply_scrubbed, reply_modified = scrub_reply(result.customer_reply)
    action_scrubbed, action_modified = scrub_reply(result.recommended_next_action)

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
