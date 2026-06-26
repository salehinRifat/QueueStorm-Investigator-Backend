import json
from typing import Any

import httpx

from app.config import settings

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
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


def _convert_messages(messages: list[dict[str, str]]) -> tuple[str | None, list[dict]]:
    """Convert OpenAI-style messages to Gemini format.

    Returns (system_instruction, contents).
    """
    system_instruction = None
    contents = []

    for msg in messages:
        role = msg["role"]
        text = msg["content"]

        if role == "system":
            system_instruction = text
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})

    return system_instruction, contents


def call_llm(
    messages: list[dict[str, str]],
    json_schema: dict[str, Any],
) -> dict[str, Any]:
    if not settings.llm_api_key:
        raise LLMConfigError("LLM_API_KEY is not set")

    model = settings.llm_model or "gemini-2.0-flash"
    system_instruction, contents = _convert_messages(messages)

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "maxOutputTokens": 8192,
        },
    }

    if system_instruction:
        payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

    headers = {
        "x-goog-api-key": settings.llm_api_key,
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"

    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.post(url, json=payload, headers=headers)
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
            raw = body["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise LLMInvalidResponseError(f"Failed to parse response: {e}") from e

        _validate_response_json(parsed)
        return parsed

    raise last_error or LLMError("LLM call failed after retries")
