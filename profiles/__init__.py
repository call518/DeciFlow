"""Explicit, domain-specific decision profiles shared by both engines."""

import json
from pathlib import Path

PROFILES = {
    path.stem: json.loads(path.read_text())
    for path in sorted(Path(__file__).parent.glob("*.json"))
}


def validate_settings(profile: object, chunk_events: object) -> tuple[str, int]:
    """Validate a profile and its positive event-count chunk size."""
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("Select a supported decision profile.")
    if type(chunk_events) is not int or chunk_events < 1:
        raise ValueError("Chunk events must be a positive integer.")
    return profile, chunk_events
