"""Register local Python actions and pass decisions through standard input."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import anyio
from anyio.abc import ByteReceiveStream

from classifier import Result

REGISTRY_PATH = Path("/var/lib/deciflow-actions/actions.json")
ACTION_TIMEOUT = 30
PREPARE_TIMEOUT = 300
REGISTRY_LOCK = anyio.Lock()
MODULE_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9,._-]+\])?"
    r"(?:\s*(?:===|==|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9.*+!_-]+"
    r"(?:\s*,\s*(?:===|==|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9.*+!_-]+)*)?"
)


def get_registry_path() -> Path:
    """Use configurable persistent storage, defaulting to /var/lib/deciflow-actions."""
    directory = os.getenv("DECIFLOW_ACTIONS_DIR", "").strip()
    return (
        Path(directory).expanduser().absolute() / "actions.json"
        if directory
        else REGISTRY_PATH
    )


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
        if fields["name"] in names:
            raise ValueError("Action names must be unique.")
        names.add(fields["name"])
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
            if not isinstance(identity, str) or not re.fullmatch(
                r"[0-9a-f]{32}", identity
            ):
                raise ValueError("Invalid action ID.")
            if identity in identities:
                raise ValueError("Action IDs must be unique.")
            identities.add(identity)
            fields["id"] = identity
        actions.append(fields)
    return actions


def load_actions() -> list[Result]:
    """Read saved actions; absent registry means no actions are configured."""
    registry = get_registry_path()
    if not registry.exists():
        return []
    values = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(values, list) or any(
        not isinstance(value, dict)
        or any(
            not isinstance(value.get(key), str) for key in ("name", "python", "script")
        )
        for value in values
    ):
        raise ValueError("Invalid action registry.")
    return values


async def save_actions(values: object) -> list[Result]:
    """Prepare independent environments before atomically saving registrations."""
    actions = validate_actions(values)
    async with REGISTRY_LOCK:
        previous = {action.get("id"): action for action in load_actions()}
        for action in actions:
            if action.get("pythonVersion"):
                await prepare_action(action, previous.get(action["id"]))
        registry = get_registry_path()
        for action in actions:
            if "code" in action:
                script = (
                    registry.parent / action["id"] / "scripts" / f"{uuid4().hex}.py"
                )
                script.parent.mkdir(parents=True, exist_ok=True)
                script.write_text(action["code"], encoding="utf-8")
                action["script"] = str(script)
        registry.parent.mkdir(parents=True, exist_ok=True)
        temporary = registry.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(actions, indent=2) + "\n", encoding="utf-8")
        temporary.replace(registry)
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


async def prepare_action(action: Result, previous: Result | None = None) -> None:
    """Reuse unchanged environments or build a new revision without replacing one."""
    unchanged = previous is not None and all(
        previous.get(key) == action[key] for key in ("pythonVersion", "modules")
    )
    revision = previous["revision"] if unchanged and previous else uuid4().hex
    project = get_registry_path().parent / action["id"] / "environments" / revision
    interpreter = (
        project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    ready = project / ".ready"
    action.update({"revision": revision, "python": str(interpreter)})
    if ready.is_file() and interpreter.is_file() and (project / "uv.lock").is_file():
        return
    ready.unlink(missing_ok=True)
    project.mkdir(parents=True, exist_ok=True)
    if unchanged and previous and not (project / "uv.lock").is_file():
        old_project = Path(previous["python"]).parent.parent.parent
        if old_project != project and (old_project / "uv.lock").is_file():
            for filename in ("pyproject.toml", "uv.lock"):
                shutil.copyfile(old_project / filename, project / filename)
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
                ["venv", "--no-project", "--python", version, str(project / ".venv")],
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
    """Run JSON stdin; bound error output and stop on timeout or cancellation."""
    started = perf_counter()
    if action.get("pythonVersion") and (
        not Path(action["python"]).is_file()
        or not (Path(action["python"]).parent.parent.parent / ".ready").is_file()
    ):
        return {
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
        "name": action["name"],
        **outcome,
        "elapsedMs": round((perf_counter() - started) * 1000),
    }
