"""Start an installed DeciFlow application with a writable user workspace."""

import argparse
import os
import shlex
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from deciflow.paths import RESOURCE_ROOT

GUIDE = "https://github.com/call518/DeciFlow/blob/main/docs/tool-install.md"


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
    replacements = {
        "COMPOSE_PROFILES": "",
        "LAYA_API_URL": "http://127.0.0.1:8000/v1/systemone",
    }
    lines = [
        f"{line.split('=', 1)[0]}={replacements[line.split('=', 1)[0]]}"
        if not line.startswith("#") and line.split("=", 1)[0] in replacements
        else line
        for line in text.splitlines()
    ]
    with env.open("x", encoding="utf-8") as output:
        env.chmod(0o600)
        output.write("\n".join(lines) + "\n")
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
    """Initialize or inspect configuration, or validate and start DeciFlow."""
    location = argparse.ArgumentParser(add_help=False)
    location.add_argument(
        "--config-dir",
        type=Path,
        default=argparse.SUPPRESS,
        help="directory containing .env and oauth2-proxy files (default: ~/.config/deciflow)",
    )
    parser = argparse.ArgumentParser(
        description="Start DeciFlow after checking its configuration.",
        parents=[location],
    )
    parser.add_argument("--version", action="version", version=version("deciflow"))
    commands = parser.add_subparsers(dest="command")
    start = commands.add_parser(
        "start", parents=[location], help="validate and start DeciFlow"
    )
    start.add_argument(
        "--daemon", action="store_true", help="start detached with file logging"
    )
    commands.add_parser(
        "status", parents=[location], help="show this installation's process status"
    )
    commands.add_parser(
        "stop", parents=[location], help="stop this installation gracefully"
    )
    commands.add_parser(
        "init", parents=[location], help="create configuration templates"
    )
    config = commands.add_parser(
        "config", parents=[location], help="inspect configuration"
    )
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser(
        "test", parents=[location], help="check startup prerequisites"
    )
    config_commands.add_parser(
        "list", parents=[location], help="list effective settings with secrets redacted"
    )
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    directory = (
        getattr(args, "config_dir", Path.home() / ".config" / "deciflow")
        .expanduser()
        .resolve()
    )
    check_command = shlex.join(
        ["deciflow", "config", "test", "--config-dir", str(directory)]
    )
    try:
        if args.command == "init":
            created = prepare_workspace(directory)
            print(
                f"{'Created' if created else 'Preserved'} {directory / '.env'}. "
                "Edit the configuration, then run:\n"
                f"{check_command}"
            )
            return
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

        if not directory.is_dir():
            raise ValueError(
                f"Run deciflow init --config-dir {shlex.quote(str(directory))}"
            )
        with RunLock(directory) as lock:
            result = run_config_test(directory, detailed=False)
            if result:
                advice = (
                    check_command
                    if (directory / ".env").is_file()
                    else shlex.join(
                        ["deciflow", "init", "--config-dir", str(directory)]
                    )
                )
                print(f"Run: {advice}", file=sys.stderr)
                raise SystemExit(result)
            os.chdir(directory)
            if args.daemon:
                launch_daemon(directory, lock)
                return
            from deciflow import server

            server.ROOT = directory
            print(f"Configuration: {directory / '.env'}", flush=True)
            # Inherit the lock and mode across UI exec-based restarts.
            sys.orig_argv = [
                sys.executable,
                "-m",
                "deciflow.cli",
                "start",
                "--config-dir",
                str(directory),
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
