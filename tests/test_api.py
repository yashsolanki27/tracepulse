"""Integration tests against a live tracepulse_test Postgres (pgvector).

RCA/embedding are monkeypatched so no Groq call and no sentence-transformers
model load happens. Requires the docker-compose `db` service running.
"""
import pytest

pytestmark = pytest.mark.integration

TICKET = {"title": "API outage", "description": "5xx spike on /checkout",
          "logs": "ERROR upstream timeout", "system": "payments"}


@pytest.fixture(autouse=True)
def _mock_ai(monkeypatch):
    # rca/embeddings functions are imported INTO the routers.tickets module
    # (`from rca import analyze_ticket`), so patch the bound names there.
    monkeypatch.setattr("routers.tickets.analyze_ticket", lambda *a: {
        "root_cause": "upstream 500", "evidence": "log line", "issue_area": "api",
        "suggested_resolution": "retry with backoff", "priority": "high",
        "severity": "major", "issue_type": "outage", "team": "platform",
    })
    monkeypatch.setattr("routers.tickets.embed_ticket", lambda *_: [0.1] * 384)


def test_create_requires_api_key(client):
    r = client.post("/tickets", json=TICKET, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_create_ticket_pipeline(client):
    r = client.post("/tickets", json=TICKET)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "open"
    assert body["priority"] == "high"
    assert body["root_cause"] == "upstream 500"
    assert body["target_resolution_time"] is not None  # SLA clock started


def test_create_rejects_blank_title(client):
    r = client.post("/tickets", json={**TICKET, "title": "   "})
    assert r.status_code == 422


def test_list_and_get(client):
    created = client.post("/tickets", json=TICKET).json()
    listed = client.get("/tickets").json()
    assert any(t["id"] == created["id"] for t in listed)
    detail = client.get(f"/tickets/{created['id']}").json()
    assert detail["similar_incidents"] == []


def test_get_missing_404(client):
    assert client.get("/tickets/99999").status_code == 404


def test_resolve_then_status_machine(client):
    t = client.post("/tickets", json=TICKET).json()
    r = client.patch(f"/tickets/{t['id']}/resolve",
                     json={"resolution_text": "rolled back deploy"})
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert client.patch(f"/tickets/{t['id']}/status",
                        json={"status": "open"}).status_code == 409
    assert client.patch(f"/tickets/{t['id']}/status",
                        json={"status": "in_progress"}).status_code == 200


def test_assign_flow(client, db_session):
    from models import Engineer
    eng = Engineer(name="Dana Ops", email="d@x.io", slack_handle="@d", active=True)
    db_session.add(eng)
    db_session.commit()
    t = client.post("/tickets", json=TICKET).json()
    r = client.patch(f"/tickets/{t['id']}/assign", json={"engineer_id": eng.id})
    assert r.status_code == 200 and r.json()["assigned_engineer_id"] == eng.id
    assert client.patch(f"/tickets/{t['id']}/assign",
                        json={"engineer_id": 99999}).status_code == 404
