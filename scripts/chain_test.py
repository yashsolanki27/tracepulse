"""Live chain test: LogPulse /triage (deployed) -> TracePulse /ingest/webhook (local).

Run:  .venv/Scripts/python.exe scripts/chain_test.py
Writes result to chain_test_result.txt.
"""
import json
import pathlib
import sys

sys.path.insert(0, r"K:\ADVANCE WEB\pulsegrid")

from pulsegrid_common.logpulse_client import post_to_logpulse
from pulsegrid_common.tracepulse_client import post_to_tracepulse

ROOT = pathlib.Path(__file__).resolve().parent.parent

API_KEY = next(
    line.split("=", 1)[1].strip()
    for line in (ROOT / ".env").read_text().splitlines()
    if line.startswith("TRACEPULSE_API_KEY=")
)

log_text = (
    "PulseGrid alert firing: ERPInvoiceSyncFailures on erp-service:8001 "
    "(job=erp-service, severity=critical). Invoice sync error rate above 20%. "
    "Integration failure detected - alert triggered at observability layer."
)

result = {}
triage = post_to_logpulse(url="https://log-pulse.up.railway.app/triage", log_text=log_text, timeout=90.0)
result["logpulse"] = (
    {"id": triage.id, "category": triage.category, "confidence": triage.confidence}
    if triage else None
)
if triage:
    conf = triage.confidence
    if conf is not None and conf > 1:
        conf = conf / 100.0
    tp = post_to_tracepulse(
        api_key=API_KEY,
        source="alertmanager",
        title="ERPInvoiceSyncFailures on erp-service:8001",
        description="Invoice sync error rate above 20%.",
        logs=log_text,
        labels={"alertname": "ERPInvoiceSyncFailures", "instance": "erp-service:8001"},
        dedup_key="alert:ERPInvoiceSyncFailures:erp-service:8001:chaintest2",
        triage={"triage_id": triage.id, "category": triage.category, "confidence": conf},
        url="http://127.0.0.1:8001/ingest/webhook",
    )
    result["tracepulse"] = {"ticket_id": tp.ticket_id, "status": tp.status} if tp else None
else:
    result["tracepulse"] = "skipped (LogPulse failed)"

(ROOT / "chain_test_result.txt").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
