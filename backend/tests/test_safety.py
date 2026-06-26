from app.models.response import TicketOut
from app.enums import EvidenceVerdict, CaseType, Severity, Department
from app.safety.scrubber import scrub_reply, check_safety


def _make_ticket(customer_reply: str = "Our team will contact you.", recommended_next_action: str = "Investigate the case.", human_review: bool = False) -> TicketOut:
    return TicketOut(
        ticket_id="TKT-TEST",
        relevant_transaction_id="TXN-001",
        evidence_verdict=EvidenceVerdict.consistent,
        case_type=CaseType.wrong_transfer,
        severity=Severity.high,
        department=Department.dispute_resolution,
        agent_summary="Test case.",
        recommended_next_action=recommended_next_action,
        customer_reply=customer_reply,
        human_review_required=human_review,
        confidence=0.9,
        reason_codes=["test"],
    )


def test_english_pin_detected():
    text, modified = scrub_reply("Please share your PIN with us.")
    assert modified
    assert "We never ask for your PIN, OTP, or password" in text


def test_english_otp_detected():
    text, modified = scrub_reply("Share your OTP so we can verify.")
    assert modified
    assert "We never ask for your PIN, OTP, or password" in text


def test_english_password_detected():
    text, modified = scrub_reply("Enter your password to proceed.")
    assert modified
    assert "We never ask for your PIN, OTP, or password" in text


def test_refund_promise_detected():
    text, modified = scrub_reply("We will refund you 500 taka.")
    assert modified
    assert "eligible amount" in text


def test_money_returned_detected():
    text, modified = scrub_reply("Your money will be returned soon.")
    assert modified
    assert "eligible amount" in text


def test_reversal_detected():
    text, modified = scrub_reply("We will reverse the transaction.")
    assert modified
    assert "eligible amount" in text


def test_unblock_detected():
    text, modified = scrub_reply("Your account will be unblocked shortly.")
    assert modified


def test_third_party_contact_detected():
    text, modified = scrub_reply("Please contact this number for help.")
    assert modified


def test_bangla_pin_detected():
    text, modified = scrub_reply("আপনার পিন দিন।")
    assert modified
    assert "পিন" not in text or "PIN" in text


def test_bangla_refund_detected():
    text, modified = scrub_reply("আমরা ফেরত দেব।")
    assert modified


def test_bangla_unblock_detected():
    text, modified = scrub_reply("আপনার একাউন্ট খুলে দেওয়া হবে।")
    assert modified


def test_banglish_pin_detected():
    text, modified = scrub_reply("apnar pin din.")
    assert modified


def test_banglish_refund_detected():
    text, modified = scrub_reply("amra refund dibo.")
    assert modified


def test_safe_text_unchanged():
    text, modified = scrub_reply("Our team will review your case through official channels. Please keep your credentials private.")
    assert not modified


def test_safe_bangla_unchanged():
    text, modified = scrub_reply("আমাদের টিম আপনার কেস পর্যালোচনা করে অফিসিয়াল চ্যানেলে যোগাযোগ করবে। অনুগ্রহ করে কারো সাথে পিন বা ওটিপি শেয়ার করবেন না।")
    assert not modified


def test_multiple_violations():
    text, modified = scrub_reply("Share your PIN. We will refund you.")
    assert modified
    assert "We never ask for your PIN, OTP, or password" in text
    assert "eligible amount" in text


def test_case_insensitive():
    text, modified = scrub_reply("SHARE YOUR PIN NOW.")
    assert modified


def test_check_safety_updates_ticket():
    ticket = _make_ticket(customer_reply="Share your PIN with us.")
    result = check_safety(ticket)
    assert result.human_review_required
    assert "safety_override" in (result.reason_codes or [])


def test_check_safety_no_change_safe():
    ticket = _make_ticket(customer_reply="Our team will assist you through official channels.")
    result = check_safety(ticket)
    assert not result.human_review_required
    assert "safety_override" not in (result.reason_codes or [])


def test_recommended_action_also_scrubbed():
    ticket = _make_ticket(
        customer_reply="We will check.",
        recommended_next_action="We will reverse the transaction.",
    )
    result = check_safety(ticket)
    assert result.human_review_required
    assert "eligible amount" in result.recommended_next_action
    assert "safety_override" in (result.reason_codes or [])


def test_original_ticket_unchanged():
    ticket = _make_ticket(customer_reply="Share your PIN.")
    result = check_safety(ticket)
    assert result.customer_reply != ticket.customer_reply
    assert ticket.customer_reply == "Share your PIN."


def test_empty_text():
    text, modified = scrub_reply("")
    assert not modified
    assert text == ""
