"""Decision engine settings and verified model budgets."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

# https://docs.typesafe.ai/models (verified 2026-10-10).
JEV_MODEL = "jev-1.13.0"
JEV_CONTEXT_TOKENS = 32_000
JEV_REQUEST_TOKENS = 64_000
DEFAULT_JEV_INPUT_BYTES = 30_000
LAYA_MODEL = "multilingual"
LAYA_CONTEXT_TOKENS = 8192
LAYA_HEAD_TOKENS = 256


@dataclass(frozen=True)
class Engine:
    """Snapshot the provider settings for one classification stream."""

    name: str
    url: str
    api_key: str
    model: str
    timeout: int


def get_engine() -> Engine:
    """Select Laya by default; never fall back to a paid provider."""
    name = os.getenv("DECISION_ENGINE", "laya").strip().lower()
    if name == "jev":
        get_jev_input_bytes()
        return Engine(
            name,
            "https://api.typesafe.ai/v1/systemone",
            os.getenv("TYPESAFE_API_KEY", ""),
            JEV_MODEL,
            30,
        )
    if name != "laya":
        raise ValueError("DECISION_ENGINE must be laya or jev.")
    url = os.getenv("LAYA_API_URL", "http://127.0.0.1:8000/v1/systemone").strip()
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("LAYA_API_URL must be an HTTP(S) URL without credentials.")
    return Engine(name, url, os.getenv("LAYA_API_KEY", "changeme"), LAYA_MODEL, 120)


def get_jev_input_bytes() -> int:
    """Read a conservative byte budget, not an exact Jev token count."""
    key = "MAX_JEV_INPUT_BYTES"
    try:
        value = int(os.getenv(key, str(DEFAULT_JEV_INPUT_BYTES)))
    except ValueError as error:
        raise ValueError(f"{key} must be an integer from 1 to 30,000.") from error
    if not 1 <= value <= DEFAULT_JEV_INPUT_BYTES:
        raise ValueError(f"{key} must be an integer from 1 to 30,000.")
    return value
