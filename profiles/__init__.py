"""Explicit, domain-specific decision profiles shared by both engines."""

import json
from pathlib import Path

PROFILES = {
    path.stem: json.loads(path.read_text())
    for path in sorted(Path(__file__).parent.glob("*.json"))
}


def validate_settings(profile: object, chunk_lines: object) -> tuple[str, int]:
    """Validate a profile and its positive nonempty-line chunk size."""
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("Select a supported decision profile.")
    if type(chunk_lines) is not int or chunk_lines < 1:
        raise ValueError("Chunk lines must be a positive integer.")
    return profile, chunk_lines
