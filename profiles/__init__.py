"""Explicit, domain-specific decision profiles shared by both engines."""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from typing import Any

from config_store import load_records, save_record, save_records
from decisions import review_options


def _load_templates() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    profiles = {}
    identities = {}
    for path in sorted(Path(__file__).parent.glob("*.json")):
        definition = json.loads(path.read_text())
        identity = definition.pop("id")
        if identity in profiles:
            raise ValueError("Sample Criteria IDs must be unique.")
        profiles[identity] = definition
        identities[path.stem] = identity
    return profiles, identities


DEFAULT_PROFILES, SAMPLE_PROFILE_IDS = _load_templates()
GENERAL_PROFILE_ID = SAMPLE_PROFILE_IDS["general"]
PROFILES = deepcopy(DEFAULT_PROFILES)


ProfileMap = dict[str, dict[str, Any]]
PROFILE_SNAPSHOT: ContextVar[ProfileMap | None] = ContextVar(
    "profile_snapshot", default=None
)


def get_profile(profile: str) -> dict[str, Any]:
    """Read the run's frozen criteria, or current criteria for direct calls."""
    return (PROFILE_SNAPSHOT.get() or PROFILES)[profile]


@contextmanager
def use_profile_snapshot(snapshot: ProfileMap) -> Iterator[None]:
    """Keep concurrent runs isolated from criteria edits."""
    token = PROFILE_SNAPSHOT.set(snapshot)
    try:
        yield
    finally:
        PROFILE_SNAPSHOT.reset(token)


def validate_profiles(values: object) -> ProfileMap:
    """Validate editable profiles and their typed decisions."""
    if not isinstance(values, dict):
        raise TypeError("Criteria profiles must be an object keyed by profile ID.")
    validated: ProfileMap = {}
    names: set[str] = set()
    for identity, value in values.items():
        if not isinstance(identity, str) or not re.fullmatch(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
            identity,
        ):
            raise ValueError("Criteria IDs must be canonical lowercase UUIDs.")
        if not isinstance(value, dict):
            raise TypeError(
                "Each profile must contain a name, instructions and criteria."
            )
        fields = {}
        for key in ("label", "instructions"):
            text = value.get(key)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Enter a nonempty {key} for {identity}.")
            fields[key] = text.strip()
        name = fields["label"].casefold()
        if name in names:
            raise ValueError("Criteria names must be unique.")
        names.add(name)
        fields.update(_validate_questions(value))
        normalization = value.get("normalization")
        if normalization is not None:
            if normalization != "single_line_syslog_header":
                raise ValueError("Unsupported profile normalization.")
            fields["normalization"] = normalization
        validated[identity] = fields
    return validated


def _validate_questions(profile: dict[str, Any]) -> dict[str, Any]:
    questions = profile.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("Add at least one decision.")
    cleaned = {}
    for identity, definition in questions.items():
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", identity)
            or not isinstance(definition, dict)
        ):
            raise ValueError("Decision IDs must be unique lowercase identifiers.")
        kind = definition.get("type")
        if kind not in {"choice", "score", "noul"}:
            raise ValueError("Select Choice, Score or Noul.")
        item = {"type": kind}
        for key in ("label", "instructions"):
            text = definition.get(key)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Enter a nonempty decision {key}.")
            item[key] = text.strip()
        criteria = definition.get("criteria")
        if kind == "choice":
            if (
                not isinstance(criteria, dict)
                or not 2 <= len(criteria) <= 255
                or any(
                    not isinstance(k, str) or not k.strip() or k in {"all", "failed"}
                    for k in criteria
                )
            ):
                raise ValueError(
                    "Choice requires 2–255 named options; all/failed are reserved."
                )
            options = review_options(definition)
            if (
                not isinstance(options, list)
                or any(
                    not isinstance(key, str) or key not in criteria for key in options
                )
                or len(set(options)) != len(options)
            ):
                raise ValueError("Review options must be unique Choice option IDs.")
            item["reviewOptions"] = options
        elif kind == "score" and (
            not isinstance(criteria, list) or not 2 <= len(criteria) <= 10
        ):
            raise ValueError("Score requires 2–10 ordered levels.")
        if kind != "noul":
            assert isinstance(criteria, (dict, list))
            texts = criteria.values() if isinstance(criteria, dict) else criteria
            if any(not isinstance(v, str) or not v.strip() for v in texts):
                raise ValueError("Every option or level needs a nonempty definition.")
            item["criteria"] = deepcopy(criteria)
        cleaned[identity] = item
    default = profile.get("defaultDecision")
    if not isinstance(default, str) or default not in cleaned:
        raise ValueError("Select exactly one existing default chart decision.")
    return {"questions": cleaned, "defaultDecision": default}


def load_profiles() -> None:
    """Load saved criteria and ensure the required consultation samples exist."""
    stored = load_records("criteria", DEFAULT_PROFILES)
    values = validate_profiles(stored)
    for name in ("consultation", "central_gov", "local_gov"):
        identity = SAMPLE_PROFILE_IDS[name]
        sample = DEFAULT_PROFILES[identity]
        if identity not in values and not any(
            profile["label"].casefold() == sample["label"].casefold()
            for profile in values.values()
        ):
            save_record("criteria", identity, sample)
            values[identity] = deepcopy(sample)
    PROFILES.clear()
    PROFILES.update(values)


def save_profiles(values: object) -> ProfileMap:
    """Atomically persist validated profiles before publishing the new settings."""
    profiles = validate_profiles(values)
    save_records("criteria", profiles)
    PROFILES.clear()
    PROFILES.update(profiles)
    return deepcopy(PROFILES)


def validate_settings(profile: object, chunk_events: object) -> tuple[str, int]:
    """Validate a profile and its positive event-count chunk size."""
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("Select a supported decision profile.")
    if type(chunk_events) is not int or chunk_events < 1:
        raise ValueError("Chunk events must be a positive integer.")
    return profile, chunk_events
