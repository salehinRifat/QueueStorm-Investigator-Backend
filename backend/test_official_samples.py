import json, sys, requests

SAMPLES = r"C:\Users\Abdullah\OneDrive\Desktop\sust_hack\docs\SUST_Preli_Sample_Cases.json"
URL = "http://127.0.0.1:8000/analyze-ticket"

with open(SAMPLES, encoding="utf-8") as f:
    data = json.load(f)

cases = data["cases"]

_SEVERITY_LEVELS = {"low": 0, "medium": 1, "high": 2, "critical": 3}

passed = 0
failed = 0
with_warnings = 0

print(f"{'ID':12s} {'Verdict':16s} {'Case':24s} {'Dept':22s} {'Sev':8s} {'HR':4s} {'Result':6s}")
print("-" * 92)

for case in cases:
    inp = case["input"]
    exp = case["expected_output"]
    sid = case["id"]

    try:
        r = requests.post(URL, json=inp, timeout=60)
    except Exception as e:
        print(f"{sid:12s} {'CONNECTION ERROR':>50s}")
        failed += 1
        continue

    if r.status_code != 200:
        print(f"{sid:12s} HTTP {r.status_code}")
        failed += 1
        continue

    out = r.json()
    checks = []

    # required fields must exist
    for field in ["evidence_verdict", "case_type", "department", "severity", "human_review_required"]:
        if field not in out:
            checks.append(f"missing field: {field}")

    if not checks:
        txn_ok = out.get("relevant_transaction_id") == exp.get("relevant_transaction_id")
        if not txn_ok:
            checks.append(f"txn_id got={out.get('relevant_transaction_id')} exp={exp.get('relevant_transaction_id')}")

        if out.get("evidence_verdict") != exp.get("evidence_verdict"):
            checks.append(f"verdict got={out.get('evidence_verdict')} exp={exp.get('evidence_verdict')}")

        if out.get("case_type") != exp.get("case_type"):
            checks.append(f"case got={out.get('case_type')} exp={exp.get('case_type')}")

        if out.get("department") != exp.get("department"):
            checks.append(f"dept got={out.get('department')} exp={exp.get('department')}")

        if out.get("human_review_required") != exp.get("human_review_required"):
            checks.append(f"hr got={out.get('human_review_required')} exp={exp.get('human_review_required')}")

    sev = out.get("severity", "?")
    hr = str(out.get("human_review_required", "?"))
    exp_sev = exp.get("severity", "?")

    if checks:
        print(f"{sid:12s} {out.get('evidence_verdict','?'):16s} {out.get('case_type','?'):24s} {out.get('department','?'):22s} {sev:8s} {hr:4s} FAIL")
        for c in checks:
            print(f"  {'':12s} {c}")
        print(f"  {'':12s} codes={out.get('reason_codes', [])}")
        reply = out.get('customer_reply', '')
        if reply:
            print(f"  {'':12s} reply: {reply[:150]}...")
        failed += 1
    else:
        sev_diff = abs(_SEVERITY_LEVELS.get(sev, 0) - _SEVERITY_LEVELS.get(exp_sev, 0))
        flag = "  OK" if sev_diff <= 1 else "SEV!"
        print(f"{sid:12s} {out.get('evidence_verdict'):16s} {out.get('case_type'):24s} {out.get('department'):22s} {sev:8s} {hr:4s} PASS{flag}")
        passed += 1
        if sev_diff > 0:
            with_warnings += 1

print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed out of {len(cases)}")
if with_warnings:
    print(f"Warnings: {with_warnings} cases had severity mismatch (within tolerance)")
sys.exit(0 if failed == 0 else 1)
