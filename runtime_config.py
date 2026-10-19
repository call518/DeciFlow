"""Describe non-secret runtime overrides and their environment fallbacks."""

import os
import re
from pathlib import Path
from typing import Any

from config_store import load_records

FIELDS: dict[str, tuple[str, str, str, list[str] | None, str]] = {
    "DECISION_ENGINE": (
        "Decision Engine",
        "Engine",
        "laya",
        ["laya", "jev"],
        "Select the engine for new runs. Jev usage incurs charges. No automatic fallback.",
    ),
    "LAYA_API_URL": (
        "API URL",
        "Laya",
        "http://127.0.0.1:8000/v1/systemone",
        None,
        "Full decision URL, including /v1/systemone. This selects a server; it does not start or configure it.",
    ),
    "LAYA_MODEL": (
        "Model",
        "Laya",
        "multilingual",
        None,
        "Built-ins: english, multilingual, typed-decisions. Custom names must already be registered on the Laya server.",
    ),
    "LAYA_MAX_TOKENS": (
        "Total Token Budget",
        "Laya",
        "",
        None,
        "Blank selects the built-in model window automatically: English 512, others 8192. Custom models require an explicit verified budget.",
    ),
    "LAYA_HEAD_TOKENS": (
        "Question Token Budget",
        "Laya",
        "256",
        None,
        "Positive and below the total budget. Remote server limits also apply. Larger questions leave less room for input.",
    ),
    "LAYA_CONCURRENCY": (
        "Concurrent Requests",
        "Laya",
        "4",
        None,
        "Positive simultaneous requests per run, shared across its Hosts. This does not change server workers or GPU parallelism.",
    ),
    "JEV_MODEL": (
        "Model",
        "Jev",
        "jev-1.13.0",
        None,
        "Use a pinned version for repeatable evaluation. jev-latest and jev-preview aliases can change. Availability depends on the account.",
    ),
    "JEV_MAX_INPUT_BYTES": (
        "Request Byte Budget",
        "Jev",
        "30000",
        None,
        "1–30000 UTF-8 JSON bytes including questions. This is a conservative byte guard, not a token allocation. Oversized events are retained for review.",
    ),
    "JEV_CONCURRENCY": (
        "Concurrent Requests",
        "Jev",
        "4",
        None,
        "Positive simultaneous requests per run. Other Tasks have independent limits.",
    ),
    "OPENAI_CRITERIA_MODEL": (
        "Criteria Authoring Model",
        "AI Assistance",
        "gpt-5.6-terra",
        None,
        "Used only by Generate With AI. Requires Responses API Structured Outputs and model access. Generation incurs charges; review the generated draft before saving.",
    ),
}


def load_overrides() -> dict[str, str]:
    """Read saved overrides without exposing credentials."""
    records = load_records("settings", {"application": {"resultsPerPage": 30}})
    return records.get("application", {}).get("runtimeOverrides", {})


def effective_values(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Resolve UI overrides, environment values, then built-in defaults."""
    saved = load_overrides() if overrides is None else overrides
    return {
        key: saved.get(key, os.getenv(key, str(field[2])))
        for key, field in FIELDS.items()
    }


def configuration_description() -> dict[str, Any]:
    """Return editable fields and safe environment-only information."""
    overrides = load_overrides()
    values = effective_values(overrides)
    references: dict[str, str] = {}
    comments: list[str] = []
    for line in (Path(__file__).parent / ".env.example").read_text().splitlines():
        if line.startswith("#"):
            text = line.lstrip("# ")
            if text and not re.search(r"[가-힣]", text):
                comments.append(text)
        elif "=" in line:
            references[line.split("=", 1)[0]] = "\n".join(comments)
            comments = []
        else:
            comments = []
    fields = []
    for key, (label, group, default, options, help_text) in FIELDS.items():
        fields.append(
            {
                "key": key,
                "label": label,
                "group": group,
                "options": options,
                "help": help_text,
                "reference": references.get(key, ""),
                "value": values[key],
                "fallback": os.getenv(key, str(default)),
                "source": "UI Override"
                if key in overrides
                else "Environment"
                if key in os.environ
                else "Default",
            }
        )
    environment = []
    for key in [
        "PORT",
        "DECIFLOW_DATA_DIR",
        "DECIFLOW_LOG_DIR",
        "DECIFLOW_CSRF_TRUSTED_ORIGINS",
        "COMPOSE_PROFILES",
    ]:
        environment.append(
            {
                "key": key,
                "help": references.get(key, ""),
                "value": os.getenv(key, "Not Set"),
                "application": "Container Recreation / Process Restart",
            }
        )
    return {
        "fields": fields,
        "overrides": overrides,
        "environment": environment,
        "credentialReferences": {
            key: references.get(key, "")
            for key in ["LAYA_API_KEY", "JEV_API_KEY", "OPENAI_API_KEY"]
        },
        "credentials": {
            key: bool(os.getenv(key, "").strip())
            for key in ["LAYA_API_KEY", "JEV_API_KEY", "OPENAI_API_KEY"]
        },
    }


def validate_overrides(value: object) -> dict[str, str]:
    """Validate all effective settings before one atomic preference save."""
    from config import get_engine

    if not isinstance(value, dict) or set(value) - FIELDS.keys():
        raise ValueError("Provide only supported runtime settings.")
    if any(not isinstance(item, str) or len(item) > 2000 for item in value.values()):
        raise ValueError(
            "Runtime settings must be strings of at most 2,000 characters."
        )
    overrides = {key: item.strip() for key, item in value.items()}
    values = effective_values(overrides)
    selected = get_engine(values)
    for name in ("laya", "jev"):
        get_engine({**values, "DECISION_ENGINE": name})
    if selected.name == "jev" and not selected.api_key:
        raise ValueError("Configure JEV_API_KEY in .env before selecting Jev.")
    if not values["OPENAI_CRITERIA_MODEL"] or any(
        char.isspace() for char in values["OPENAI_CRITERIA_MODEL"]
    ):
        raise ValueError("OPENAI_CRITERIA_MODEL must be a nonempty model identifier.")
    return overrides
