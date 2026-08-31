"""Throwaway test: verify Groq openai/gpt-oss-120b returns the expected JSON shape.

Run: uv run python test_groq_call.py
"""

import json
import os

from openai import OpenAI


def load_env(path: str = ".env") -> None:
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


load_env()

SYSTEM_PROMPT = open("prompts/rca_v1.txt", encoding="utf-8").read()

SAMPLE_TICKET = """Title: Checkout API returning 500s after deployment
Description: Since this morning's deploy of checkout-service v2.4.1, roughly 30% of checkout requests return HTTP 500. Rollback of v2.4.0 restores normal behavior.
Logs:
2026-08-31T08:12:01Z checkout-service ERROR payment_db connection refused (postgres-primary:5432)
2026-08-31T08:12:01Z checkout-service ERROR SQLAlchemy OperationalError: could not connect to server: Connection refused
2026-08-31T08:12:02Z checkout-service WARN connection pool exhausted (10/10 in use)
2026-08-31T08:12:05Z checkout-service ERROR unhandled exception in POST /checkout: OperationalError
"""


def main() -> None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY not set")

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": SAMPLE_TICKET},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    raw = response.choices[0].message.content
    print("--- RAW RESPONSE ---")
    print(raw)
    print("--- PARSED ---")
    data = json.loads(raw)
    assert set(data.keys()) == {"root_cause", "evidence", "issue_area", "suggested_resolution"}, data.keys()
    for key in ("root_cause", "evidence", "issue_area", "suggested_resolution"):
        assert isinstance(data[key], str) and data[key].strip(), key
    print("OK: JSON shape correct, all 4 keys are non-empty strings")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
