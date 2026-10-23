"""Locate immutable application resources in a checkout or installed wheel."""

from pathlib import Path

RESOURCE_ROOT = Path(__file__).resolve().parent
if not (RESOURCE_ROOT / "public").is_dir():
    RESOURCE_ROOT = RESOURCE_ROOT.parent
