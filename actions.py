"""Register local Python actions and pass decisions through standard input."""

import json
import logging
import os
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import NAMESPACE_URL, uuid4, uuid5

import anyio
from anyio.abc import ByteReceiveStream

from classifier import Result
from config_store import (
    get_data_directory,
    load_records,
    save_record,
    save_records,
)
from result_payload import compact_result

DEFAULT_ACTION_ID = uuid5(NAMESPACE_URL, "deciflow:action:elasticsearch").hex
DEFAULT_ACTION_CODE = """import json
import sys
from datetime import datetime, timezone
from elasticsearch import Elasticsearch

result = json.load(sys.stdin)

es = Elasticsearch("http://host.docker.internal:9200")

doc = {
    **result,
    "@timestamp": datetime.now(timezone.utc).isoformat(),
}

resp = es.index(index="deciflow", document=doc)
print(resp["result"], resp["_id"])
"""
ACTION_TIMEOUT = 30
PREPARE_TIMEOUT = 300
REGISTRY_LOCK = anyio.Lock()
ACTION_USERS: Counter[str] = Counter()
ACTION_OPERATIONS: set[str] = set()
PREPARING_ACTIONS: set[str] = set()
MODULE_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9,._-]+\])?"
    r"(?:\s*(?:===|==|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9.*+!_-]+"
    r"(?:\s*,\s*(?:===|==|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9.*+!_-]+)*)?"
)


def get_actions_directory() -> Path:
    """Return the directory for Action scripts, projects and environments."""
    return get_data_directory() / "actions"


def _default_action() -> Result:
    action: Result = {
        "id": DEFAULT_ACTION_ID,
        "name": "Sample Elasticsearch",
        "pythonVersion": "3.12",
        "modules": ["elasticsearch"],
        "code": DEFAULT_ACTION_CODE,
    }
    _initialize_action(action)
    directory = _action_directory(action)
    executable = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    action.update(
        python=str(directory / ".venv" / executable),
        script=str(directory / "action.py"),
    )
    return action


def validate_actions(values: object) -> list[Result]:
    """Validate names and existing executable/script paths without running code."""
    if not isinstance(values, list):
        raise TypeError("Actions must be a list.")
    actions: list[Result] = []
    names: set[str] = set()
    identities: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            raise TypeError("Each action must contain name, python, and script.")
        version_value = value.get("pythonVersion", "")
        if not isinstance(version_value, str):
            raise TypeError("Python version must be a string.")
        managed = bool(version_value.strip())
        if not managed and value.get("modules"):
            raise ValueError("Enter a Python version to install modules.")
        fields: Result = {}
        inline = "code" in value
        if inline:
            code = value["code"]
            if not isinstance(code, str) or not code.strip():
                raise ValueError("Enter Python code for the action.")
            if not managed:
                raise ValueError("Enter a Python version for the action code.")
            fields["code"] = code
        keys = (
            ("name",)
            if inline
            else (("name", "script") if managed else ("name", "python", "script"))
        )
        for key in keys:
            text = value.get(key)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Enter an action {key}.")
            fields[key] = text.strip()
        if fields["name"].casefold() in names:
            raise ValueError("Action names must be unique.")
        names.add(fields["name"].casefold())
        for key in () if inline else (("script",) if managed else ("python", "script")):
            # Keep venv interpreter symlinks: resolving them loses the venv.
            path = Path(fields[key]).expanduser().absolute()
            if not path.is_file():
                raise ValueError(f"Action {key} file does not exist: {path}")
            if key == "python" and not os.access(path, os.X_OK):
                raise ValueError(f"Action Python is not executable: {path}")
            fields[key] = str(path)
        if managed:
            version = version_value.strip()
            if not isinstance(version, str) or not re.fullmatch(
                r"3\.\d+(?:\.\d+)?", version
            ):
                raise ValueError("Enter a Python version such as 3.12 or 3.12.11.")
            modules = value.get("modules", [])
            if isinstance(modules, str):
                modules = [
                    line.strip() for line in modules.splitlines() if line.strip()
                ]
            if not isinstance(modules, list) or any(
                not isinstance(module, str) or not MODULE_PATTERN.fullmatch(module)
                for module in modules
            ):
                raise ValueError(
                    "Enter package names with optional extras or versions."
                )
            fields.update({"pythonVersion": version, "modules": modules})
        identity = value.get("id") or uuid4().hex
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
            raise ValueError("Invalid action ID.")
        if identity in identities:
            raise ValueError("Action IDs must be unique.")
        identities.add(identity)
        fields["id"] = identity
        actions.append(fields)
    return actions


def load_actions() -> list[Result]:
    """Seed the sample on first initialization; preserve saved edits and deletions."""
    default = _default_action()
    records = load_records("actions", {default["id"]: default})
    values = list(records.values())
    if not isinstance(values, list) or any(
        not isinstance(value, dict)
        or any(
            not isinstance(value.get(key), str) for key in ("name", "python", "script")
        )
        for value in values
    ):
        raise ValueError("Invalid action registry.")

    return values


async def initialize_default_action() -> None:
    """Prepare the bundled Action before Tasks can start; retry failed setup later."""
    async with REGISTRY_LOCK:
        action = next(
            (item for item in load_actions() if item["id"] == DEFAULT_ACTION_ID), None
        )
        if action is None:
            return
        if get_action_status(action) == "ready" and Path(action["script"]).is_file():
            return
        try:
            await prepare_action(action)
            Path(action["script"]).write_text(action["code"], encoding="utf-8")
            action.pop("preparationError", None)
        except (OSError, ValueError, TimeoutError) as error:
            action["preparationError"] = str(error)
            logging.getLogger("uvicorn.error").exception(
                "Default Action environment preparation failed."
            )
        save_record("actions", action["id"], action)


def _action_directory(action: Result) -> Path:
    identity = action.get("id")
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
        raise ValueError("Select a UI-managed Action with a valid ID.")
    if action.get("directory", identity) != identity:
        raise ValueError("Invalid Action directory.")
    return get_actions_directory() / identity


def _initialize_action(action: Result) -> None:
    action["directory"] = action["id"]


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


@contextmanager
def _update_action(action: Result, previous: Result | None) -> Iterator[None]:
    directory = _action_directory(action)
    directory.mkdir(parents=True, exist_ok=True)
    same_environment = previous is not None and all(
        previous.get(key) == action[key] for key in ("pythonVersion", "modules")
    )
    files = ["action.py"]
    if (
        not same_environment
        or previous is None
        or Path(previous["python"]).parent.parent.parent != directory
        or not Path(previous["python"]).is_file()
        or not (directory / ".ready").is_file()
        or not (directory / "uv.lock").is_file()
    ):
        files.extend([".venv", "pyproject.toml", "uv.lock", ".ready"])
    # Build at the final path: venv entry points contain absolute interpreter paths.
    with TemporaryDirectory(prefix=".prepare-", dir=directory) as temporary:
        backup = Path(temporary)
        moved: list[Path] = []
        prepared: list[Path] = []
        try:
            for filename in files:
                path = directory / filename
                if path.exists() or path.is_symlink():
                    path.replace(backup / filename)
                    moved.append(path)
                prepared.append(path)
            if same_environment:
                for filename in ("pyproject.toml", "uv.lock"):
                    if (backup / filename).is_file():
                        shutil.copyfile(backup / filename, directory / filename)
            yield
        except BaseException:
            for path in prepared:
                _remove_path(path)
            for path in moved:
                (backup / path.name).replace(path)
            raise


def ensure_actions_available(actions: list[Result]) -> None:
    """Reject new runs while their Action environments are being rebuilt."""
    if any(action.get("id") in ACTION_OPERATIONS for action in actions):
        raise ValueError(
            "Action maintenance is in progress. Try again after it finishes."
        )


@contextmanager
def use_actions(actions: list[Result]) -> Iterator[None]:
    """Protect Action data throughout analysis, including between executions."""
    ensure_actions_available(actions)
    identities = {action["id"] for action in actions if action.get("id")}
    ACTION_USERS.update(identities)
    try:
        yield
    finally:
        for identity in identities:
            ACTION_USERS[identity] -= 1
            if not ACTION_USERS[identity]:
                del ACTION_USERS[identity]


def _ensure_idle(actions: list[Result]) -> None:
    if any(ACTION_USERS[action.get("id", "")] for action in actions):
        raise ValueError(
            "Stop runs using this Action before editing, resetting, or deleting it."
        )


@contextmanager
def _maintain_actions(actions: list[Result]) -> Iterator[None]:
    _ensure_idle(actions)
    identities = {action["id"] for action in actions}
    ACTION_OPERATIONS.update(identities)
    try:
        yield
    finally:
        ACTION_OPERATIONS.difference_update(identities)


async def reset_action(identity: str) -> Result:
    """Rebuild only the saved Action's venv, keeping code and locked dependencies."""
    async with REGISTRY_LOCK:
        action = next((a for a in load_actions() if a.get("id") == identity), None)
        if action is None or not action.get("pythonVersion"):
            raise ValueError("Select a registered UI-managed Action.")
        directory = _action_directory(action)
        project = Path(action["python"]).parent.parent.parent
        venv = project / ".venv"
        if project != directory:
            raise ValueError("Save this Action before resetting its environment.")
        with _maintain_actions([action]):
            (project / ".ready").unlink(missing_ok=True)
            if venv.exists():
                await anyio.to_thread.run_sync(shutil.rmtree, venv)
            await prepare_action(action)
            action.pop("preparationError", None)
            save_record("actions", action["id"], action)
        return action


async def save_actions(values: object) -> list[Result]:
    """Prepare independent environments before atomically saving registrations."""
    actions = validate_actions(values)
    async with REGISTRY_LOCK:
        saved = load_actions()
        previous = {action.get("id"): action for action in saved}
        retained = {action.get("id") for action in actions}
        removed = [a for key, a in previous.items() if key and key not in retained]
        managed = [a for a in actions if a.get("pythonVersion")]
        changing = []
        for action in managed:
            old = previous.get(action["id"])
            _initialize_action(action)
            if "code" not in action:
                action["code"] = Path(action["script"]).read_text(encoding="utf-8")
            directory = _action_directory(action)
            if (
                old is None
                or any(
                    action.get(key) != old.get(key)
                    for key in ("pythonVersion", "modules", "code")
                )
                or get_action_status(old) != "ready"
                or Path(old["script"]) != directory / "action.py"
                or Path(old["python"]).parent.parent.parent != directory
            ):
                changing.append(action)
        with _maintain_actions([*removed, *changing]), ExitStack() as updates:
            for action in changing:
                updates.enter_context(
                    _update_action(action, previous.get(action["id"]))
                )
            for action in managed:
                await prepare_action(action)
                script = _action_directory(action) / "action.py"
                if (
                    not script.is_file()
                    or script.read_text(encoding="utf-8") != action["code"]
                ):
                    script.write_text(action["code"], encoding="utf-8")
                action["script"] = str(script)
            save_records(
                "actions",
                {action["id"]: action for action in actions},
            )
        for action in removed:
            await anyio.to_thread.run_sync(_remove_path, _action_directory(action))
    return actions


async def _run_uv(arguments: list[str], project: Path) -> None:
    environment = dict(os.environ)
    environment.pop("VIRTUAL_ENV", None)
    environment.pop("UV_PROJECT", None)
    # Docker sets this for DeciFlow; never install Action packages into that venv.
    environment["UV_PROJECT_ENVIRONMENT"] = str(project / ".venv")
    async with await anyio.open_process(
        ["uv", *arguments, "--no-config", "--no-progress"],
        cwd=project,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as process:
        try:
            with anyio.fail_after(PREPARE_TIMEOUT):
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(_read_output, process.stdout)
                    tasks.start_soon(_read_output, process.stderr)
                    while process.returncode is None:
                        await anyio.sleep(0.05)
            if process.returncode != 0:
                raise ValueError(
                    f"uv {arguments[0]} failed (exit {process.returncode}). "
                    "Check the Python version, modules, and package index access."
                )
        finally:
            if process.returncode is None:
                process.kill()
                with anyio.CancelScope(shield=True):
                    while process.returncode is None:
                        await anyio.sleep(0.05)


def get_action_status(action: Result) -> str:
    """Report readiness only after dependency sync completed successfully."""
    if not action.get("pythonVersion"):
        return "external"
    if action.get("id") in PREPARING_ACTIONS | ACTION_OPERATIONS:
        return "preparing"
    interpreter = Path(action["python"])
    project = interpreter.parent.parent.parent
    return (
        "ready"
        if (
            interpreter.is_file()
            and Path(action["script"]).is_file()
            and (project / ".ready").is_file()
            and (project / "uv.lock").is_file()
        )
        else "not_ready"
    )


async def prepare_action(action: Result) -> None:
    """Track preparation until Python and all dependencies are installed."""
    identity = action["id"]
    PREPARING_ACTIONS.add(identity)
    try:
        await _prepare_action(action)
    finally:
        PREPARING_ACTIONS.discard(identity)


async def _prepare_action(action: Result) -> None:
    """Prepare the environment directly in its Action directory."""
    if "directory" not in action:
        _initialize_action(action)
    project = _action_directory(action)
    interpreter = (
        project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    ready = project / ".ready"
    action["python"] = str(interpreter)
    if ready.is_file() and interpreter.is_file() and (project / "uv.lock").is_file():
        return
    ready.unlink(missing_ok=True)
    project.mkdir(parents=True, exist_ok=True)
    version = action["pythonVersion"]
    if not (project / "uv.lock").is_file():
        constraint = version if version.count(".") == 2 else version + ".*"
        (project / "pyproject.toml").write_text(
            '[project]\nname = "deciflow-action"\nversion = "0.1.0"\n'
            f'requires-python = "=={constraint}"\ndependencies = []\n',
            encoding="utf-8",
        )
    try:
        if not interpreter.is_file():
            if (project / ".venv").exists():
                shutil.rmtree(project / ".venv")
            await _run_uv(
                [
                    "venv",
                    "--seed",
                    "--no-project",
                    "--python",
                    version,
                    str(project / ".venv"),
                ],
                project,
            )
        if not (project / "uv.lock").is_file():
            if action["modules"]:
                await _run_uv(
                    [
                        "add",
                        "--no-sync",
                        "--raw",
                        "--python",
                        version,
                        *action["modules"],
                    ],
                    project,
                )
            else:
                await _run_uv(["lock", "--python", version], project)
        await _run_uv(
            [
                "sync",
                "--frozen",
                "--no-dev",
                "--no-install-project",
                "--python",
                version,
            ],
            project,
        )
    except (OSError, ValueError, TimeoutError) as error:
        raise ValueError(
            f"Could not prepare action {action['name']}. {error}"
        ) from error
    ready.touch()


async def _read_output(stream: ByteReceiveStream | None, limit: int = 0) -> str:
    if stream is None:
        return ""
    output = bytearray()
    async for chunk in stream:
        output.extend(chunk[: max(0, limit - len(output))])
    return output.decode("utf-8", errors="replace")


async def run_action(action: Result, payload: Result) -> Result:
    """Protect owned data while executing an Action, including direct callers."""
    try:
        with use_actions([action]):
            return await _run_action(
                action,
                {
                    key: value
                    for key, value in compact_result(payload).items()
                    if key
                    not in {
                        "_workId",
                        "_checkpoint",
                        "_recoveredResult",
                        "_actionPhase",
                    }
                },
            )
    except ValueError as error:
        return {
            "id": action["id"],
            "name": action["name"],
            "status": "failed",
            "elapsedMs": 0,
            "error": str(error),
        }


async def _run_action(action: Result, payload: Result) -> Result:
    """Run JSON stdin; bound error output and stop on timeout or cancellation."""
    started = perf_counter()
    if action.get("pythonVersion") and (
        not Path(action["python"]).is_file()
        or not (Path(action["python"]).parent.parent.parent / ".ready").is_file()
    ):
        return {
            "id": action["id"],
            "name": action["name"],
            "status": "failed",
            "elapsedMs": 0,
            "error": (
                "Action environment is missing or incomplete. "
                "Save actions to prepare it."
            ),
        }
    stderr = ""
    environment = dict(os.environ)
    if action.get("pythonVersion"):
        executable = Path(action["python"])
        environment["VIRTUAL_ENV"] = str(executable.parent.parent)
        environment["PATH"] = (
            str(executable.parent) + os.pathsep + environment.get("PATH", "")
        )
    try:
        async with await anyio.open_process(
            [action["python"], action["script"]],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as process:

            async def handle_output() -> None:
                nonlocal stderr
                stderr = await _read_output(process.stderr, 4096)

            code: int | None = None
            try:
                with anyio.fail_after(ACTION_TIMEOUT):
                    async with anyio.create_task_group() as tasks:
                        tasks.start_soon(_read_output, process.stdout)
                        tasks.start_soon(handle_output)
                        assert process.stdin is not None
                        try:
                            await process.stdin.send(
                                (
                                    json.dumps(
                                        payload, ensure_ascii=True, allow_nan=False
                                    )
                                    + "\n"
                                ).encode()
                            )
                        except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                            pass  # Scripts may exit without consuming input.
                        await process.stdin.aclose()
                        while process.returncode is None:
                            await anyio.sleep(0.05)
                        code = process.returncode
            finally:
                if process.returncode is None:
                    process.kill()
                    with anyio.CancelScope(shield=True):
                        while process.returncode is None:
                            await anyio.sleep(0.05)
            outcome = {"status": "success" if code == 0 else "failed", "exitCode": code}
            if code != 0 and stderr:
                outcome["error"] = stderr
    except TimeoutError:
        outcome = {
            "status": "failed",
            "error": f"Action timed out after {ACTION_TIMEOUT} seconds.",
        }
    except OSError as error:
        outcome = {"status": "failed", "error": str(error)}
    return {
        "id": action["id"],
        "name": action["name"],
        **outcome,
        "elapsedMs": round((perf_counter() - started) * 1000),
    }
