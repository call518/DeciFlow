"""Validate explicit settings and expand each source's paths or patterns."""

from pathlib import Path
from typing import Any

from profiles import validate_settings
from sources import resolve_sources


def parse_source_settings(values: object) -> list[dict[str, Any]]:
    """Accept configured sources or preserve legacy path inputs with defaults."""
    if isinstance(values, str):
        values = [line.strip() for line in values.splitlines() if line.strip()]
    if not isinstance(values, list) or not values:
        raise ValueError("Enter at least one source path or pattern.")
    sources = []
    for value in values:
        if isinstance(value, str):
            value = {"path": value}
        if not isinstance(value, dict):
            raise TypeError(
                "Each source must specify a path, profile, and chunk lines."
            )
        path = value.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Enter a source path or pattern.")
        profile, lines = validate_settings(
            value.get("profile", "general"), value.get("chunkLines", 1)
        )
        sources.append({"path": path.strip(), "profile": profile, "chunkLines": lines})
    return sources


def resolve_configured_sources(
    specs: list[dict[str, Any]], *, follow: bool = False
) -> dict[Path, dict[str, Any]]:
    """Deduplicate files; reject overlapping patterns with conflicting settings."""
    result: dict[Path, dict[str, Any]] = {}
    for spec in specs:
        for path in resolve_sources(spec["path"], follow=follow):
            path = path.resolve()
            if path in result and (
                result[path]["profile"],
                result[path]["chunkLines"],
            ) != (spec["profile"], spec["chunkLines"]):
                raise ValueError(f"Conflicting profile or chunk size for: {path}")
            if path not in result:
                result[path] = {**spec, "sourcePatterns": [spec["path"]]}
            elif spec["path"] not in result[path]["sourcePatterns"]:
                result[path]["sourcePatterns"].append(spec["path"])
    return result
