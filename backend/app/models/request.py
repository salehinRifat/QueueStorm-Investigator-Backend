from pydantic import BaseModel, Field
from typing import Optional
from app.enums import Language, Channel, UserType, TransactionType, TransactionStatus


class TransactionIn(BaseModel):
    transaction_id: str
    timestamp: str
    type: TransactionType
    amount: float
    counterparty: str
    status: TransactionStatus


class TicketIn(BaseModel):
    ticket_id: str
    complaint: str = Field(min_length=1)
    language: Optional[Language] = None
    channel: Optional[Channel] = None
    user_type: Optional[UserType] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[list[TransactionIn]] = None
    metadata: Optional[dict] = None
