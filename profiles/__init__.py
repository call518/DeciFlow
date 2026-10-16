"""Explicit, domain-specific decision profiles shared by both engines."""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from typing import Any

from config_store import load_records, save_records

DEFAULT_PROFILES = {
    path.stem: json.loads(path.read_text())
    for path in sorted(Path(__file__).parent.glob("*.json"))
}
PROFILES = deepcopy(DEFAULT_PROFILES)


ProfileMap = dict[str, dict[str, Any]]
PROFILE_SNAPSHOT: ContextVar[ProfileMap | None] = ContextVar(
    "profile_snapshot", default=None
)
CATEGORIES = ("normal", "warning", "error", "security", "other")


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
    """Validate editable profiles with the five fixed result categories."""
    if not isinstance(values, dict):
        raise TypeError("Criteria profiles must be an object keyed by profile ID.")
    validated: ProfileMap = {}
    names: set[str] = set()
    for identity, value in values.items():
        if not isinstance(identity, str) or not re.fullmatch(
            r"(?:[a-z][a-z0-9_-]{0,63}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})",
            identity,
        ):
            raise ValueError(
                "Profile IDs must be UUIDs or legacy lowercase identifiers."
            )
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
        criteria = value.get("criteria")
        if not isinstance(criteria, dict) or set(criteria) != set(CATEGORIES):
            raise ValueError(
                "Criteria must define Normal, Warning, Error, Security and Other."
            )
        if any(not isinstance(v, str) or not v.strip() for v in criteria.values()):
            raise ValueError("Every category needs a nonempty definition.")
        fields["criteria"] = {key: criteria[key].strip() for key in CATEGORIES}
        normalization = value.get("normalization")
        if normalization is not None:
            if normalization != "single_line_syslog_header":
                raise ValueError("Unsupported profile normalization.")
            fields["normalization"] = normalization
        validated[identity] = fields
    if "general" not in validated:
        raise ValueError("The general profile is required and cannot be deleted.")
    return validated


def load_profiles() -> None:
    """Load saved criteria, persisting current defaults on the first startup."""
    values = validate_profiles(load_records("criteria", DEFAULT_PROFILES))
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
