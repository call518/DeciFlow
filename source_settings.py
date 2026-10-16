"""Validate explicit settings and expand each source's paths or patterns."""

from pathlib import Path
from typing import Any

from profiles import validate_settings
from source_registry import load_sources, source_paths
from sources import resolve_sources
from ssh_hosts import load_hosts


def parse_source_settings(values: object) -> list[dict[str, Any]]:
    """Accept configured sources or preserve legacy path inputs with defaults."""
    if isinstance(values, str):
        values = [line.strip() for line in values.splitlines() if line.strip()]
    if not isinstance(values, list) or not values:
        raise ValueError("Enter at least one source path or pattern.")
    sources = []
    hosts = {host["id"]: host for host in load_hosts()}
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
        if value.get("action"):
            raise ValueError("Select the Action again using its UUID.")
        action = value.get("actionId", "")
        if not isinstance(action, str):
            raise TypeError("Action must be a registered Action UUID.")
        spec = {
            **definition,
            "path": path.strip(),
            "profile": profile,
            "chunkEvents": events,
            **({"actionId": action.strip()} if action.strip() else {}),
        }
        if definition.get("type") != "ssh":
            if value.get("hostIds"):
                raise ValueError("Local File Sources cannot select SSH Hosts.")
            sources.append(spec)
            continue
        host_ids = value.get("hostIds")
        if (
            not isinstance(host_ids, list)
            or not host_ids
            or any(
                not isinstance(identity, str) or identity not in hosts
                for identity in host_ids
            )
            or len(set(host_ids)) != len(host_ids)
        ):
            raise ValueError(
                "Select one or more distinct SSH Hosts for each Remote File Source."
            )
        for identity in host_ids:
            host = hosts[identity]
            sources.append(
                {
                    **spec,
                    "hostId": identity,
                    "hostName": host["name"],
                    "host": host["host"],
                    "port": host["port"],
                    "username": host["username"],
                    "keyId": host["keyId"],
                    "keyPath": host["keyPath"],
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
        for pattern in source_paths(spec["path"]):
            for path in resolve_sources(pattern, follow=follow):
                path = path.resolve()
                if path in result and (
                    result[path]["profile"],
                    result[path]["chunkEvents"],
                    result[path].get("actionId", ""),
                ) != (spec["profile"], spec["chunkEvents"], spec.get("actionId", "")):
                    raise ValueError(
                        f"Conflicting profile, chunk size, or action for: {path}"
                    )
                if path not in result:
                    result[path] = {**spec, "sourcePatterns": [pattern]}
                elif pattern not in result[path]["sourcePatterns"]:
                    result[path]["sourcePatterns"].append(pattern)
    return result
