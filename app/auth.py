import os

from fastapi import Header, HTTPException


def verify_api_key(x_api_key: str | None = Header(None)) -> None:
    expected = os.getenv("TRACEPULSE_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="API key not configured")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
