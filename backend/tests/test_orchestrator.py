from unittest.mock import patch, MagicMock

import pytest

from app.models.request import TicketIn, TransactionIn
from app.models.response import TicketOut
from app.service.orchestrator import investigate, _safe_fallback
from app.enums import EvidenceVerdict, CaseType, Severity, Department, Channel, Language
from app.llm.client import LLMError

BASE_TICKET = {
    "ticket_id": "TKT-001",
    "complaint": "I sent 5000 taka to 01712345678 but it didn't reach",
    "language": "en",
    "channel": "in_app_chat",
}

BASE_TXN = {
    "transaction_id": "TXN-001",
    "amount": 5000.0,
    "type": "transfer",
    "counterparty": "01712345678",
    "timestamp": "2026-06-25T14:30:00",
    "status": "completed",
}

BASE_OUT = TicketOut(
    ticket_id="TKT-001",
    relevant_transaction_id="TXN-001",
    evidence_verdict=EvidenceVerdict.consistent,
    case_type=CaseType.wrong_transfer,
    severity=Severity.high,
    department=Department.dispute_resolution,
    agent_summary="Sent 5000 to wrong number.",
    recommended_next_action="File a dispute.",
    customer_reply="We will investigate and get back to you.",
    human_review_required=False,
    confidence=0.85,
    reason_codes=["test"],
)


def _make_ticket(**kwargs) -> TicketIn:
    data = {**BASE_TICKET, **kwargs}
    txn = TransactionIn(**BASE_TXN)
    data.setdefault("transaction_history", [txn])
    return TicketIn(**data)


def test_happy_path():
    ticket = _make_ticket()
    with (
        patch("app.service.orchestrator.compute_shortlist", return_value=([], "none")),
        patch("app.service.orchestrator.build_prompt", return_value=[]),
        patch("app.service.orchestrator.build_json_schema", return_value={}),
        patch("app.service.orchestrator.call_llm", return_value=BASE_OUT.model_dump()),
        patch("app.service.orchestrator.post_process_llm_output", return_value=BASE_OUT),
        patch("app.service.orchestrator.check_safety", return_value=BASE_OUT),
    ):
        result = investigate(ticket)
    assert result.ticket_id == "TKT-001"
    assert result.evidence_verdict == EvidenceVerdict.consistent
    assert result.relevant_transaction_id == "TXN-001"


def test_llm_error_returns_safe_fallback():
    ticket = _make_ticket()
    with (
        patch("app.service.orchestrator.compute_shortlist", return_value=([], "none")),
        patch("app.service.orchestrator.build_prompt", return_value=[]),
        patch("app.service.orchestrator.build_json_schema", return_value={}),
            patch("app.service.orchestrator.call_llm", side_effect=LLMError("API down")),
        ):
            result = investigate(ticket)
    assert result.ticket_id == "TKT-001"
    assert result.evidence_verdict == EvidenceVerdict.insufficient_data
    assert result.human_review_required is True
    assert "llm_error" in (result.reason_codes or [])


def test_pre_scan_error_returns_safe_fallback():
    ticket = _make_ticket()
    with (
        patch("app.service.orchestrator.compute_shortlist", side_effect=ValueError("bad data")),
    ):
        result = investigate(ticket)
    assert result.ticket_id == "TKT-001"
    assert result.evidence_verdict == EvidenceVerdict.insufficient_data
    assert "pre_scan_error" in (result.reason_codes or [])


def test_post_process_error_does_not_crash():
    ticket = _make_ticket()
    with (
        patch("app.service.orchestrator.compute_shortlist", return_value=([], "none")),
        patch("app.service.orchestrator.build_prompt", return_value=[]),
        patch("app.service.orchestrator.build_json_schema", return_value={}),
        patch("app.service.orchestrator.call_llm", return_value=BASE_OUT.model_dump()),
        patch("app.service.orchestrator.post_process_llm_output", side_effect=Exception("boom")),
        patch("app.service.orchestrator.check_safety", return_value=BASE_OUT),
    ):
        result = investigate(ticket)
    assert result.ticket_id == "TKT-001"
    assert result.agent_summary == BASE_OUT.agent_summary


def test_safety_scrub_error_does_not_crash():
    ticket = _make_ticket()
    with (
        patch("app.service.orchestrator.compute_shortlist", return_value=([], "none")),
        patch("app.service.orchestrator.build_prompt", return_value=[]),
        patch("app.service.orchestrator.build_json_schema", return_value={}),
        patch("app.service.orchestrator.call_llm", return_value=BASE_OUT.model_dump()),
        patch("app.service.orchestrator.post_process_llm_output", return_value=BASE_OUT),
        patch("app.service.orchestrator.check_safety", side_effect=Exception("boom")),
    ):
        result = investigate(ticket)
    assert result.ticket_id == "TKT-001"
    assert result.agent_summary == BASE_OUT.agent_summary


def test_warning_codes_merged():
    ticket = _make_ticket(transaction_history=[])  # triggers "no_history" warning
    with (
        patch("app.service.orchestrator.compute_shortlist", return_value=([], "none")),
        patch("app.service.orchestrator.build_prompt", return_value=[]),
        patch("app.service.orchestrator.build_json_schema", return_value={}),
        patch("app.service.orchestrator.call_llm", return_value=BASE_OUT.model_dump()),
        patch("app.service.orchestrator.post_process_llm_output", return_value=BASE_OUT),
        patch("app.service.orchestrator.check_safety", return_value=BASE_OUT),
    ):
        result = investigate(ticket)
    assert "no_history" in (result.reason_codes or [])


def test_llm_error_with_warnings():
    ticket = _make_ticket(
        complaint="hi",  # too vague — triggers warning
        transaction_history=[],
    )
    with (
        patch("app.service.orchestrator.compute_shortlist", return_value=([], "none")),
        patch("app.service.orchestrator.build_prompt", return_value=[]),
        patch("app.service.orchestrator.build_json_schema", return_value={}),
            patch("app.service.orchestrator.call_llm", side_effect=LLMError("down")),
        ):
            result = investigate(ticket)
    codes = result.reason_codes or []
    assert "llm_error" in codes
    assert "too_vague" in codes
    assert "no_history" in codes


def test_safe_fallback_factory():
    result = _safe_fallback("TKT-X", "test_reason")
    assert result.ticket_id == "TKT-X"
    assert "test_reason" in (result.reason_codes or [])
    assert result.relevant_transaction_id is None
    assert result.evidence_verdict == EvidenceVerdict.insufficient_data
    assert result.human_review_required is True
