"""Persist application preferences in the shared SQLite database."""

from classifier import Result
from config_store import load_records, save_record


def load_settings() -> Result:
    """Read preferences, persisting the default page size on first access."""
    return load_records("settings", {"application": {"resultsPerPage": 30}})[
        "application"
    ]


def save_settings(value: object) -> Result:
    """Validate and commit supported page sizes."""
    if not isinstance(value, dict) or type(value.get("resultsPerPage")) is not int:
        raise ValueError("Select a valid Results per Page value.")
    if value["resultsPerPage"] not in {10, 30, 50, 100}:
        raise ValueError("Results per Page must be 10, 30, 50, or 100.")
    settings = {"resultsPerPage": value["resultsPerPage"]}
    save_record("settings", "application", settings)
    return settings
