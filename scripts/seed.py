"""Seed TracePulse with realistic past incidents via the real API.

Creates 18 tickets (6 incident clusters x 3 variants) through
POST /tickets (real X-API-Key auth -> RCA via Groq + real embeddings),
then immediately PATCH /tickets/{id}/resolve on each so every seed
ticket ends up resolved AND embedded — eligible for similarity matching.

Rate limiting: sleeps REQUEST_DELAY seconds between tickets and retries
with backoff on HTTP 429, staying well under Groq's 30 RPM free-tier cap.

Usage:  python scripts/seed.py   (env: TRACEPULSE_API_KEY, TRACEPULSE_URL)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.getenv("TRACEPULSE_URL", "http://localhost:8001")


def _load_api_key() -> str:
    """Prefer TRACEPULSE_API_KEY from the repo .env (the key actually deployed
    in the container), falling back to the process env, then a literal."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("TRACEPULSE_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.getenv("TRACEPULSE_API_KEY", "f5e3dedede71bfc93cce84fa63fb0c5027442afc0dd4a00c6334f3d8fb98495e")


KEY = _load_api_key()
REQUEST_DELAY = float(os.getenv("SEED_DELAY", "4"))  # ~15 RPM incl. RCA latency

SEEDS = [
    # --- Cluster: database connectivity / connection pool exhaustion ---
    {
        "title": "Payment DB connection refused from checkout-service",
        "description": "checkout-service cannot connect to postgres-primary:5432. All payment requests fail with connection refused since 09:14 UTC. Connection pool shows 0 healthy connections.",
        "logs": "psycopg2.OperationalError: could not connect to server: Connection refused\nconnect timeout after 5s, pool exhausted (10/10 in use)",
        "system": "payments", "severity": "critical",
        "resolution_text": "Fixed by adding the checkout-service pod to the database security group and restarting the pool; connections recovered within 2 minutes.",
    },
    {
        "title": "Orders service fails to reach Postgres after failover",
        "description": "After the nightly failover drill the orders service still points at the old primary. Every order insert fails with 'server closed the connection unexpectedly'.",
        "logs": "sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) server closed the connection unexpectedly\nreconnect attempts exhausted, giving up",
        "system": "orders", "severity": "high",
        "resolution_text": "Updated the DATABASE_URL secret to the new primary endpoint, redeployed, and verified write throughput returned to baseline.",
    },
    {
        "title": "Analytics warehouse connection pool exhausted",
        "description": "The analytics ETL workers exhaust the warehouse connection pool during the morning batch, causing 'too many clients already' errors and stalled pipelines.",
        "logs": "FATAL: sorry, too many clients already\netl-worker-3: pool checkout timeout after 30s",
        "system": "analytics", "severity": "medium",
        "resolution_text": "Capped ETL worker concurrency at pool size and added PgBouncer in transaction mode; saturation alerts cleared and the batch completed normally.",
    },
    # --- Cluster: memory / OOM ---
    {
        "title": "Image-resizer pods OOMKilled during thumbnail batch",
        "description": "media-service image-resizer pods get OOMKilled every 10 minutes while processing the daily thumbnail batch. Memory limit is 512mb, peak usage reaches 1.2gb on large uploads.",
        "logs": "container image-resizer-4xk9: OOMKilled, exit code 137, restart count 22",
        "system": "media", "severity": "high",
        "resolution_text": "Raised the memory limit to 2GiB and added a streaming resize path for images over 20mb; no OOMKills in the following batch.",
    },
    {
        "title": "Search indexer leaking memory until OOM",
        "description": "The search indexer's RSS grows steadily by ~300mb/hour until the container is killed. Restarting temporarily fixes it; the leak correlates with large batch indexing jobs.",
        "logs": "kubernetes: node reported OOM event for indexer-0\nrss 2.9GiB / limit 3GiB",
        "system": "search", "severity": "high",
        "resolution_text": "Fixed the unbounded batch buffer by flushing to the index every 5k docs; RSS now stays flat under 800mb over 48h.",
    },
    {
        "title": "Notifications worker crashes with MemoryError",
        "description": "The notification worker crashes with a Python MemoryError when loading the full recipient list for large campaigns into memory at once.",
        "logs": "MemoryError: Unable to allocate 3.4 GiB for array in campaign_loader.py:88",
        "system": "notifications", "severity": "medium",
        "resolution_text": "Rewrote the loader to stream recipients in chunks of 1000 and bumped the container to 1GiB; large campaigns complete without errors.",
    },
    # --- Cluster: auth / certificates ---
    {
        "title": "JWT validation failing after key rotation",
        "description": "After rotating the signing keys, the API returns 401 for all requests signed with the new key. The auth service still trusts only the stale JWKS cache.",
        "logs": "auth-service ERROR InvalidSignatureError: key id 'sk-2026-06' not in JWKS\n401 on /api/v2/* for 12 minutes",
        "system": "auth", "severity": "critical",
        "resolution_text": "Lowered the JWKS cache TTL to 5 minutes and pre-warmed both keys during rotation; future rotations no longer cause 401 storms.",
    },
    {
        "title": "Expired TLS certificate breaks service-to-service auth",
        "description": "Internal mTLS between the api-gateway and user-service started failing with certificate verify failed; the leaf cert expired overnight.",
        "logs": "ssl.SSLCertVerificationError: certificate has expired (notAfter=Aug 30 23:59:59 2026)",
        "system": "platform", "severity": "critical",
        "resolution_text": "Replaced the expired leaf certificate via cert-manager and added a 14-day expiry alert so renewals can never silently lapse again.",
    },
    {
        "title": "SSO login loop for enterprise tenants",
        "description": "Enterprise SSO users are bounced back to the login page after authenticating. The session cookie is rejected because clock skew between the IdP and the auth service exceeds tolerance.",
        "logs": "WARN session rejected: token nbf is 471s in the future\nIdP skews +8min after DST change",
        "system": "auth", "severity": "high",
        "resolution_text": "Increased the allowed token clock-skew leeway to 120 seconds and fixed the IdP NTP config; logins restored for all enterprise tenants.",
    },
    # --- Cluster: network / timeouts ---
    {
        "title": "Intermittent packet loss between services in us-east-1",
        "description": "Random 2-5% packet loss between service subnets causes sporadic request timeouts across the mesh. Not tied to any deploy; started after the network policy change.",
        "logs": "ping stats: 4.1% packet loss avg over 10 min\nh3 WARN request timeout after 2000ms (12 occurrences/min)",
        "system": "platform", "severity": "high",
        "resolution_text": "Rolled back the over-broad network policy that blocked VXLAN traffic between subnets; packet loss back to 0% and mesh timeouts stopped.",
    },
    {
        "title": "Payment gateway requests timing out at 30s",
        "description": "All calls to the external payment gateway hang and time out after 30 seconds since 03:40 UTC. Direct curl from a bastion works, pointing to NAT gateway port exhaustion.",
        "logs": "httpx.ReadTimeout: timeout 30s exceeded (gateway acme-pay v2)\nNAT gateway: 64k/64k ports in use",
        "system": "payments", "severity": "critical",
        "resolution_text": "Added a second NAT gateway IP and reduced idle connection hold time to 60s; SNAT port exhaustion cleared and gateway calls return in under 300ms.",
    },
    {
        "title": "Websocket connections dropped behind load balancer",
        "description": "Clients using websockets are disconnected every ~60 seconds. The load balancer idle timeout is shorter than the application keep-alive interval.",
        "logs": "client-9f2: ws closed 1001 (going away) after 61s\nlb logs show idle_timeout=60s",
        "system": "platform", "severity": "medium",
        "resolution_text": "Reduced the client keep-alive ping interval to 30s so it beats the LB idle timeout; websocket sessions now stay up for hours.",
    },
    # --- Cluster: deployment / config regressions ---
    {
        "title": "Checkout 500s after v2.4.1 deploy",
        "description": "checkout-service v2.4.1 returns HTTP 500 for ~30% of requests since the morning deploy. Rollback to v2.4.0 restores normal behavior, indicating a bad config template.",
        "logs": "checkout-service ERROR payment_db connection refused (postgres-primary:5432)\nSQLAlchemy OperationalError; pool exhausted (10/10 in use)",
        "system": "checkout", "severity": "critical",
        "resolution_text": "Corrected the DATABASE_HOST value in the v2.4.1 config template and re-deployed; error rate returned to 0.01%.",
    },
    {
        "title": "Feature flag default broke cart pricing",
        "description": "A default-on feature flag served the experimental pricing service to all carts; prices were off by one cent rounding and support volume spiked.",
        "logs": "pricing-svc v0: rounding mode 'bankers' vs legacy 'half-up'\nflag cart_pricing_v2 rollout=100% (intended 5%)",
        "system": "checkout", "severity": "medium",
        "resolution_text": "Reverted the flag default to 5% rollout and added a rollout-percentage diff check to the deploy pipeline to catch accidental 100% flips.",
    },
    {
        "title": "Bad migration locks orders table during deploy",
        "description": "Schema migration 0042 took an ACCESS EXCLUSIVE lock on the orders table for 6 minutes during the deploy window, stalling all order writes and timing out health checks.",
        "logs": "pg locks: ALTER TABLE orders waiting 6m12s\norder write latency p99: 29.4s",
        "system": "orders", "severity": "high",
        "resolution_text": "Rewrote the migration to use CREATE INDEX CONCURRENTLY with a lock_timeout and ran it in maintenance mode; future migrations run lock-free.",
    },
    # --- Cluster: disk / storage ---
    {
        "title": "Log volume fills disk on ingestion nodes",
        "description": "Ingestion nodes hit 98% disk usage because verbose DEBUG logging shipped to the wrong topic, filling the local log volume and stalling ingestion.",
        "logs": "df: /var/log 98% used (49/50GiB)\nkafka ingestion lag 1.4M messages and climbing",
        "system": "ingest", "severity": "high",
        "resolution_text": "Corrected the DEBUG log topic routing, rotated and pruned the filled volume, and set an 85% disk alert with an auto-cleanup job.",
    },
    {
        "title": "S3 upload latency spikes break media pipeline",
        "description": "Media uploads to S3 spike from 400ms to 25s during the backup window because nightly backup jobs saturate the same 10Gbps uplink.",
        "logs": "upload throughput 12MB/s vs baseline 800MB/s\nbackup job window overlaps 02:00-04:00 UTC",
        "system": "media", "severity": "medium",
        "resolution_text": "Moved backups to a dedicated VPC endpoint and QoS-capped backup bandwidth to 40%; upload latency back under 500ms.",
    },
    {
        "title": "Postgres WAL archive backlog growing on primary",
        "description": "WAL archive destination is at 95% capacity; the archiver fails and WAL segments accumulate on the primary, risking disk exhaustion within 36 hours.",
        "logs": "pg_archive: FAILED dest s3://pg-wal (SlowDown)\npg_wal dir 82GiB, growing 900MB/hr",
        "system": "database", "severity": "high",
        "resolution_text": "Enabled WAL compression and lifecycle-expired archive objects older than 14 days; the archiver caught up and pg_wal shrank to 4GiB.",
    },
]


def _request(method: str, path: str, body: dict | None = None):
    return urllib.request.Request(
        BASE + path,
        method=method,
        headers={"X-API-Key": KEY, "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )


def post_ticket(seed: dict, attempts: int = 5) -> tuple[int, dict]:
    """POST /tickets with 429/connection backoff — never hammers the free tier."""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(_request("POST", "/tickets", seed), timeout=90) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 and attempt < attempts:
                wait = REQUEST_DELAY * attempt
                print(f"    429 rate limited; backing off {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            print(f"    HTTP {e.code}: {body[:200]}", flush=True)
            raise
        except urllib.error.URLError as e:
            if attempt == attempts:
                raise
            print(f"    connection error ({e.reason}); retrying in {REQUEST_DELAY:.0f}s", flush=True)
            time.sleep(REQUEST_DELAY)


def patch_resolve(ticket_id: int, resolution_text: str) -> tuple[int, dict]:
    with urllib.request.urlopen(
        _request("PATCH", f"/tickets/{ticket_id}/resolve", {"resolution_text": resolution_text}),
        timeout=30,
    ) as resp:
        return resp.status, json.loads(resp.read())


def main() -> int:
    created, failed = [], []
    print(f"Seeding {len(SEEDS)} tickets to {BASE} (delay {REQUEST_DELAY}s)\n", flush=True)
    for i, seed in enumerate(SEEDS, 1):
        print(f"[{i}/{len(SEEDS)}] {seed['title']}", flush=True)
        try:
            status, ticket = post_ticket(seed)
            tid = ticket["id"]
            print(f"    POST {status} -> id={tid} rca={'ok' if ticket.get('root_cause') else 'NULL'}", flush=True)
            r_status, resolved = patch_resolve(tid, seed["resolution_text"])
            print(f"    PATCH resolve {r_status} resolved_at={resolved.get('resolved_at')}", flush=True)
            created.append(tid)
        except Exception as e:  # noqa: BLE001 - keep seeding, report failures at the end
            print(f"    FAILED: {e}", flush=True)
            failed.append(seed["title"])
        time.sleep(REQUEST_DELAY)

    print(f"\nDone. created={len(created)} ids={created}", flush=True)
    if failed:
        print(f"FAILED ({len(failed)}): {failed}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
