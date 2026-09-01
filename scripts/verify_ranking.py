"""Phase 8 ranking verification: POST a new incident similar to the OOM seed
cluster, then GET it back and print the ranked similar_incidents."""
import json
import os
import urllib.error
import urllib.request

BASE = os.getenv("TRACEPULSE_URL", "http://localhost:8001")


def _load_api_key() -> str:
    """Prefer TRACEPULSE_API_KEY from the repo .env, falling back to the
    process env. Fail fast with a clear error when unset."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("TRACEPULSE_API_KEY="):
                    return line.split("=", 1)[1].strip()
    key = os.getenv("TRACEPULSE_API_KEY", "")
    if not key:
        raise SystemExit(
            "ERROR: TRACEPULSE_API_KEY is not set.\n"
            "Set it in the repo .env (TRACEPULSE_API_KEY=...) or export it "
            "in your shell before running this script."
        )
    return key


KEY = _load_api_key()

NEW = {
    "title": "Report generator pod OOMKilled during nightly batch",
    "description": "The report-generator pod keeps getting OOMKilled and restarting during the nightly batch. Memory limit is 512mb but peak usage reaches 1.5gb when rendering large PDFs.",
    "logs": "container report-gen-2f8a: OOMKilled, exit code 137, restart count 9",
    "system": "reports", "severity": "high",
}


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        headers={"X-API-Key": KEY, "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


status, ticket = call("POST", "/tickets", NEW)
tid = ticket["id"]
print(f"POST /tickets -> {status}, id={tid}")

status, detail = call("GET", f"/tickets/{tid}")
print(f"GET /tickets/{tid} -> {status}")
print("similar_incidents (ranked):")
for rank, s in enumerate(detail.get("similar_incidents", []), 1):
    print(f"  {rank}. id={s['ticket_id']:>2}  sim={s['similarity']:<7} {s['title']}")
