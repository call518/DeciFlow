"""Decision engine settings and verified model budgets."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values, load_dotenv

from deciflow.runtime_config import effective_values

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
    concurrency: int = 4
    runtime: Mapping[str, str] | None = field(default=None, repr=False)

    def _value(self, key: str, default: str) -> str:
        return (
            self.runtime.get(key, default)
            if self.runtime is not None
            else os.getenv(key, default)
        )

    @property
    def input_bytes(self) -> int:
        """Return the frozen Jev request byte budget."""
        return get_jev_input_bytes(self.runtime)

    @property
    def context_tokens(self) -> int:
        """Return the conservative request window for the selected model."""
        if self.name == "jev":
            return JEV_CONTEXT_TOKENS
        raw = self._value("LAYA_MAX_TOKENS", "").strip()
        built_in = self.model in {"english", "multilingual", "typed-decisions"}
        if not raw:
            if not built_in:
                raise ValueError("Custom LAYA_MODEL requires explicit LAYA_MAX_TOKENS.")
            return 512 if self.model == "english" else LAYA_CONTEXT_TOKENS
        maximum = 512 if self.model == "english" else LAYA_CONTEXT_TOKENS
        try:
            value = int(raw)
        except ValueError as error:
            raise ValueError("LAYA_MAX_TOKENS must be a positive integer.") from error
        if not 1 <= value <= maximum:
            raise ValueError(f"LAYA_MAX_TOKENS must be between 1 and {maximum}.")
        return value

    @property
    def head_tokens(self) -> int:
        """Return the selected Laya model's question budget."""
        try:
            value = int(self._value("LAYA_HEAD_TOKENS", str(LAYA_HEAD_TOKENS)))
        except ValueError as error:
            raise ValueError("LAYA_HEAD_TOKENS must be a positive integer.") from error
        if not 0 < value < self.context_tokens:
            raise ValueError(
                f"LAYA_HEAD_TOKENS must be between 1 and {self.context_tokens - 1} "
                f"for {self.model}."
            )
        return value


def load_startup_settings(path: Path) -> None:
    """Reload explicit engine settings from .env when the UI process starts."""
    load_dotenv(path)
    # Compose retains env_file values across Restart; the mounted file is current.
    for key, value in dotenv_values(path).items():
        if value is not None and (
            key == "DECISION_ENGINE" or key.startswith(("LAYA_", "JEV_", "OPENAI_"))
        ):
            os.environ[key] = value


def get_engine(values: Mapping[str, str] | None = None) -> Engine:
    """Select Laya by default; never fall back to a paid provider."""
    values = dict(effective_values() if values is None else values)
    name = values.get("DECISION_ENGINE", "laya").strip().lower()
    if name == "jev":
        get_jev_input_bytes(values)
        return Engine(
            name,
            "https://api.typesafe.ai/v1/systemone",
            os.getenv("JEV_API_KEY", ""),
            get_model(name, values),
            30,
            get_concurrency(name, values),
            values,
        )
    if name != "laya":
        raise ValueError("DECISION_ENGINE must be laya or jev.")
    url = values.get("LAYA_API_URL", "http://127.0.0.1:8000/v1/systemone").strip()
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
    engine = Engine(
        name,
        url,
        os.getenv("LAYA_API_KEY", "changeme"),
        get_model(name, values),
        120,
        get_concurrency(name, values),
        values,
    )
    _ = engine.head_tokens  # Validate before accepting a classification run.
    return engine


def get_model(engine: str, values: Mapping[str, str] | None = None) -> str:
    """Read the selected provider's model without changing providers on failure."""
    key = f"{engine.upper()}_MODEL"
    values = os.environ if values is None else values
    model = values.get(key, LAYA_MODEL if engine == "laya" else JEV_MODEL).strip()
    if not model:
        raise ValueError(f"{key} must not be empty.")
    if engine == "laya" and not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", model):
        raise ValueError(f"{key} must be a built-in or registered model name.")
    return model


def get_jev_input_bytes(values: Mapping[str, str] | None = None) -> int:
    """Read a conservative byte budget, not an exact Jev token count."""
    values = effective_values() if values is None else values
    key = "JEV_MAX_INPUT_BYTES"
    try:
        value = int(values.get(key, str(DEFAULT_JEV_INPUT_BYTES)))
    except ValueError as error:
        raise ValueError(f"{key} must be an integer from 1 to 30,000.") from error
    if not 1 <= value <= DEFAULT_JEV_INPUT_BYTES:
        raise ValueError(f"{key} must be an integer from 1 to 30,000.")
    return value


def get_concurrency(engine: str, values: Mapping[str, str] | None = None) -> int:
    """Read the selected engine's positive simultaneous request limit."""
    values = effective_values() if values is None else values
    key = f"{engine.upper()}_CONCURRENCY"
    try:
        value = int(values.get(key, "4"))
    except ValueError as error:
        raise ValueError(f"{key} must be a positive integer.") from error
    if value < 1:
        raise ValueError(f"{key} must be a positive integer.")
    return value
