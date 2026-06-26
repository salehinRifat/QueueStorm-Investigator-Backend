import json, sys
sys.path.insert(0, ".")

from app.models.request import TicketIn
from app.service.prompt_builder import build_prompt, build_json_schema
from app.llm.client import call_llm, LLMError

SAMPLES = r"C:\Users\Abdullah\OneDrive\Desktop\sust_hack\docs\SUST_Preli_Sample_Cases.json"
with open(SAMPLES, encoding="utf-8") as f:
    data = json.load(f)

targets = ["SAMPLE-07", "SAMPLE-09", "SAMPLE-10"]
cases = {c["id"]: c for c in data["cases"]}

for sid in targets:
    inp = cases[sid]["input"]
    ticket = TicketIn(**inp)

    from app.service.rules import compute_shortlist
    shortlist, flag = compute_shortlist(ticket.transaction_history or [], ticket.complaint)

    messages = build_prompt(ticket, shortlist, flag)
    schema = build_json_schema()

    print(f"\n=== {sid} ===")
    print(f"Shortlist: {shortlist}, flag={flag}")
    print(f"Messages[0] length: {len(messages[0]['content'])}")
    print(f"Messages[1] length: {len(messages[1]['content'])}")
    print(f"Total message chars: {sum(len(m['content']) for m in messages)}")

    try:
        result = call_llm(messages, schema)
        print(f"SUCCESS: verdict={result.get('evidence_verdict')}")
    except LLMError as e:
        print(f"LLMError: {e}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
