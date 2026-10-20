"""Validate explicit settings and expand each source's paths or patterns."""

from pathlib import Path
from typing import Any

from profiles import GENERAL_PROFILE_ID, validate_settings
from source_registry import input_settings, load_sources, source_paths
from sources import resolve_sources
from ssh_hosts import load_hosts


def parse_source_settings(
    values: object, *, allow_unassigned_profile: bool = False
) -> list[dict[str, Any]]:
    """Accept registered Sources or explicit paths with per-source settings."""
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
        profile = value.get("profile", GENERAL_PROFILE_ID)
        events = value.get("chunkEvents", 1)
        if allow_unassigned_profile and profile == "":
            if type(events) is not int or events < 1:
                raise ValueError("Chunk events must be a positive integer.")
        else:
            profile, events = validate_settings(profile, events)
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
        spec.update(input_settings(definition or value))
        if spec.get("format") == "jsonl":
            spec["chunkEvents"] = 1
        if definition.get("type") != "ssh":
            if value.get("hostIds"):
                raise ValueError("Only Remote File (SSH) Sources can select SSH Hosts.")
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
        if spec.get("type") in {"ssh", "hdfs", "webhdfs"}:
            continue
        for pattern in source_paths(spec["path"]):
            for path in resolve_sources(pattern, follow=follow):
                path = path.resolve()
                if path in result and (
                    result[path]["profile"],
                    result[path]["chunkEvents"],
                    result[path].get("actionId", ""),
                    result[path].get("format", "text"),
                    result[path].get("contentField"),
                ) != (
                    spec["profile"],
                    spec["chunkEvents"],
                    spec.get("actionId", ""),
                    spec.get("format", "text"),
                    spec.get("contentField"),
                ):
                    raise ValueError(
                        f"Conflicting profile, input format, content field, chunk size, "
                        f"or action for: {path}"
                    )
                if path not in result:
                    result[path] = {**spec, "sourcePatterns": [pattern]}
                elif pattern not in result[path]["sourcePatterns"]:
                    result[path]["sourcePatterns"].append(pattern)
    return result
