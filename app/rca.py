import json
import logging
import os

from openai import OpenAI, OpenAIError

logger = logging.getLogger("tracepulse.rca")

MODEL = "openai/gpt-oss-120b"
TIMEOUT_SECONDS = 10
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "rca_v1.txt")

RCA_KEYS = ("root_cause", "evidence", "issue_area", "suggested_resolution")


def _system_prompt() -> str:
    with open(PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("GROQ_API_KEY", ""),
        base_url="https://api.groq.com/openai/v1",
        timeout=TIMEOUT_SECONDS,
    )


def analyze_ticket(title: str, description: str, logs: str) -> dict | None:
    """Run RCA via Groq gpt-oss-120b. 10s timeout, one retry, returns None on failure."""
    ticket_text = f"Title: {title}\nDescription: {description}\nLogs:\n{logs}"
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": ticket_text},
    ]
    for attempt in (1, 2):
        try:
            response = _client().chat.completions.create(
                model=MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            data = json.loads(response.choices[0].message.content)
            if all(isinstance(data.get(k), str) and data[k].strip() for k in RCA_KEYS):
                return {k: data[k] for k in RCA_KEYS}
            logger.warning("RCA attempt %d: unexpected JSON shape, keys=%s", attempt, sorted(data))
        except (json.JSONDecodeError, KeyError, OpenAIError, TimeoutError) as exc:
            logger.warning("RCA attempt %d failed: %s", attempt, exc)
    logger.error("RCA failed after retry; returning null RCA fields")
    return None