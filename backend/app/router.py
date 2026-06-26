import logging

from fastapi import APIRouter
from app.models.request import TicketIn
from app.models.response import TicketOut
from app.enums import EvidenceVerdict, CaseType, Severity, Department
from app.service.orchestrator import investigate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/analyze-ticket", response_model=TicketOut)
async def analyze_ticket(ticket: TicketIn):
    try:
        return investigate(ticket)
    except Exception:
        logger.exception("Unhandled error in analyze_ticket")
        return TicketOut(
            ticket_id=ticket.ticket_id,
            relevant_transaction_id=None,
            evidence_verdict=EvidenceVerdict.insufficient_data,
            case_type=CaseType.other,
            severity=Severity.medium,
            department=Department.customer_support,
            agent_summary="A system error occurred during analysis.",
            recommended_next_action="Review the case manually through official channels.",
            customer_reply="We encountered a technical issue while reviewing your concern. Our team will follow up through official channels. Please do not share your PIN or OTP with anyone.",
            human_review_required=True,
            confidence=0.0,
            reason_codes=["system_error"],
        )
