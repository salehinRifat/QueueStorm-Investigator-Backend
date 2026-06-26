import json
from typing import Any

import httpx

from app.config import settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
REQUEST_TIMEOUT = settings.request_timeout_seconds
MAX_RETRIES = 1


class LLMError(Exception):
    pass


class LLMConfigError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMInvalidResponseError(LLMError):
    pass


class LLMAPIError(LLMError):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"API error {status_code}: {body}")


_REQUIRED_OUTPUT_FIELDS = {
    "ticket_id", "evidence_verdict", "case_type", "severity",
    "department", "agent_summary", "recommended_next_action",
    "customer_reply", "human_review_required",
}


def _validate_response_json(data: dict[str, Any]) -> None:
    missing = _REQUIRED_OUTPUT_FIELDS - data.keys()
    if missing:
        raise LLMInvalidResponseError(
            f"Response missing required fields: {', '.join(sorted(missing))}"
        )


def call_llm(
    messages: list[dict[str, str]],
    json_schema: dict[str, Any],
) -> dict[str, Any]:
    if not settings.xai_api_key:
        raise LLMConfigError("XAI_API_KEY is not set")

    model = settings.llm_model or "llama-3.3-70b-versatile"

    payload = {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "ticket_analysis",
                "schema": json_schema,
            },
        },
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {settings.xai_api_key}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException:
            last_error = LLMTimeoutError("Request timed out")
            continue

        if response.status_code >= 500 and attempt < MAX_RETRIES:
            continue

        if response.status_code != 200:
            raise LLMAPIError(response.status_code, response.text[:500])

        try:
            body = response.json()
        except json.JSONDecodeError as e:
            raise LLMInvalidResponseError(f"Invalid JSON: {e}") from e

        try:
            raw = body["choices"][0]["message"]["content"]
            parsed = json.loads(raw)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise LLMInvalidResponseError(f"Failed to parse response: {e}") from e

        _validate_response_json(parsed)
        return parsed

    raise last_error or LLMError("LLM call failed after retries")
