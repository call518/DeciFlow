"""Keep canonical input text once across storage, Actions, and JSON exports."""

import json
from typing import Any


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove redundant valid input copies while preserving malformed raw input."""
    item = dict(result)
    record = item.get("inputRecord")
    field = item.get("contentField")
    if (
        item.get("inputFormat") == "jsonl"
        and isinstance(record, dict)
        and isinstance(field, str)
        and field in record
        and record[field] == item.get("log")
    ):
        raw = item.get("rawInput")
        if isinstance(raw, str):
            try:
                if json.loads(raw) == record:
                    item.pop("rawInput")
            except (ValueError, TypeError):
                pass
        item["inputRecord"] = {
            key: value for key, value in record.items() if key != field
        }
        item["inputContentInLog"] = True
    if not item.get("error") and item.get("decisionDefinitions"):
        item.pop("questions", None)
    provider = item.get("providerResponse")
    if (
        not item.get("error")
        and isinstance(provider, dict)
        and isinstance(item.get("decisions"), dict)
        and provider.get("answers") == item["decisions"]
    ):
        item["providerResponse"] = {
            **{key: value for key, value in provider.items() if key != "answers"},
            "answersInDecisions": True,
        }
    if item != result and item.get("schemaVersion") == 1:
        item["schemaVersion"] = 2
    return item
