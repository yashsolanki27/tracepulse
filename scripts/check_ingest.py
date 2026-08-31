"""Live E2E check of POST /ingest/webhook against the running local stack.

Run detached (Groq RCA can take >30s):
  Start-Process pwsh -ArgumentList '-File scripts/check_ingest.py' -WindowStyle Hidden
Result is written to ingest_check_result.txt in the repo root.
"""
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_api_key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TRACEPULSE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("TRACEPULSE_API_KEY not found in .env")


def call(payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        "http://127.0.0.1:8001/ingest/webhook",
        data=json.dumps(payload).encode(),
        headers={"X-API-Key": load_api_key(), "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as resp:
        return resp.status, json.loads(resp.read())


def main() -> None:
    payload = {
        "source": "reconciliation",
        "title": "CRM order 77 has no ERP invoice",
        "description": "Sync error: order 77 created in CRM, no matching invoice found in ERP after integration-sync -- mismatch detected",
        "labels": {"order_id": "77", "service": "crm-service"},
        "dedup_key": "order:77",
        "triage": {"triage_id": "tp_991", "category": "integration", "confidence": 0.92},
    }
    results = {}
    status, body = call(payload)
    results["first_call"] = {"http": status, **body}
    status2, body2 = call(payload)
    results["second_call_dedup"] = {"http": status2, **body2}
    req = urllib.request.Request(
        "http://127.0.0.1:8001/ingest/webhook",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            results["no_key"] = {"http": resp.status}
    except urllib.error.HTTPError as e:
        results["no_key"] = {"http": e.code, **json.loads(e.read())}
    # Fetch the created ticket to verify RCA/triage/similarity/SLA ran.
    if results["first_call"].get("ticket_id"):
        tid = results["first_call"]["ticket_id"]
        req = urllib.request.Request(
            f"http://127.0.0.1:8001/tickets/{tid}",
            headers={"X-API-Key": load_api_key()},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            t = json.loads(resp.read())
        results["ticket"] = {
            "id": t["id"],
            "title": t["title"],
            "status": t["status"],
            "priority": t["priority"],
            "root_cause_set": bool(t["root_cause"]),
            "similar_count": len(t.get("similar_incidents", [])),
            "sla_deadline": t["target_resolution_time"],
        }
    out = ROOT / "ingest_check_result.txt"
    out.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
