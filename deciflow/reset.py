"""Reset only the configured application data after execution has stopped."""

import os
import shutil
import sys
from pathlib import Path

from deciflow.config_store import get_data_directory, load_records, save_records
from deciflow.result_store import close_result_store


def reset_directory() -> Path:
    """Validate the dedicated data root before allowing a destructive reset."""
    root = get_data_directory()
    protected = {
        Path("/"),
        Path("/etc"),
        Path("/usr"),
        Path("/usr/local"),
        Path("/var"),
        Path("/var/lib"),
        Path("/tmp"),
        Path("/home"),
        Path("/opt"),
        Path.home(),
        Path.cwd().resolve(),
    }
    from deciflow.paths import RESOURCE_ROOT

    project = RESOURCE_ROOT
    resolved = root.resolve()
    if root.is_symlink() or resolved in protected or resolved == project:
        raise ValueError("Reset requires a dedicated application data directory.")
    if resolved in project.parents or resolved in Path.cwd().resolve().parents:
        raise ValueError("The data directory must not contain the application.")
    return root


def reset_data(root: Path) -> None:
    """Reset application data while preserving SSH key files and registration."""
    if root != reset_directory():
        raise ValueError("The data directory changed during reset.")
    close_result_store(root)
    keys = load_records("ssh_keys")
    for entry in root.iterdir():
        if entry.name == "ssh-keys":
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    if keys:
        save_records("ssh_keys", keys)


def restart_process() -> None:
    """Replace this process with its original Python invocation."""
    os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])
