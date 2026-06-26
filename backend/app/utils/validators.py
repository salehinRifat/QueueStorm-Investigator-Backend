import re
from app.models.request import TicketIn
from app.utils.language import detect_language

EMBEDDED_INSTRUCTION = re.compile(
    r"\b(?:ignore|forget|disregard|override)\s+.*?(?:instructions?|rules?|prompt|system)",
    re.IGNORECASE,
)

PHISHING_INDICATOR = re.compile(
    r"\b(?:share|send|give|provide)\s+.*?(?:otp|pin|password)\b",
    re.IGNORECASE,
)

MIN_COMPLAINT_WORDS = 3


def validate_complaint(complaint: str) -> list[str]:
    """Validate complaint text. Returns a list of warning codes (empty = no warnings)."""
    warnings: list[str] = []

    if not complaint or not complaint.strip():
        return ["empty"]

    words = complaint.strip().split()
    if len(words) < MIN_COMPLAINT_WORDS:
        warnings.append("too_vague")

    if EMBEDDED_INSTRUCTION.search(complaint):
        warnings.append("embedded_instruction")

    if PHISHING_INDICATOR.search(complaint):
        warnings.append("phishing_indicator")

    return warnings


def validate_ticket(ticket: TicketIn) -> list[str]:
    """Validate the full ticket. Returns a list of warning codes."""
    warnings: list[str] = validate_complaint(ticket.complaint)

    if not ticket.transaction_history:
        warnings.append("no_history")

    if ticket.language is not None:
        detected = detect_language(ticket.complaint)
        if detected != ticket.language and ticket.language != "mixed" and detected != "mixed":
            warnings.append("language_mismatch")

    return warnings
