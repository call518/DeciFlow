"""Locate application resources and select the runtime environment file."""

import os
from pathlib import Path


def default_config_directory() -> Path:
    """Locate the user's configuration independently of the working directory."""
    return Path.home() / ".config" / "deciflow"


def resolve_env_path() -> Path:
    """Select one environment file; an explicit missing path is an error."""
    explicit = os.getenv("DECIFLOW_ENV_PATH", "")
    if not explicit:
        raise ValueError(
            "Set DECIFLOW_ENV_PATH to your configuration file, for example: "
            'export DECIFLOW_ENV_PATH="$HOME/.config/deciflow/.env"'
        )
    path = Path(explicit).expanduser().absolute()
    if not path.is_file():
        raise ValueError(
            f"Configuration file not found: {path}. Run deciflow init or correct DECIFLOW_ENV_PATH."
        )
    return path


RESOURCE_ROOT = Path(__file__).resolve().parent
if not (RESOURCE_ROOT / "public").is_dir():
    RESOURCE_ROOT = RESOURCE_ROOT.parent
