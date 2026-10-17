"""Explicit, domain-specific decision profiles shared by both engines."""

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from typing import Any

from config_store import load_records, save_record, save_records

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
        if "questions" in value:
            fields.update(_validate_questions(value))
        else:
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


def _validate_questions(profile: dict[str, Any]) -> dict[str, Any]:
    questions = profile["questions"]
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
        summary = definition.get("summary", True)
        if not isinstance(summary, bool):
            raise TypeError("Summary must be a boolean.")
        item["summary"] = summary
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
    primary = profile.get("primaryQuestion")
    if primary not in cleaned or cleaned[primary]["type"] != "choice":
        raise ValueError("Select a Choice decision for the primary classification.")
    return {"questions": cleaned, "primaryQuestion": primary}


def load_profiles() -> None:
    """Load saved criteria and ensure the required consultation samples exist."""
    values = validate_profiles(load_records("criteria", DEFAULT_PROFILES))
    # Update only untouched samples, preserving saved Task IDs and user edits.
    legacy_hashes = {
        "eaaeb8160dec0b9b1e1ba1406087995f46126008936fbf8753fb926fd1ea2366",
        "5cdb1ea0a7e66c3d541df8248989898612c3616dbe395579d9fdecf47a253a23",
        "c4ca8223b173892bc9f1b24a4a5daf754d0b9086b6280506b6a35f009041c58a",
        "139d8de41dc425a8339bf9707dd5747a9f87c76398db743496ba1db74d00910f",
    }
    for identity in ("consultation", "consultation_eng"):
        sample = DEFAULT_PROFILES[identity]
        saved = values.get(identity)
        name_exists = any(
            key != identity
            and profile["label"].casefold() == sample["label"].casefold()
            for key, profile in values.items()
        )
        untouched = (
            identity == "consultation"
            and saved is not None
            and hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()
            in legacy_hashes
        )
        if not name_exists and (saved is None or untouched):
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
