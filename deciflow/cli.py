"""Start an installed DeciFlow application with a writable user workspace."""

import argparse
import os
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from deciflow.paths import RESOURCE_ROOT, default_config_directory, resolve_env_path

GUIDE = "https://github.com/call518/DeciFlow/blob/main/INSTALL.md"


def prepare_workspace(directory: Path) -> bool:
    """Create missing templates without replacing user configuration or secrets."""
    directory.mkdir(parents=True, exist_ok=True)
    proxy = directory / "oauth2-proxy"
    proxy.mkdir(exist_ok=True)
    for name in ("oauth2-proxy.cfg", "allowed-emails.example.txt"):
        target = proxy / name
        if not target.exists():
            shutil.copyfile(RESOURCE_ROOT / "oauth2-proxy" / name, target)
    env = directory / ".env"
    if env.exists():
        return False
    text = (RESOURCE_ROOT / ".env.example").read_text()
    with env.open("x", encoding="utf-8") as output:
        env.chmod(0o600)
        output.write(text)
    return True


def storage_directories() -> list[tuple[str, Path]]:
    """Resolve storage using the application's shared defaults."""
    from deciflow.config_store import get_data_directory
    from deciflow.server import DEFAULT_LOG_DIR

    directories = [("DECIFLOW_DATA_DIR", get_data_directory())]
    logs = os.getenv("DECIFLOW_LOG_DIR", DEFAULT_LOG_DIR).strip()
    if logs:
        directories.append(("DECIFLOW_LOG_DIR", Path(logs).absolute()))
    return directories


def check_storage_directory(key: str, path: Path) -> None:
    """Check one directory without creating it or selecting an alternate path."""
    if not path.is_dir():
        raise ValueError(
            f"{key} directory does not exist or is not a directory: {path}"
        )
    try:
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as error:
        raise ValueError(f"Cannot write to {key} directory: {path}") from error


def main() -> None:
    """Run the CLI while keeping the caller's file selector unchanged."""
    previous = os.getenv("DECIFLOW_ENV_PATH")
    try:
        _main()
    finally:
        if previous is None:
            os.environ.pop("DECIFLOW_ENV_PATH", None)
        else:
            os.environ["DECIFLOW_ENV_PATH"] = previous


def _main() -> None:
    """Initialize or inspect configuration, or validate and start DeciFlow."""
    parser = argparse.ArgumentParser(
        description="Start DeciFlow using DECIFLOW_ENV_PATH."
    )
    parser.add_argument("--version", action="version", version=version("deciflow"))
    commands = parser.add_subparsers(dest="command")
    start = commands.add_parser("start", help="validate and start DeciFlow")
    start.add_argument(
        "--daemon", action="store_true", help="start detached with file logging"
    )
    commands.add_parser("status", help="show this installation's process status")
    commands.add_parser("stop", help="stop this installation gracefully")
    commands.add_parser("init", help="create configuration templates")
    config = commands.add_parser("config", help="inspect configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("test", help="check startup prerequisites")
    config_commands.add_parser(
        "list", help="list effective settings with secrets redacted"
    )
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    check_command = "deciflow config test"
    try:
        if args.command == "init":
            directory = default_config_directory()
            created = prepare_workspace(directory)
            print(
                f"{'Created' if created else 'Preserved'} {directory / '.env'}. "
                "Edit the configuration, then register this in your shell startup file:\n"
                'export DECIFLOW_ENV_PATH="$HOME/.config/deciflow/.env"\n'
                f"Then run: {check_command}"
            )
            return
        selected = resolve_env_path()
        os.environ["DECIFLOW_ENV_PATH"] = str(selected)
        directory = selected.parent
        if args.command in {"status", "stop"}:
            from deciflow import process_control

            if os.name != "posix":
                raise ValueError(
                    "CLI process management requires Linux, WSL2, or macOS"
                )
            if args.command == "status":
                raise SystemExit(process_control.status(directory))
            process_control.stop(directory)
            return
        from deciflow.cli_config import list_configuration, run_config_test

        if args.command == "config" and args.config_command == "list":
            list_configuration(directory)
            return
        if args.command == "config":
            raise SystemExit(run_config_test(directory))
        from deciflow.process_control import DAEMON_ENV, RunLock, Runtime, launch_daemon

        with RunLock(directory) as lock:
            result = run_config_test(directory, detailed=False)
            if result:
                print(f"Run: {check_command}", file=sys.stderr)
                raise SystemExit(result)
            os.chdir(directory)
            if args.daemon:
                launch_daemon(directory, lock)
                return
            from deciflow import server

            server.ROOT = directory
            print(f"Configuration: {selected}", flush=True)
            # Inherit the lock and mode across UI exec-based restarts.
            sys.orig_argv = [
                sys.executable,
                "-m",
                "deciflow.cli",
                "start",
            ]
            with Runtime(directory, os.getenv(DAEMON_ENV) == "1") as runtime:
                try:
                    server.main(
                        manage_proxy=True,
                        stop=runtime.stop,
                        on_started=runtime.ready.set,
                    )
                except SystemExit as error:
                    if error.code:
                        print(f"Run: {check_command}", file=sys.stderr)
                    raise
    except (ValueError, OSError, RuntimeError) as error:
        print(f"DeciFlow stopped: {error}\nRun: {check_command}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
