import json
import os
from pathlib import Path
from app.enums import EvidenceVerdict, CaseType, Severity, Department
from app.models.request import TransactionIn
from app.models.response import TicketOut
from app.service.rules import (
    compute_shortlist,
    is_vague_complaint,
    detect_duplicate_pattern,
    extract_counterparty_hint,
    post_process_llm_output,
    _is_phishing_report,
    _find_established_recipient,
)
from app.utils.amounts import normalize_bangla_digits, extract_amount, fuzzy_amount_match
from app.utils.timeparse import extract_time

SAMPLES_PATH = Path(__file__).resolve().parent.parent / "SUST_Preli_Sample_Cases.json"


def _load_samples():
    with open(SAMPLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _make_txns(raw_txns: list[dict]) -> list[TransactionIn]:
    return [TransactionIn(**t) for t in raw_txns] if raw_txns else []


def test_normalize_bangla_digits():
    assert normalize_bangla_digits("২০০০ টাকা") == "2000 টাকা"
    assert normalize_bangla_digits("৫০০") == "500"
    assert normalize_bangla_digits("৳১০০০") == "1000"
    assert normalize_bangla_digits("hello ১২৩ world") == "hello 123 world"


def test_extract_amount():
    assert extract_amount("I sent 5000 taka") == 5000.0
    assert extract_amount("পেমেন্ট ১২০০ টাকা") == 1200.0
    assert extract_amount("850 BDT") == 850.0
    assert extract_amount("৳১০০০") == 1000.0
    assert extract_amount("no amount here") is None


def test_fuzzy_amount_match():
    assert fuzzy_amount_match(5000, 5000)
    assert fuzzy_amount_match(5000, 5110, tolerance=0.02) is False
    assert fuzzy_amount_match(5000, 5010, tolerance=0.02) is True
    assert fuzzy_amount_match(100, 105, tolerance=0.05) is True


def test_extract_time():
    assert extract_time("around 2pm today") is not None
    assert extract_time("yesterday") is not None
    assert extract_time("no time ref") is None


def test_extract_counterparty_hint():
    assert extract_counterparty_hint("number was 01712345678") is not None
    assert extract_counterparty_hint("no phone here") is None


def test_sample_01_wrong_transfer_match():
    samples = _load_samples()
    case = samples["cases"][0]
    txns = _make_txns(case["input"]["transaction_history"])
    shortlist, flag = compute_shortlist(txns, case["input"]["complaint"])
    assert flag == "single_match", f"SAMPLE-01: expected single_match, got {flag}"
    assert len(shortlist) > 0
    assert shortlist[0]["transaction_id"] == "TXN-9101"


def test_sample_02_inconsistent_pattern():
    samples = _load_samples()
    case = samples["cases"][1]
    txns = _make_txns(case["input"]["transaction_history"])
    shortlist, flag = compute_shortlist(txns, case["input"]["complaint"])
    top_id = shortlist[0]["transaction_id"] if shortlist else None
    assert top_id == "TXN-9202", f"SAMPLE-02: expected TXN-9202, got {top_id}"
    assert shortlist[0]["matched_amount"], "Should match amount"
    assert not shortlist[0]["matched_counterparty"], "No phone in complaint, should be unmatched"


def test_sample_03_failed_payment():
    samples = _load_samples()
    case = samples["cases"][2]
    txns = _make_txns(case["input"]["transaction_history"])
    shortlist, flag = compute_shortlist(txns, case["input"]["complaint"])
    assert len(shortlist) == 1
    assert shortlist[0]["transaction_id"] == "TXN-9301"


def test_sample_05_phishing_empty_history():
    samples = _load_samples()
    case = samples["cases"][4]
    txns = _make_txns(case["input"]["transaction_history"])
    shortlist, flag = compute_shortlist(txns, case["input"]["complaint"])
    assert flag == "no_match"
    assert len(shortlist) == 0


def test_sample_06_vague_complaint():
    samples = _load_samples()
    case = samples["cases"][5]
    assert is_vague_complaint(case["input"]["complaint"]), "SAMPLE-06 should be vague"


def test_sample_07_bangla_cash_in():
    samples = _load_samples()
    case = samples["cases"][6]
    txns = _make_txns(case["input"]["transaction_history"])
    shortlist, flag = compute_shortlist(txns, case["input"]["complaint"])
    assert len(shortlist) > 0
    assert shortlist[0]["transaction_id"] == "TXN-9701"


def test_sample_08_ambiguous_match():
    samples = _load_samples()
    case = samples["cases"][7]
    txns = _make_txns(case["input"]["transaction_history"])
    shortlist, flag = compute_shortlist(txns, case["input"]["complaint"])
    assert flag == "ambiguous", f"SAMPLE-08: expected ambiguous, got {flag}"
    assert shortlist[0]["matched_amount"], "All three TXNs match amount"


def test_sample_09_merchant_settlement():
    samples = _load_samples()
    case = samples["cases"][8]
    txns = _make_txns(case["input"]["transaction_history"])
    shortlist, flag = compute_shortlist(txns, case["input"]["complaint"])
    assert len(shortlist) == 1
    assert shortlist[0]["transaction_id"] == "TXN-9901"


def test_sample_10_duplicate_detection():
    samples = _load_samples()
    case = samples["cases"][9]
    txns = _make_txns(case["input"]["transaction_history"])
    dup = detect_duplicate_pattern(txns)
    assert dup == "TXN-10002", f"SAMPLE-10: expected TXN-10002, got {dup}"


def test_is_vague_false_for_detailed():
    assert not is_vague_complaint("I sent 5000 taka to 01712345678 yesterday around 2pm")


def test_empty_history_returns_no_match():
    shortlist, flag = compute_shortlist([], "I have a problem")
    assert flag == "no_match"
    assert len(shortlist) == 0


# ── Verifier tests ──

def _make_candidate(
    txn_id: str | None = "TXN-001",
    verdict: EvidenceVerdict = EvidenceVerdict.consistent,
    case_type: CaseType = CaseType.wrong_transfer,
    severity: Severity = Severity.high,
    department: Department = Department.dispute_resolution,
    reason_codes: list[str] | None = None,
) -> TicketOut:
    return TicketOut(
        ticket_id="TKT-TEST",
        relevant_transaction_id=txn_id,
        evidence_verdict=verdict,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary="Test summary.",
        recommended_next_action="Investigate.",
        customer_reply="We will check.",
        human_review_required=False,
        confidence=0.9,
        reason_codes=reason_codes,
    )


def _dummy_shortlist(txid: str = "TXN-001") -> list[dict]:
    return [{"transaction_id": txid, "score": 0.9, "matched_amount": True, "matched_time": True, "matched_counterparty": True, "matched_type": True}]


def test_verifier_rejects_txn_not_in_shortlist():
    candidate = _make_candidate(txn_id="TXN-999")
    result = post_process_llm_output(candidate, _dummy_shortlist(), "single_match", "I sent 5000 taka to 01712345678.", [])
    assert result.relevant_transaction_id is None
    assert "unverified_transaction" in (result.reason_codes or [])


def test_verifier_enforces_ambiguous():
    candidate = _make_candidate(txn_id="TXN-001")
    result = post_process_llm_output(candidate, _dummy_shortlist(), "ambiguous", "I sent 1000 taka yesterday.", [])
    assert result.relevant_transaction_id is None
    assert result.evidence_verdict == EvidenceVerdict.insufficient_data
    assert "ambiguous_override" in (result.reason_codes or [])


def test_verifier_enforces_no_match():
    candidate = _make_candidate(txn_id="TXN-001")
    result = post_process_llm_output(candidate, [], "no_match", "I sent 5000 taka yesterday.", [])
    assert result.relevant_transaction_id is None
    assert result.evidence_verdict == EvidenceVerdict.insufficient_data
    assert "no_match_override" in (result.reason_codes or [])


def test_verifier_clean_passthrough():
    candidate = _make_candidate(txn_id="TXN-001")
    result = post_process_llm_output(candidate, _dummy_shortlist(), "single_match", "I sent 5000 taka to 01712345678.", [])
    assert result.relevant_transaction_id == "TXN-001"
    assert result.evidence_verdict == EvidenceVerdict.consistent


# ── Overlay tests ──

def _make_txn(txid: str, amount: float, counterparty: str, status: str = "completed", txn_type: str = "transfer") -> TransactionIn:
    return TransactionIn(transaction_id=txid, timestamp="2026-04-14T12:00:00Z", type=txn_type, amount=amount, counterparty=counterparty, status=status)


def test_overlay_established_recipient():
    history = [
        _make_txn("T1", 1000, "+8801712345678"),
        _make_txn("T2", 2000, "+8801712345678"),
        _make_txn("T3", 1500, "+8801712345678"),
    ]
    candidate = _make_candidate(txn_id="T3")
    result = post_process_llm_output(candidate, _dummy_shortlist("T3"), "single_match", "I sent money to the wrong person.", history)
    assert result.evidence_verdict == EvidenceVerdict.inconsistent
    assert "established_recipient_pattern" in (result.reason_codes or [])


def test_overlay_established_recipient_not_met():
    history = [
        _make_txn("T1", 1000, "+8801712345678"),
        _make_txn("T2", 2000, "+8801712345678"),
    ]
    candidate = _make_candidate(txn_id="T2")
    result = post_process_llm_output(candidate, _dummy_shortlist("T2"), "single_match", "I sent 2000 taka to the wrong person yesterday.", history)
    assert result.evidence_verdict == EvidenceVerdict.consistent


def test_overlay_phishing_no_history():
    candidate = _make_candidate(txn_id=None, verdict=EvidenceVerdict.insufficient_data, case_type=CaseType.other, severity=Severity.low, department=Department.customer_support)
    result = post_process_llm_output(candidate, [], "no_match",
        "Someone called me saying they are from the company and asked for my OTP. They said my account will be blocked.", [])
    assert result.case_type == CaseType.phishing_or_social_engineering
    assert result.severity == Severity.critical
    assert result.department == Department.fraud_risk
    assert result.relevant_transaction_id is None
    assert "phishing_override" in (result.reason_codes or [])


def test_overlay_vague_complaint():
    candidate = _make_candidate(txn_id="TXN-001")
    result = post_process_llm_output(candidate, _dummy_shortlist(), "single_match", "Something is wrong.", [])
    assert result.relevant_transaction_id is None
    assert result.evidence_verdict == EvidenceVerdict.insufficient_data
    assert "vague_override" in (result.reason_codes or [])


def _make_dup_txn(txid: str, timestamp: str) -> TransactionIn:
    return TransactionIn(transaction_id=txid, timestamp=timestamp, type="payment", amount=850, counterparty="BILLER-DESCO", status="completed")


def test_overlay_duplicate_auto_detected():
    history = [
        _make_dup_txn("T1", "2026-04-14T08:15:30Z"),
        _make_dup_txn("T2", "2026-04-14T08:15:42Z"),
    ]
    candidate = _make_candidate(txn_id="T1")
    result = post_process_llm_output(candidate, _dummy_shortlist("T1"), "single_match", "My 850 taka bill was deducted twice to BILLER-DESCO yesterday.", history)
    assert result.relevant_transaction_id == "T2"
    assert "duplicate_auto_detected" in (result.reason_codes or [])


def test_overlay_duplicate_llm_agrees():
    history = [
        _make_dup_txn("T1", "2026-04-14T08:15:30Z"),
        _make_dup_txn("T2", "2026-04-14T08:15:42Z"),
    ]
    candidate = _make_candidate(txn_id="T2")
    result = post_process_llm_output(candidate, _dummy_shortlist("T2"), "single_match", "My 850 taka bill was deducted twice to BILLER-DESCO yesterday.", history)
    assert result.relevant_transaction_id == "T2"
    assert "duplicate_auto_detected" not in (result.reason_codes or [])


def test_full_pipeline_vague_and_no_history():
    candidate = _make_candidate(txn_id="TXN-001")
    result = post_process_llm_output(candidate, [], "no_match", "Something is wrong with my money.", [])
    assert result.relevant_transaction_id is None
    assert result.evidence_verdict == EvidenceVerdict.insufficient_data
    codes = result.reason_codes or []
    assert "no_match_override" in codes
    assert "vague_override" in codes
    assert "unverified_transaction" not in codes
    assert len(codes) == len(set(codes)), "No duplicate reason codes"


def test_is_phishing_report_positive():
    assert _is_phishing_report("Someone called me and asked for my OTP.")


def test_is_phishing_report_negative():
    assert not _is_phishing_report("I need help with my account.")


def test_find_established_recipient_positive():
    history = [
        _make_txn("T1", 100, "+8801712345678"),
        _make_txn("T2", 200, "+8801712345678"),
        _make_txn("T3", 300, "+8801712345678"),
    ]
    cp, count = _find_established_recipient(history)
    assert cp == "+8801712345678"
    assert count >= 3


def test_find_established_recipient_mixed_types():
    history = [
        _make_txn("T1", 100, "AGENT-512", txn_type="cash_in"),
        _make_txn("T2", 200, "AGENT-512", txn_type="cash_in"),
        _make_txn("T3", 300, "AGENT-512", txn_type="cash_in"),
    ]
    cp, count = _find_established_recipient(history)
    assert cp is None
    assert count == 0
