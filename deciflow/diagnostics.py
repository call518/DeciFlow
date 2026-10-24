"""Record operational failures without exception values or source contents."""

import logging
import os
import sqlite3
import traceback
from pathlib import Path


def log_failure(operation: str, error: BaseException) -> None:
    """Log a code location, error category, and safe system error description."""
    error = error.__cause__ or error
    reason = type(error).__name__
    if isinstance(error, OSError) and error.errno is not None:
        reason += f" (errno={error.errno}: {os.strerror(error.errno)})"
    if isinstance(error, sqlite3.Error) and hasattr(error, "sqlite_errorcode"):
        reason += f" (sqlite_errorcode={error.sqlite_errorcode})"
    frames = traceback.extract_tb(error.__traceback__)
    location = " -> ".join(
        f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"
        for frame in frames
    )
    # Do not log exception messages, local variables, or source lines.
    logging.getLogger("uvicorn.error").error(
        "%s failed: %s; location=%s", operation, reason, location or "unavailable"
    )
