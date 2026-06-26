# QueueStorm Investigator

AI copilot that cross-references customer complaints against transaction history via LLM and returns a structured analysis with a safe customer-facing reply.

**Hackathon project for SUST Preli 2026.**

## How it works

```
POST /analyze-ticket
  │
  ├─ 1. Validate & warn     (language mismatch, vague complaint, injection attempts)
  ├─ 2. Pre-scan engine     (deterministic scoring — amount, time, counterparty, type)
  ├─ 3. Prompt builder      (injects enums, safety rules, JSON schema into prompt)
  ├─ 4. LLM call            (Gemini 2.0 Flash via googleapis.com)
  ├─ 5. Post-process        (verifier + rule overlay + department enforcement)
  ├─ 6. Safety scrubber     (strips PIN, OTP, refund promises, 3rd-party contacts)
  └─ 7. Response            (TicketOut with reason codes)
```

## API

### `POST /analyze-ticket`

**Request:**
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to 01712345678 but it didn't reach",
  "language": "en",
  "channel": "in_app_chat",
  "transaction_history": [
    {
      "transaction_id": "TXN-001",
      "timestamp": "2026-06-25T14:30:00",
      "type": "transfer",
      "amount": 5000.0,
      "counterparty": "01712345678",
      "status": "completed"
    }
  ]
}
```

**Response:**
```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-001",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "The customer sent 5000 BDT to 01712345678 via transfer. The transaction completed successfully at 2026-06-25 14:30 but the recipient claims non-receipt.",
  "recommended_next_action": "Escalate to dispute resolution team for trace investigation.",
  "customer_reply": "Thank you for reporting this. We have flagged this transaction for review by our dispute resolution team. We will follow up within 24 hours. Please do not share your PIN or OTP with anyone.",
  "human_review_required": false,
  "confidence": 0.85,
  "reason_codes": []
}
```

### `GET /health`

```json
{ "status": "ok" }
```

## Project structure

```
QueueStorm-Investigator-Backend/
├── server.py              # Vercel entry point
├── vercel.json            # Vercel config
├── requirements.txt       # Python deps
├── .env                   # LLM_API_KEY, LLM_MODEL, PORT
└── backend/
    ├── app/
    │   ├── server.py      # FastAPI app factory
    │   ├── router.py      # /analyze-ticket + /health
    │   ├── config.py      # Settings from .env
    │   ├── enums.py       # All enums (CaseType, Department, etc.)
    │   ├── models/
    │   │   ├── request.py  # TicketIn, TransactionIn
    │   │   └── response.py # TicketOut
    │   ├── llm/
    │   │   └── client.py   # Gemini API wrapper
    │   ├── service/
    │   │   ├── orchestrator.py  # Pipeline coordinator
    │   │   ├── prompt_builder.py
    │   │   └── rules.py         # Pre-scan, verifier, overlay, department map
    │   ├── safety/
    │   │   ├── scrubber.py      # Reply safety check + credential redaction
    │   │   └── banned_phrases.py
    │   └── utils/
    │       ├── language.py
    │       ├── validators.py
    │       ├── amounts.py
    │       └── timeparse.py
    └── tests/                  # 109 unit tests
```

## Setup

```bash
# Clone
git clone <repo>
cd QueueStorm-Investigator-Backend

# Environment
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt
pip install -r backend\requirements.txt   # also install test/dev deps

# Configure
copy .env.example .env    # or edit backend\.env
# Set LLM_API_KEY and LLM_MODEL (default: gemini-2.0-flash)
```

## Run locally

```bash
cd backend
python -m uvicorn app.server:app --port 8000 --reload
```

Or (Vercel-style):
```bash
cd QueueStorm-Investigator-Backend
python -m uvicorn server:app --port 8000 --reload
```

## Run tests

```bash
cd backend
python -m pytest tests/ -v
```

## Deploy to Vercel

```bash
npm i -g vercel
vercel
```

Set environment variables in Vercel dashboard:
- `LLM_API_KEY` — your Gemini API key
- `LLM_MODEL` — model name (default: `gemini-2.0-flash`)
