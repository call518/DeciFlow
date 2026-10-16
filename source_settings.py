"""Validate explicit settings and expand each source's paths or patterns."""

from pathlib import Path
from typing import Any

from profiles import validate_settings
from source_registry import load_sources
from sources import resolve_sources


def parse_source_settings(values: object) -> list[dict[str, Any]]:
    """Accept configured sources or preserve legacy path inputs with defaults."""
    if isinstance(values, str):
        values = [line.strip() for line in values.splitlines() if line.strip()]
    if not isinstance(values, list) or not values:
        raise ValueError("Enter at least one source path or pattern.")
    sources = []
    registered = {source["id"]: source for source in load_sources()}
    for value in values:
        if isinstance(value, str):
            value = {"path": value}
        if not isinstance(value, dict):
            raise TypeError(
                "Each source must specify a path, profile, and chunk events."
            )
        definition = {}
        if "sourceId" in value:
            identity = value["sourceId"]
            if not isinstance(identity, str) or identity not in registered:
                raise ValueError(
                    "Select a registered source. Refresh Sources if it was deleted."
                )
            definition = {**registered[identity], "sourceId": identity}
        path = definition.get("path", value.get("path"))
        if not isinstance(path, str) or not path.strip():
            raise ValueError("Enter a source path or pattern.")
        profile, events = validate_settings(
            value.get("profile", "general"),
            value.get("chunkEvents", value.get("chunkLines", 1)),
        )
        action = value.get("action", "")
        if not isinstance(action, str):
            raise TypeError("Action must be a registered action name.")
        sources.append(
            {
                **definition,
                "path": path.strip(),
                "profile": profile,
                "chunkEvents": events,
                **({"action": action.strip()} if action.strip() else {}),
            }
        )
    return sources


def resolve_configured_sources(
    specs: list[dict[str, Any]], *, follow: bool = False
) -> dict[Path, dict[str, Any]]:
    """Deduplicate files; reject overlapping patterns with conflicting settings."""
    result: dict[Path, dict[str, Any]] = {}
    for spec in specs:
        if spec.get("type") == "ssh":
            continue
        for path in resolve_sources(spec["path"], follow=follow):
            path = path.resolve()
            if path in result and (
                result[path]["profile"],
                result[path]["chunkEvents"],
                result[path].get("action", ""),
            ) != (spec["profile"], spec["chunkEvents"], spec.get("action", "")):
                raise ValueError(
                    f"Conflicting profile, chunk size, or action for: {path}"
                )
            if path not in result:
                result[path] = {**spec, "sourcePatterns": [spec["path"]]}
            elif spec["path"] not in result[path]["sourcePatterns"]:
                result[path]["sourcePatterns"].append(spec["path"])
    return result
