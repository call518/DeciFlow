"""Start DeciFlow from a Git checkout."""

from deciflow.server import main

if __name__ == "__main__":
    try:
        main(manage_proxy=True)
    except (ValueError, OSError, RuntimeError) as error:
        raise SystemExit(f"DeciFlow stopped: {error}") from None
