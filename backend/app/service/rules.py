import re
from copy import deepcopy
from datetime import datetime, timezone
from rapidfuzz import fuzz
from app.enums import EvidenceVerdict, CaseType, Severity, Department
from app.models.request import TransactionIn
from app.models.response import TicketOut
from app.utils.amounts import extract_amount, fuzzy_amount_match
from app.utils.timeparse import extract_time, time_decay_weight

TYPE_KEYWORDS: dict[str, list[str]] = {
    "transfer": ["sent", "transfer", "send", "transferred", "পাঠিয়েছি", "send করেছি", "transfer করেছি"],
    "payment": ["pay", "paid", "payment", "bill", "recharge", "পেমেন্ট", "পে", "পরিশোধ"],
    "cash_in": ["cash in", "cash-in", "cashin", "ক্যাশ ইন", "ক্যাশইন", "agent এ টাকা দিয়েছি"],
    "cash_out": ["cash out", "cash-out", "cashout", "ক্যাশ আউট"],
    "settlement": ["settle", "settlement", "নিষ্পত্তি", "settle হয়নি"],
    "refund": ["refund", "ফেরত", "return", "টাকা ফেরত"],
}

SINGLE_COMPLETED_STATUSES = {"completed", "pending"}


def normalize_phone(text: str) -> str:
    cleaned = re.sub(r"[^\d]", "", text)
    if cleaned.startswith("88") and len(cleaned) > 11:
        cleaned = cleaned[2:]
    if len(cleaned) == 14 and cleaned.startswith("880"):
        cleaned = cleaned[3:]
    if len(cleaned) == 13 and cleaned.startswith("880"):
        cleaned = cleaned[3:]
    return cleaned


def extract_counterparty_hint(text: str) -> str | None:
    patterns = [
        re.compile(r"(?:number|নম্বর|number was|number is)\s*(?:was|is)?\s*:?\s*(01\d{8,9})"),
        re.compile(r"(?:to|থেকে|থেকে)\s*(?:\+?8801\d{8,9}|01\d{8,9})"),
        re.compile(r"(?<!\d)(?:\+?8801\d{8,9}|01\d{8,9})(?!\d)"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return normalize_phone(match.group(0))
    return None


def _extract_type_intent(text: str) -> str | None:
    lower = text.lower()
    for txn_type, keywords in TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in lower:
                return txn_type
    return None


def _parse_timestamp(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_shortlist(
    history: list[TransactionIn], complaint: str
) -> tuple[list[dict], str]:
    if not history:
        return [], "no_match"

    claimed_amount = extract_amount(complaint)
    claimed_time = extract_time(complaint)
    counterparty_hint = extract_counterparty_hint(complaint)
    type_intent = _extract_type_intent(complaint)

    fields_present = sum(1 for f in [claimed_amount, claimed_time, counterparty_hint, type_intent] if f is not None)
    if fields_present == 0:
        weights = {"amount": 0.55, "time": 0.25, "counterparty": 0.15, "type": 0.05}
    else:
        base = {"amount": 0.55, "time": 0.25, "counterparty": 0.15, "type": 0.05}
        missing_weight = sum(base[k] for k in base if k not in _present_fields(claimed_amount, claimed_time, counterparty_hint, type_intent))
        scale = 1.0 / (1.0 - missing_weight) if missing_weight < 1.0 else 1.0
        weights = {}
        for k, v in base.items():
            key_present = {"amount": claimed_amount, "time": claimed_time, "counterparty": counterparty_hint, "type": type_intent}[k] is not None
            weights[k] = v * scale if key_present else 0.0

    scored = []
    for txn in history:
        amount_score = 0.0
        if claimed_amount is not None:
            amount_score = 1.0 if fuzzy_amount_match(claimed_amount, txn.amount) else 0.0

        time_score = 0.0
        if claimed_time is not None:
            txn_time = _parse_timestamp(txn.timestamp)
            if txn_time:
                hours_diff = (txn_time - claimed_time).total_seconds() / 3600
                time_score = time_decay_weight(hours_diff)

        counterparty_score = 0.0
        if counterparty_hint is not None:
            ratio = fuzz.token_set_ratio(normalize_phone(counterparty_hint), normalize_phone(txn.counterparty))
            counterparty_score = ratio / 100.0

        type_score = 0.0
        if type_intent is not None:
            type_score = 1.0 if type_intent == txn.type else 0.0

        total = (
            weights["amount"] * amount_score
            + weights["time"] * time_score
            + weights["counterparty"] * counterparty_score
            + weights["type"] * type_score
        )

        scored.append({
            "transaction_id": txn.transaction_id,
            "score": round(total, 4),
            "matched_amount": amount_score >= 0.98,
            "matched_time": time_score > 0.01,
            "matched_counterparty": counterparty_score >= 0.70,
            "matched_type": type_score >= 0.99,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    if not scored:
        return [], "no_match"

    top_score = scored[0]["score"]
    if top_score < 0.40:
        return scored, "no_match"

    if len(scored) == 1:
        return scored, "single_match"

    gap = scored[0]["score"] - scored[1]["score"]
    flag = "single_match" if gap >= 0.05 else "ambiguous"

    return scored, flag


def _present_fields(amount, time, counterparty, type_intent) -> set[str]:
    fields = set()
    if amount is not None:
        fields.add("amount")
    if time is not None:
        fields.add("time")
    if counterparty is not None:
        fields.add("counterparty")
    if type_intent is not None:
        fields.add("type")
    return fields


def is_vague_complaint(complaint: str) -> bool:
    word_count = len(complaint.split())
    has_amount = extract_amount(complaint) is not None
    has_counterparty = extract_counterparty_hint(complaint) is not None
    has_time = extract_time(complaint) is not None
    return (not has_amount and not has_counterparty and not has_time and word_count < 12)


def detect_duplicate_pattern(history: list[TransactionIn]) -> str | None:
    if not history or len(history) < 2:
        return None

    completed = [t for t in history if t.status == "completed"]
    for i in range(len(completed)):
        for j in range(i + 1, len(completed)):
            a, b = completed[i], completed[j]
            if a.amount == b.amount and a.counterparty == b.counterparty:
                t_a = _parse_timestamp(a.timestamp)
                t_b = _parse_timestamp(b.timestamp)
                if t_a and t_b:
                    diff_seconds = abs((t_b - t_a).total_seconds())
                    if diff_seconds <= 60:
                        later = b if t_b > t_a else a
                        return later.transaction_id
    return None


CASE_TO_DEPARTMENT: dict[CaseType, Department] = {
    CaseType.wrong_transfer: Department.dispute_resolution,
    CaseType.payment_failed: Department.payments_ops,
    CaseType.duplicate_payment: Department.payments_ops,
    CaseType.merchant_settlement_delay: Department.merchant_operations,
    CaseType.agent_cash_in_issue: Department.agent_operations,
    CaseType.refund_request: Department.customer_support,
    CaseType.phishing_or_social_engineering: Department.fraud_risk,
    CaseType.other: Department.customer_support,
}


def _enforce_department(result: TicketOut) -> None:
    expected = CASE_TO_DEPARTMENT.get(result.case_type)
    if expected is not None and result.department != expected:
        result.department = expected
        _add_reason(result, "department_override")


# ── Rule Overlay + Verifier ──

_PHISHING_REPORT = re.compile(
    r"(?:"
    r"(?:called|contacted|messaged)\s+me\s+(?:saying|claiming|pretending)"
    r"|"
    r"(?:ask(?:ed)?|requested)\s+(?:for\s+)?(?:my|me\s+(?:for\s+)?)\s+(?:otp|pin|password)"
    r"|"
    r"(?:account|wallet)\s+(?:will\s+be|is\s+going\s+to\s+be)\s+(?:blocked|suspended|closed)"
    r")",
    re.IGNORECASE,
)


def _is_phishing_report(complaint: str) -> bool:
    return bool(_PHISHING_REPORT.search(complaint))


def _find_established_recipient(history: list[TransactionIn], threshold: int = 3) -> tuple[str | None, int]:
    counts: dict[str, int] = {}
    for txn in history:
        if txn.status == "completed" and txn.type == "transfer":
            cp = txn.counterparty.strip()
            if cp:
                counts[cp] = counts.get(cp, 0) + 1
    for cp, count in counts.items():
        if count >= threshold:
            return cp, count
    return None, 0


def _add_reason(result: TicketOut, code: str) -> None:
    if result.reason_codes is None:
        result.reason_codes = []
    if code not in result.reason_codes:
        result.reason_codes.append(code)


def _verify_llm_output(
    result: TicketOut,
    shortlist: list[dict],
    flag: str,
) -> None:
    shortlist_ids = {s["transaction_id"] for s in shortlist}

    if flag == "ambiguous":
        result.relevant_transaction_id = None
        result.evidence_verdict = EvidenceVerdict.insufficient_data
        _add_reason(result, "ambiguous_override")

    if flag == "no_match" or not shortlist:
        result.relevant_transaction_id = None
        result.evidence_verdict = EvidenceVerdict.insufficient_data
        _add_reason(result, "no_match_override")

    if result.relevant_transaction_id is not None and result.relevant_transaction_id not in shortlist_ids:
        result.relevant_transaction_id = None
        _add_reason(result, "unverified_transaction")


def _apply_rules(
    result: TicketOut,
    complaint: str,
    history: list[TransactionIn],
) -> None:
    if is_vague_complaint(complaint):
        result.relevant_transaction_id = None
        result.evidence_verdict = EvidenceVerdict.insufficient_data
        _add_reason(result, "vague_override")

    if result.case_type == CaseType.wrong_transfer and history:
        cp, count = _find_established_recipient(history)
        if cp is not None:
            result.evidence_verdict = EvidenceVerdict.inconsistent
            _add_reason(result, "established_recipient_pattern")

    if not history and _is_phishing_report(complaint):
        result.case_type = CaseType.phishing_or_social_engineering
        result.severity = Severity.critical
        result.department = Department.fraud_risk
        result.evidence_verdict = EvidenceVerdict.insufficient_data
        result.relevant_transaction_id = None
        _add_reason(result, "phishing_override")

    dup_id = detect_duplicate_pattern(history)
    if dup_id is not None:
        if result.relevant_transaction_id != dup_id:
            result.relevant_transaction_id = dup_id
            _add_reason(result, "duplicate_auto_detected")


def post_process_llm_output(
    candidate: TicketOut,
    shortlist: list[dict],
    flag: str,
    complaint: str,
    history: list[TransactionIn],
) -> TicketOut:
    result = candidate.model_copy(deep=True)
    _verify_llm_output(result, shortlist, flag)
    _apply_rules(result, complaint, history)
    _enforce_department(result)
    return result
