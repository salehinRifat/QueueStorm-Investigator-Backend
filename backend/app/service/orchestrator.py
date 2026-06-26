import logging
from typing import Any

from app.enums import EvidenceVerdict, CaseType, Severity, Department
from app.llm.client import call_llm, LLMError
from app.models.request import TicketIn, TransactionIn
from app.models.response import TicketOut
from app.service.prompt_builder import build_prompt, build_json_schema
from app.service.rules import compute_shortlist, post_process_llm_output
from app.safety.scrubber import check_safety
from app.utils.validators import validate_ticket

logger = logging.getLogger(__name__)


def _safe_fallback(ticket_id: str, reason: str, error_detail: str = "") -> TicketOut:
    return TicketOut(
        ticket_id=ticket_id,
        relevant_transaction_id=None,
        evidence_verdict=EvidenceVerdict.insufficient_data,
        case_type=CaseType.other,
        severity=Severity.medium,
        department=Department.customer_support,
        agent_summary=f"Analysis failed: {reason}." + (f" {error_detail}" if error_detail else ""),
        recommended_next_action="Review the case manually through official channels.",
        customer_reply="We encountered an issue while reviewing your concern. Our team will follow up through official channels. Please do not share your PIN or OTP with anyone.",
        human_review_required=True,
        confidence=0.0,
        reason_codes=[reason],
    )


def investigate(ticket: TicketIn) -> TicketOut:
    warnings = validate_ticket(ticket)
    complaint = ticket.complaint
    history: list[TransactionIn] = ticket.transaction_history or []

    try:
        shortlist, flag = compute_shortlist(history, complaint)
    except Exception:
        logger.exception("Pre-scan failed")
        result = _safe_fallback(ticket.ticket_id, "pre_scan_error")
        _merge_warnings(result, warnings)
        return result

    try:
        messages = build_prompt(ticket, shortlist, flag)
        json_schema = build_json_schema()
        llm_response = call_llm(messages, json_schema)
    except LLMError:
        logger.exception("LLM call failed")
        result = _safe_fallback(ticket.ticket_id, "llm_error")
        _merge_warnings(result, warnings)
        return result

    candidate = TicketOut(**llm_response)

    try:
        corrected = post_process_llm_output(candidate, shortlist, flag, complaint, history)
    except Exception:
        logger.exception("Post-processing failed")
        corrected = candidate

    try:
        final = check_safety(corrected)
    except Exception:
        logger.exception("Safety scrub failed")
        final = corrected

    _merge_warnings(final, warnings)
    return final


def _merge_warnings(result: TicketOut, warnings: list[str]) -> None:
    if not warnings:
        return
    if result.reason_codes is None:
        result.reason_codes = []
    for w in warnings:
        if w not in result.reason_codes:
            result.reason_codes.append(w)
