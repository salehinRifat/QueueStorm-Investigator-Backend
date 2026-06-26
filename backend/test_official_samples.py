import json, sys, requests

SAMPLES = r"C:\Users\Abdullah\OneDrive\Desktop\sust_hack\docs\SUST_Preli_Sample_Cases.json"
URL = "http://127.0.0.1:8000/analyze-ticket"

with open(SAMPLES, encoding="utf-8") as f:
    data = json.load(f)

all_cases = {c["id"]: c for c in data["cases"]}
SELECTED = ["SAMPLE-01", "SAMPLE-05", "SAMPLE-07"]

passed = 0
failed = 0

for sid in SELECTED:
    case = all_cases[sid]
    inp = case["input"]
    exp = case["expected_output"]
    try:
        r = requests.post(URL, json=inp, timeout=60)
    except Exception as e:
        print(f"{sid:12s} | CONNECTION ERROR: {e}")
        failed += 1
        continue

    if r.status_code != 200:
        print(f"{sid:12s} | HTTP {r.status_code} — {r.text[:200]}")
        failed += 1
        continue

    out = r.json()
    checks = []
    if out.get("relevant_transaction_id") != exp["relevant_transaction_id"]:
        checks.append(f"txn_id got={out.get('relevant_transaction_id')} exp={exp['relevant_transaction_id']}")
    if out.get("evidence_verdict") != exp["evidence_verdict"]:
        checks.append(f"verdict got={out.get('evidence_verdict')} exp={exp['evidence_verdict']}")
    if out.get("case_type") != exp["case_type"]:
        checks.append(f"case_type got={out.get('case_type')} exp={exp['case_type']}")
    if out.get("department") != exp["department"]:
        checks.append(f"dept got={out.get('department')} exp={exp['department']}")
    if out.get("human_review_required") != exp["human_review_required"]:
        checks.append(f"human_review got={out.get('human_review_required')} exp={exp['human_review_required']}")

    if checks:
        print(f"{sid:12s} | FAIL | {'; '.join(checks)}")
        print(f"           severity={out.get('severity')} reason_codes={out.get('reason_codes', [])}")
        failed += 1
    else:
        print(f"{sid:12s} | PASS | verdict={out['evidence_verdict']} case={out['case_type']} dept={out['department']} hr={out['human_review_required']}")

print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed out of {len(SELECTED)}")
sys.exit(0 if failed == 0 else 1)
