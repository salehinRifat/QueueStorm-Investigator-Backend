from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.enums import EvidenceVerdict, CaseType, Severity, Department
from app.main import app
from app.models.response import TicketOut

client = TestClient(app)

VALID_TICKET = {
    "ticket_id": "TKT-001",
    "complaint": "I sent 5000 taka to 01712345678 but it didn't reach",
    "language": "en",
    "channel": "in_app_chat",
    "transaction_history": [
        {
            "transaction_id": "TXN-001",
            "amount": 5000.0,
            "type": "transfer",
            "counterparty": "01712345678",
            "timestamp": "2026-06-25T14:30:00",
            "status": "completed",
        }
    ],
}

FAKE_OUT = TicketOut(
    ticket_id="TKT-001",
    relevant_transaction_id="TXN-001",
    evidence_verdict=EvidenceVerdict.consistent,
    case_type=CaseType.wrong_transfer,
    severity=Severity.high,
    department=Department.dispute_resolution,
    agent_summary="Test summary.",
    recommended_next_action="File a dispute.",
    customer_reply="We will investigate.",
    human_review_required=False,
    confidence=0.85,
    reason_codes=["test"],
)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("app.router.investigate", return_value=FAKE_OUT)
def test_analyze_ticket_success(mock_investigate):
    response = client.post("/analyze-ticket", json=VALID_TICKET)
    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"] == "TKT-001"
    assert data["evidence_verdict"] == "consistent"
    assert data["relevant_transaction_id"] == "TXN-001"
    assert data["confidence"] == 0.85


@patch("app.router.investigate", side_effect=Exception("unexpected"))
def test_analyze_ticket_unhandled_error(mock_investigate):
    response = client.post("/analyze-ticket", json=VALID_TICKET)
    assert response.status_code == 200
    data = response.json()
    assert data["ticket_id"] == "TKT-001"
    assert data["evidence_verdict"] == "insufficient_data"
    assert data["human_review_required"] is True
    assert "system_error" in data.get("reason_codes", [])


def test_analyze_ticket_missing_complaint():
    payload = {k: v for k, v in VALID_TICKET.items() if k != "complaint"}
    response = client.post("/analyze-ticket", json=payload)
    assert response.status_code == 422


def test_analyze_ticket_invalid_channel():
    payload = {**VALID_TICKET, "channel": "invalid_channel"}
    response = client.post("/analyze-ticket", json=payload)
    assert response.status_code == 422
