"""Consume a DeciFlow decision; replace the handler with your own integration."""

import json
import sys
from typing import Any


def handle_result(result: dict[str, Any]) -> None:
    """Apply user-defined behavior to one successful classification."""
    if result["category"] not in {"error", "security"}:
        return
    # Replace this with a notification, API call, or database write.
    print(f"{result['eventId']}: {result['category']} — {result['log']}")


if __name__ == "__main__":
    handle_result(json.load(sys.stdin))
