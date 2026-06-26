import json
from unittest.mock import patch, MagicMock

import httpx
import pytest

from app.config import settings
from app.llm.client import (
    call_llm,
    LLMConfigError,
    LLMTimeoutError,
    LLMInvalidResponseError,
    LLMAPIError,
    _convert_messages,
)

MINIMAL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "ticket_id": {"type": "string"},
        "evidence_verdict": {"type": "string"},
        "case_type": {"type": "string"},
        "severity": {"type": "string"},
        "department": {"type": "string"},
        "agent_summary": {"type": "string"},
        "recommended_next_action": {"type": "string"},
        "customer_reply": {"type": "string"},
        "human_review_required": {"type": "boolean"},
    },
    "required": [
        "ticket_id", "evidence_verdict", "case_type", "severity",
        "department", "agent_summary", "recommended_next_action",
        "customer_reply", "human_review_required",
    ],
}

MESSAGES = [
    {"role": "system", "content": "You are an assistant."},
    {"role": "user", "content": "Analyze this ticket."},
]

VALID_RESPONSE = {
    "ticket_id": "TKT-001",
    "evidence_verdict": "consistent",
    "case_type": "wrong_transfer",
    "severity": "high",
    "department": "dispute_resolution",
    "agent_summary": "Test.",
    "recommended_next_action": "Investigate.",
    "customer_reply": "We will check.",
    "human_review_required": False,
    "confidence": 0.9,
    "reason_codes": ["test"],
}

GEMINI_RESPONSE_BODY = {
    "candidates": [{
        "content": {
            "parts": [{"text": json.dumps(VALID_RESPONSE)}]
        }
    }]
}


def _mock_httpx(status: int = 200, content: str | None = None, invalid_json: bool = False):
    """Return a mock for httpx.Client.post."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status
    mock_response.text = content or json.dumps(GEMINI_RESPONSE_BODY)
    if invalid_json:
        mock_response.json.side_effect = json.JSONDecodeError("bad", doc="", pos=0)
    else:
        mock_response.json.return_value = json.loads(mock_response.text)
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    return patch("httpx.Client", return_value=mock_client)


def test_convert_messages_with_system():
    sys_inst, contents = _convert_messages(MESSAGES)
    assert sys_inst == "You are an assistant."
    assert len(contents) == 1
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Analyze this ticket."


def test_convert_messages_no_system():
    sys_inst, contents = _convert_messages([{"role": "user", "content": "hi"}])
    assert sys_inst is None
    assert len(contents) == 1


def test_successful_response():
    with _mock_httpx():
        result = call_llm(MESSAGES, MINIMAL_SCHEMA)
    assert result["ticket_id"] == "TKT-001"
    assert result["evidence_verdict"] == "consistent"


def test_missing_api_key():
    with patch.object(settings, "llm_api_key", ""):
        with pytest.raises(LLMConfigError, match="LLM_API_KEY"):
            call_llm(MESSAGES, MINIMAL_SCHEMA)


def test_timeout():
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = httpx.TimeoutException("timed out")
    with patch("httpx.Client", return_value=mock_client):
        with pytest.raises(LLMTimeoutError):
            call_llm(MESSAGES, MINIMAL_SCHEMA)


def test_invalid_json_from_api():
    with _mock_httpx(invalid_json=True):
        with pytest.raises(LLMInvalidResponseError):
            call_llm(MESSAGES, MINIMAL_SCHEMA)


def test_api_error_401():
    with _mock_httpx(status=401, content='{"error": "unauthorized"}'):
        with pytest.raises(LLMAPIError) as exc:
            call_llm(MESSAGES, MINIMAL_SCHEMA)
        assert exc.value.status_code == 401


def test_retry_on_500_then_success():
    mock_response_fail = MagicMock(spec=httpx.Response)
    mock_response_fail.status_code = 500
    mock_response_fail.text = "{}"
    mock_response_fail.json.return_value = {}

    mock_response_ok = MagicMock(spec=httpx.Response)
    mock_response_ok.status_code = 200
    mock_response_ok.text = json.dumps(GEMINI_RESPONSE_BODY)
    mock_response_ok.json.return_value = json.loads(mock_response_ok.text)

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = [mock_response_fail, mock_response_ok]

    with patch("httpx.Client", return_value=mock_client):
        result = call_llm(MESSAGES, MINIMAL_SCHEMA)
    assert result["ticket_id"] == "TKT-001"


def test_missing_required_fields():
    bad_response = {"ticket_id": "TKT-001"}
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps(bad_response)}]}}]}
    with _mock_httpx(content=json.dumps(body)):
        with pytest.raises(LLMInvalidResponseError, match="required fields"):
            call_llm(MESSAGES, MINIMAL_SCHEMA)


def test_request_payload_format():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = json.dumps(GEMINI_RESPONSE_BODY)
    mock_response.json.return_value = json.loads(mock_response.text)

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.__enter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("httpx.Client", return_value=mock_client):
        call_llm(MESSAGES, MINIMAL_SCHEMA)

        call_args = mock_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args.kwargs.get("url")
        assert url.startswith("https://generativelanguage.googleapis.com/v1beta/models/")
        assert url.endswith(":generateContent")
        headers = call_args.kwargs.get("headers", {})
        assert "x-goog-api-key" in headers
        assert headers["Content-Type"] == "application/json"
        payload = call_args.kwargs["json"]
    assert payload["contents"][0]["role"] == "user"
    assert payload["system_instruction"]["parts"][0]["text"] == "You are an assistant."
    assert payload["generationConfig"]["response_mime_type"] == "application/json"
