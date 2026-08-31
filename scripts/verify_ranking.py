"""Phase 8 ranking verification: POST a new incident similar to the OOM seed
cluster, then GET it back and print the ranked similar_incidents."""
import json
import urllib.error
import urllib.request

KEY = "f5e3dedede71bfc93cce84fa63fb0c5027442afc0dd4a00c6334f3d8fb98495e"
BASE = "http://localhost:8001"

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
