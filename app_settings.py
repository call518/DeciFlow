"""Persist small application preferences independently of result history."""

import json
import os
from pathlib import Path
from threading import Lock

from classifier import Result

_SAVE_LOCK = Lock()


def settings_path() -> Path:
    """Return the shared application preferences path."""
    root = os.getenv("DECIFLOW_DATA_DIR", "").strip() or "/var/lib/deciflow-data"
    return Path(root).expanduser().absolute() / "settings.json"


def load_settings() -> Result:
    """Read preferences, defaulting to 50 results per page."""
    path = settings_path()
    return json.loads(path.read_text()) if path.exists() else {"resultsPerPage": 50}


def save_settings(value: object) -> Result:
    """Validate and atomically save supported page sizes."""
    if not isinstance(value, dict) or type(value.get("resultsPerPage")) is not int:
        raise ValueError("Select a valid Results per Page value.")
    if value["resultsPerPage"] not in {10, 30, 50, 100}:
        raise ValueError("Results per Page must be 10, 30, 50, or 100.")
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _SAVE_LOCK:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"resultsPerPage": value["resultsPerPage"]}) + "\n"
        )
        temporary.replace(path)
    return load_settings()
