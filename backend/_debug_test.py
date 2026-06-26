import httpx, json

SAMPLE_01 = {
    "ticket_id": "TKT-001",
    "complaint": "I sent 5000 taka to a wrong number around 2pm today. The number was supposed to be 01712345678 but I think I typed it wrong. The person isn't responding to my call. Please help me get my money back.",
    "language": "en",
    "channel": "in_app_chat",
    "user_type": "customer",
    "campaign_context": "boishakh_bonanza_day_1",
    "transaction_history": [
        {"transaction_id": "TXN-9101", "timestamp": "2026-04-14T14:08:22Z", "type": "transfer", "amount": 5000, "counterparty": "+8801719876543", "status": "completed"},
        {"transaction_id": "TXN-9087", "timestamp": "2026-04-13T18:12:00Z", "type": "cash_in", "amount": 10000, "counterparty": "AGENT-512", "status": "completed"},
    ],
}

r = httpx.post("http://127.0.0.1:8000/analyze-ticket", json=SAMPLE_01, timeout=30)
print(f"Status: {r.status_code}")
d = r.json()
print(f"verdict={d.get('evidence_verdict')} codes={d.get('reason_codes', [])}")
print(f"txn_id={d.get('relevant_transaction_id')}")
print(f"case={d.get('case_type')} dept={d.get('department')} sev={d.get('severity')}")
print(f"summary={d.get('agent_summary', '')[:200]}")
print(f"reply={d.get('customer_reply', '')[:200]}")
