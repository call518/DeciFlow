"""Verify local action registration and real subprocess delivery."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

import anyio
import httpx
import pytest

import actions
import server
from classifier import Result
from config import get_engine
from config_store import save_records
from source_settings import parse_source_settings, resolve_configured_sources


def make_action(tmp_path: Path, code: str) -> Result:
    """Create a trusted script for an isolated action test."""
    script = tmp_path / "action.py"
    script.write_text(code, encoding="utf-8")
    return {
        "id": uuid4().hex,
        "name": "capture",
        "python": sys.executable,
        "script": str(script),
    }


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_file_action_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    output = tmp_path / "received.json"
    action = make_action(
        tmp_path,
        "import json, sys\nfrom pathlib import Path\n"
        f"Path({str(output)!r}).write_text(json.dumps(json.load(sys.stdin)))\n",
    )
    source = tmp_path / "source.log"
    source.write_text("hello\n", encoding="utf-8")
    specs = parse_source_settings([{"path": str(source), "actionId": action["id"]}])

    async def handle_classify(*args: object) -> Result:
        return {"category": "normal", "probabilities": {"normal": 1}, "review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    events = [
        json.loads(event)
        async for event in server.handle_file_events(
            specs,
            resolve_configured_sources(specs),
            "batch",
            get_engine(),
            specs,
            [action],
        )
    ]
    result = next(event["result"] for event in events if event["type"] == "result")
    received = json.loads(output.read_text())
    assert received["log"] == "hello"
    assert received["source"] == str(source)
    assert received["engine"] == engine
    assert received["schemaVersion"] == 2
    assert received["eventId"] == result["eventId"]
    assert "actionExecution" not in received
    assert result["actionExecution"]["status"] == "success"


@pytest.mark.anyio
async def test_skip_unassigned_and_failed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def handle_run(*args: object) -> Result:
        pytest.fail("Action must not run")

    async def handle_results():
        yield 0, {"category": "normal"}
        yield 1, {"actionId": "capture", "error": "Provider failed"}

    monkeypatch.setattr(server, "run_action", handle_run)
    assert (
        len(
            [
                item
                async for item in server._action_results(handle_results(), [], "laya")
            ]
        )
        == 2
    )


@pytest.mark.anyio
async def test_action_failure_timeout_and_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = make_action(tmp_path, "raise SystemExit(7)\n")
    result = await actions.run_action(action, {})
    assert result["status"] == "failed"
    assert result["exitCode"] == 7
    action = make_action(tmp_path, "import time\ntime.sleep(60)\n")
    monkeypatch.setattr(actions, "ACTION_TIMEOUT", 0.05)
    result = await actions.run_action(action, {})
    assert "timed out" in result["error"]
    monkeypatch.setattr(actions, "ACTION_TIMEOUT", 30)
    task = asyncio.create_task(actions.run_action(action, {}))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    action["python"] = str(tmp_path / "missing")
    assert (await actions.run_action(action, {}))["status"] == "failed"


@pytest.mark.anyio
async def test_registration_api_and_unknown_assignment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    action = make_action(tmp_path, "pass\n")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        initial = (await client.get("/api/actions")).json()["actions"]
        assert len(initial) == 1 and initial[0]["name"] == "Elasticsearch"
        assert (await client.put("/api/actions", json=[action])).status_code == 403
        headers = {"Origin": "http://localhost"}
        response = await client.put("/api/actions", json=[action], headers=headers)
        assert response.status_code == 200
        assert actions.load_actions()[0]["name"] == "capture"
        for body in [[action, action], {}, [{**action, "script": "missing"}]]:
            assert (
                await client.put("/api/actions", json=body, headers=headers)
            ).status_code == 400
        response = await client.post(
            "/api/file-source",
            headers=headers,
            json={
                "mode": "batch",
                "sources": [{"path": "missing", "actionId": "unknown"}],
            },
        )
        assert response.status_code == 400
        assert "registered action" in response.json()["error"]
        assert (
            await client.put("/api/actions", json=[], headers=headers)
        ).status_code == 200
        assert actions.load_actions() == []


def test_action_overlap_and_venv_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source.log"
    source.write_text("hello\n")
    specs = parse_source_settings(
        [
            {"path": str(source), "actionId": "first"},
            {"path": str(source), "actionId": "second"},
        ]
    )
    with pytest.raises(ValueError, match="Conflicting"):
        resolve_configured_sources(specs)
    action = make_action(tmp_path, "pass\n")
    interpreter = tmp_path / "python"
    interpreter.symlink_to(sys.executable)
    action["python"] = str(interpreter)
    assert actions.validate_actions([action])[0]["python"] == str(interpreter)


@pytest.mark.anyio
async def test_error_output_is_bounded(tmp_path: Path) -> None:
    action = make_action(
        tmp_path, "import sys\nsys.stderr.write('x' * 100000)\nraise SystemExit(9)\n"
    )
    result = await actions.run_action(action, {})
    assert result["exitCode"] == 9
    assert len(result["error"]) == 4096


@pytest.fixture
def managed_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a local wheel index and installed Python without network access."""
    import ensurepip
    import shutil
    import zipfile

    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(tmp_path / "deciflow-venv"))
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.setenv("UV_NO_INDEX", "1")
    monkeypatch.setenv("UV_PYTHON_DOWNLOADS", "never")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    for seed_wheel in Path(ensurepip.__file__).with_name("_bundled").glob("*.whl"):
        shutil.copyfile(seed_wheel, wheels / seed_wheel.name)
    monkeypatch.setenv("UV_FIND_LINKS", str(wheels))
    with zipfile.ZipFile(
        wheels / "deciflow_test_module-1.0.0-py3-none-any.whl", "w"
    ) as wheel:
        wheel.writestr("action_probe.py", 'VALUE = "isolated module"\n')
        prefix = "deciflow_test_module-1.0.0.dist-info/"
        wheel.writestr(
            prefix + "METADATA",
            "Metadata-Version: 2.1\nName: deciflow-test-module\nVersion: 1.0.0\n",
        )
        wheel.writestr(
            prefix + "WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wheel.writestr(prefix + "RECORD", "")


@pytest.mark.anyio
async def test_managed_environment_install_reuse_and_restore(
    tmp_path: Path,
    managed_environment: None,
) -> None:
    import shutil

    output = tmp_path / "module.json"
    action = make_action(
        tmp_path,
        "import json, sys, action_probe\nfrom pathlib import Path\n"
        f"Path({str(output)!r}).write_text(json.dumps("
        "{'module': action_probe.VALUE, 'result': json.load(sys.stdin)}))\n",
    )
    action.pop("python")
    action.update(
        {
            "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
            "modules": "deciflow-test-module==1.0.0",
        }
    )
    saved = (await actions.save_actions([action]))[0]
    assert Path(saved["python"]).is_file()
    assert (
        await anyio.run_process([saved["python"], "-m", "pip", "--version"])
    ).stdout.startswith(b"pip ")
    assert (
        await anyio.run_process(
            [str(Path(saved["python"]).with_name("pip")), "--version"]
        )
    ).stdout.startswith(b"pip ")
    assert not (tmp_path / "deciflow-venv").exists()
    assert Path(saved["python"]) != Path(sys.executable)
    assert (await actions.run_action(saved, {"category": "normal"}))[
        "status"
    ] == "success"
    assert json.loads(output.read_text())["module"] == "isolated module"
    project = Path(saved["python"]).parent.parent.parent
    assert project == actions.get_actions_directory() / saved["directory"]
    lock = (project / "uv.lock").read_bytes()
    unchanged = (await actions.save_actions([saved]))[0]
    assert unchanged["python"] == saved["python"]
    shutil.rmtree(project / ".venv")
    assert "missing" in (await actions.run_action(unchanged, {}))["error"]
    restored = (await actions.save_actions([unchanged]))[0]
    assert (
        await anyio.run_process([restored["python"], "-m", "pip", "--version"])
    ).stdout.startswith(b"pip ")
    assert restored["python"] == unchanged["python"]
    assert (project / "uv.lock").read_bytes() == lock
    assert (await actions.run_action(restored, {}))["status"] == "success"
    changed = (await actions.save_actions([{**restored, "modules": []}]))[0]
    assert changed["id"] == saved["id"]
    assert changed["python"] == saved["python"]
    assert Path(changed["python"]).is_file()
    assert (await actions.run_action(changed, {}))["status"] == "failed"
    assert "action_probe" in (await actions.run_action(changed, {}))["error"]


@pytest.mark.anyio
async def test_failed_prepare_preserves_registry_and_existing_environment(
    tmp_path: Path,
    managed_environment: None,
) -> None:
    action = make_action(tmp_path, "pass\n")
    action.update(
        {
            "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
            "modules": [],
        }
    )
    saved = (await actions.save_actions([action]))[0]
    original = actions.load_actions()
    project = Path(saved["python"]).parent.parent.parent
    marker = project / ".venv" / "keep-marker"
    marker.touch()
    lock = (project / "uv.lock").read_bytes()
    with pytest.raises(ValueError, match="Could not prepare"):
        await actions.save_actions([{**saved, "modules": ["unavailable-module==9.9"]}])
    assert actions.load_actions() == original
    assert Path(saved["python"]).is_file()
    assert marker.is_file()
    assert (project / "uv.lock").read_bytes() == lock
    assert not list(project.glob(".prepare-*"))
    assert (await actions.run_action(saved, {}))["status"] == "success"


@pytest.mark.parametrize(
    "fields",
    [
        {"pythonVersion": "../python"},
        {"pythonVersion": "", "modules": ["requests"]},
        {"modules": ["--system"]},
        {"modules": ["package @ https://example.com/private.whl"]},
        {"modules": ["package\nother"]},
        {"id": "../../outside"},
    ],
)
def test_managed_settings_validation(tmp_path: Path, fields: Result) -> None:
    action = make_action(tmp_path, "pass\n")
    action.update({"pythonVersion": "3.12", "modules": [], **fields})
    with pytest.raises(ValueError):
        actions.validate_actions([action])


@pytest.mark.anyio
async def test_incomplete_restoration_is_not_executed(
    tmp_path: Path,
    managed_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    action = make_action(tmp_path, "pass\n")
    action.update(
        {
            "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
            "modules": [],
        }
    )
    saved = (await actions.save_actions([action]))[0]
    project = Path(saved["python"]).parent.parent.parent
    shutil.rmtree(project / ".venv")
    original = actions._run_uv

    async def handle_uv(arguments: list[str], directory: Path) -> None:
        if arguments[0] == "sync":
            raise ValueError("Installation failed")
        await original(arguments, directory)

    monkeypatch.setattr(actions, "_run_uv", handle_uv)
    with pytest.raises(ValueError, match="Installation failed"):
        await actions.save_actions([saved])
    assert not Path(saved["python"]).exists()
    assert actions.get_action_status(saved) == "not_ready"
    assert (await actions.run_action(saved, {}))["status"] == "failed"
    monkeypatch.setattr(actions, "_run_uv", original)
    await actions.save_actions([saved])
    assert (await actions.run_action(saved, {}))["status"] == "success"


@pytest.mark.anyio
async def test_inline_code_save_edit_and_api(
    tmp_path: Path,
    managed_environment: None,
) -> None:
    output = tmp_path / "inline.json"
    code = (
        "import json, sys\nfrom pathlib import Path\n"
        f"Path({str(output)!r}).write_text(json.dumps(json.load(sys.stdin)))\n"
    )
    action = {"name": "inline", "pythonVersion": "3.12", "modules": [], "code": code}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        headers = {"Origin": "http://localhost"}
        assert (await client.post("/api/actions")).status_code == 403
        response = await client.put("/api/actions", headers=headers, json=[action])
        assert response.status_code == 200
        saved = response.json()["actions"][0]
        assert Path(saved["script"]).parent == (
            actions.get_actions_directory() / saved["directory"]
        )
        assert Path(saved["script"]).read_text() == code
        assert (await actions.run_action(saved, {"category": "normal"}))[
            "status"
        ] == "success"
        assert json.loads(output.read_text())["category"] == "normal"
        loaded = (await client.post("/api/actions", headers=headers)).json()["actions"][
            0
        ]
        assert loaded["code"] == code
        assert "code" not in (await client.get("/api/actions")).json()["actions"][0]
        edited = {**loaded, "code": "raise SystemExit(7)\n"}
        changed = (
            await client.put("/api/actions", headers=headers, json=[edited])
        ).json()["actions"][0]
        assert changed["python"] == saved["python"]
        assert changed["script"] == saved["script"]
        assert Path(saved["script"]).read_text() == edited["code"]
        assert (await actions.run_action(changed, {}))["exitCode"] == 7
        invalid = {**changed, "code": ""}
        assert (
            await client.put("/api/actions", headers=headers, json=[invalid])
        ).status_code == 400
        assert actions.load_actions()[0]["script"] == changed["script"]
        assert (
            await client.put("/api/actions", headers=headers, json=[])
        ).status_code == 200
        assert actions.load_actions() == []


def test_configurable_action_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    assert actions.get_actions_directory() == tmp_path / "data" / "actions"


@pytest.mark.parametrize("directory", [None, "", "   "])
def test_default_action_storage(
    monkeypatch: pytest.MonkeyPatch,
    directory: str | None,
) -> None:
    if directory is None:
        monkeypatch.delenv("DECIFLOW_DATA_DIR", raising=False)
    else:
        monkeypatch.setenv("DECIFLOW_DATA_DIR", directory)
    assert actions.get_actions_directory() == Path("/var/lib/deciflow-data/actions")


@pytest.mark.anyio
async def test_save_legacy_layout_preserves_lock_and_old_files(
    tmp_path: Path,
    managed_environment: None,
) -> None:
    import shutil

    action = {
        "name": "migration",
        "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}",
        "modules": ["deciflow-test-module==1.0.0"],
        "code": "import action_probe\n",
    }
    saved = (await actions.save_actions([action]))[0]
    project = Path(saved["python"]).parent.parent.parent
    old_project = (
        actions.get_actions_directory() / "environments" / saved["id"] / "Rev-1-example"
    )
    shutil.copytree(project, old_project, symlinks=True)
    old_script = actions.get_actions_directory() / "scripts" / saved["id"] / "old.py"
    old_script.parent.mkdir(parents=True)
    old_script.write_text(saved["code"])
    saved.update(
        python=str(old_project / ".venv" / "bin" / "python"), script=str(old_script)
    )
    save_records("actions", {saved["id"]: saved})
    shutil.rmtree(project)
    restored = (await actions.save_actions([saved]))[0]
    restored_project = Path(restored["python"]).parent.parent.parent
    assert (restored_project / "uv.lock").read_bytes() == (
        old_project / "uv.lock"
    ).read_bytes()
    assert old_script.is_file()
    assert Path(saved["python"]).is_file()
    assert Path(restored["script"]).parent.name == saved["directory"]
    assert (await actions.run_action(restored, {}))["status"] == "success"


@pytest.mark.anyio
async def test_reset_rebuilds_only_venv_and_delete_removes_owned_data(
    tmp_path: Path, managed_environment: None
) -> None:
    action = make_action(tmp_path, "pass")
    action.pop("python")
    action.update(
        pythonVersion="3.12", modules=["deciflow-test-module==1.0.0"], code="pass"
    )
    saved = (await actions.save_actions([action]))[0]
    project = Path(saved["python"]).parent.parent.parent
    lock = (project / "uv.lock").read_bytes()
    registry = actions.load_actions()
    script = Path(saved["script"])
    (project / ".venv" / "old-marker").touch()
    unused = project / "data"
    unused.mkdir()
    (unused / "unused-file").touch()
    reset = await actions.reset_action(saved["id"])
    assert reset["python"] == saved["python"]
    assert not (project / ".venv" / "old-marker").exists()
    assert (project / "uv.lock").read_bytes() == lock
    assert script.read_text() == "pass"
    assert actions.load_actions() == registry
    assert (
        await anyio.run_process([reset["python"], "-m", "pip", "--version"])
    ).stdout.startswith(b"pip ")
    with actions.use_actions([saved]):
        with pytest.raises(ValueError, match="Stop runs"):
            await actions.reset_action(saved["id"])
        with pytest.raises(ValueError, match="Stop runs"):
            await actions.save_actions([])
        assert script.exists()
        assert (project / ".ready").exists()
    await actions.save_actions([])
    assert not script.parent.exists()
    assert actions.load_actions() == []
    assert (tmp_path / "action.py").exists()


@pytest.mark.anyio
async def test_reset_failure_keeps_action_unready_and_can_be_retried(
    tmp_path: Path, managed_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = make_action(tmp_path, "pass")
    action.pop("python")
    action.update(pythonVersion="3.12", modules=[])
    saved = (await actions.save_actions([action]))[0]
    original = actions._run_uv

    async def handle_failure(arguments: list[str], project: Path) -> None:
        raise ValueError("test preparation failure")

    monkeypatch.setattr(actions, "_run_uv", handle_failure)
    with pytest.raises(ValueError, match="test preparation failure"):
        await actions.reset_action(saved["id"])
    assert saved["id"] not in actions.ACTION_OPERATIONS
    assert actions.load_actions()[0]["id"] == saved["id"]
    assert (await actions.run_action(saved, {}))["status"] == "failed"
    monkeypatch.setattr(actions, "_run_uv", original)
    await actions.reset_action(saved["id"])
    assert (await actions.run_action(saved, {}))["status"] == "success"


@pytest.mark.anyio
async def test_reset_api_requires_trusted_origin(
    tmp_path: Path, managed_environment: None
) -> None:
    action = make_action(tmp_path, "pass")
    action.pop("python")
    action.update(pythonVersion="3.12", modules=[])
    saved = (await actions.save_actions([action]))[0]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        endpoint = f"/api/actions/{saved['id']}/reset"
        assert (await client.post(endpoint)).status_code == 403
        headers = {"Origin": "http://localhost"}
        response = await client.post(endpoint, headers=headers)
        assert response.status_code == 200
        assert response.json()["action"]["id"] == saved["id"]
        assert (
            await client.post("/api/actions/unknown/reset", headers=headers)
        ).status_code == 400


@pytest.mark.anyio
async def test_file_run_protects_action_before_first_execution(
    tmp_path: Path, managed_environment: None
) -> None:
    from contextlib import aclosing

    action = make_action(tmp_path, "pass")
    action.pop("python")
    action.update(pythonVersion="3.12", modules=[], code="pass")
    saved = (await actions.save_actions([action]))[0]
    source = tmp_path / "events.log"
    source.write_text("event\n")
    async with aclosing(
        server.handle_file_events(
            [str(source)], [source], "batch", get_engine(), actions=[saved]
        )
    ) as events:
        assert json.loads(await anext(events))["type"] == "start"
        with pytest.raises(ValueError, match="Stop runs"):
            await actions.reset_action(saved["id"])
        with pytest.raises(ValueError, match="Stop runs"):
            await actions.save_actions([])
    assert saved["id"] not in actions.ACTION_USERS
    await actions.reset_action(saved["id"])
    await actions.save_actions([])


@pytest.mark.anyio
async def test_action_maintenance_rejects_new_users(
    tmp_path: Path, managed_environment: None
) -> None:
    action = make_action(tmp_path, "pass")
    action.pop("python")
    action.update(pythonVersion="3.12", modules=[], code="pass")
    saved = (await actions.save_actions([action]))[0]
    with (
        actions._maintain_actions([saved]),
        pytest.raises(ValueError, match="maintenance"),
        actions.use_actions([saved]),
    ):
        pytest.fail("Maintenance must reject a new user.")
    assert saved["id"] not in actions.ACTION_OPERATIONS


@pytest.mark.anyio
async def test_action_ready_requires_completed_dependency_sync(
    tmp_path: Path, managed_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = make_action(tmp_path, "pass")
    action.pop("python")
    action.update(pythonVersion="3.12", modules=[], code="pass")
    saved = (await actions.save_actions([action]))[0]
    assert actions.get_action_status(saved) == "ready"
    original = actions._run_uv
    syncing = asyncio.Event()
    finish = asyncio.Event()

    async def handle_sync(arguments: list[str], project: Path) -> None:
        if arguments[0] == "sync":
            syncing.set()
            await finish.wait()
        await original(arguments, project)

    monkeypatch.setattr(actions, "_run_uv", handle_sync)
    reset = asyncio.create_task(actions.reset_action(saved["id"]))
    try:
        await asyncio.wait_for(syncing.wait(), timeout=5)
        assert actions.get_action_status(saved) == "preparing"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
        ) as client:
            response = await client.get("/api/actions")
            assert response.json()["actions"][0]["environmentStatus"] == "preparing"
    finally:
        finish.set()
        await reset
    assert actions.get_action_status(saved) == "ready"
    project = Path(saved["python"]).parent.parent.parent
    (project / ".ready").unlink()
    assert actions.get_action_status(saved) == "not_ready"
    assert actions.get_action_status(make_action(tmp_path, "pass")) == "external"


@pytest.mark.anyio
async def test_actions_keep_only_current_code_and_environment(
    managed_environment: None,
) -> None:
    action = {
        "name": "Elastic/search ..",
        "pythonVersion": "3.12",
        "modules": [],
        "code": "pass\n",
    }
    saved = (await actions.save_actions([action]))[0]
    assert saved["directory"] == saved["id"]
    assert "revision" not in saved and "history" not in saved
    unchanged = (await actions.save_actions([saved]))[0]
    assert unchanged == saved
    edited = (await actions.save_actions([{**unchanged, "code": "print('new')\n"}]))[0]
    assert edited["python"] == saved["python"]
    assert edited["script"] == saved["script"]
    assert Path(edited["script"]).read_text() == "print('new')\n"
    changed = (
        await actions.save_actions(
            [{**edited, "modules": ["deciflow-test-module==1.0.0"]}]
        )
    )[0]
    assert changed["script"] == edited["script"]
    assert changed["python"] == saved["python"]
    directory = actions.get_actions_directory() / saved["directory"]
    assert Path(changed["script"]) == directory / "action.py"
    assert Path(changed["python"]).parent.parent == directory / ".venv"
    assert {path.name for path in directory.iterdir()} == {
        "action.py",
        ".venv",
        "pyproject.toml",
        "uv.lock",
        ".ready",
    }
    assert not list(directory.rglob("Rev-*"))
    assert "revision" not in changed and "history" not in changed
    reset = await actions.reset_action(changed["id"])
    assert reset == changed
    await actions.save_actions([])
    assert not directory.exists()


@pytest.mark.anyio
async def test_failed_save_keeps_current_action_and_removes_prepared_files(
    managed_environment: None,
) -> None:
    saved = (
        await actions.save_actions(
            [{"name": "probe", "pythonVersion": "3.12", "modules": [], "code": "pass"}]
        )
    )[0]
    registry = actions.load_actions()
    with pytest.raises(ValueError):
        await actions.save_actions(
            [
                {
                    **saved,
                    "modules": ["missing-module==9.9"],
                    "code": "raise SystemExit(1)",
                }
            ]
        )
    assert actions.load_actions() == registry
    assert Path(saved["script"]).read_text() == "pass"
    directory = actions.get_actions_directory() / saved["directory"]
    assert not list(directory.glob(".prepare-*"))
    assert not (directory / "environments").exists()
    assert Path(saved["python"]).is_file()
    assert (await actions.run_action(saved, {}))["status"] == "success"


@pytest.mark.anyio
@pytest.mark.parametrize("layout", ["uuid", "rev"])
async def test_nested_paths_are_flattened_on_save(
    managed_environment: None, layout: str
) -> None:
    saved = (
        await actions.save_actions(
            [
                {
                    "name": "existing",
                    "pythonVersion": "3.12",
                    "modules": [],
                    "code": "pass",
                }
            ]
        )
    )[0]
    directory = Path(saved["script"]).parent
    environment = "a" * 32 if layout == "uuid" else "Rev-1-environment"
    script = "b" * 32 if layout == "uuid" else "Rev-1-script"
    old_project = directory / "environments" / environment
    old_project.mkdir(parents=True)
    for name in (".venv", "pyproject.toml", "uv.lock", ".ready"):
        (directory / name).replace(old_project / name)
    old_script = directory / "scripts" / f"{script}.py"
    old_script.parent.mkdir()
    Path(saved["script"]).replace(old_script)
    (directory / "keep.txt").write_text("user data")
    lock = (old_project / "uv.lock").read_bytes()
    saved.update(
        python=str(old_project / ".venv" / "bin" / "python"),
        script=str(old_script),
        revision="Rev-1-environment",
        history={"environments": [], "scripts": []},
    )
    save_records("actions", {saved["id"]: saved})
    loaded = actions.load_actions()[0]
    assert "revision" not in loaded and "history" not in loaded
    with pytest.raises(ValueError, match="Save this Action"):
        await actions.reset_action(saved["id"])
    restored = (await actions.save_actions([loaded]))[0]
    assert restored["id"] == saved["id"]
    assert not (directory / "environments").exists()
    assert not (directory / "scripts").exists()
    assert Path(restored["script"]) == directory / "action.py"
    assert Path(restored["python"]).parent.parent == directory / ".venv"
    assert (directory / "uv.lock").read_bytes() == lock
    assert (directory / "keep.txt").read_text() == "user data"
    assert "revision" not in restored and "history" not in restored
    assert (await actions.run_action(restored, {}))["status"] == "success"
    assert (
        await anyio.run_process([restored["python"], "-m", "pip", "--version"])
    ).stdout.startswith(b"pip ")


@pytest.mark.anyio
async def test_concurrent_saves_keep_only_the_current_script(
    managed_environment: None,
) -> None:
    saved = (
        await actions.save_actions(
            [{"name": "probe", "pythonVersion": "3.12", "modules": [], "code": "pass"}]
        )
    )[0]

    async def handle_save(code: str) -> None:
        await actions.save_actions([{**saved, "code": code}])

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(handle_save, "print(1)")
        tasks.start_soon(handle_save, "print(2)")
    current = actions.load_actions()[0]
    assert Path(current["script"]).read_text() in {"print(1)", "print(2)"}
    assert list(Path(current["script"]).parent.glob("*.py")) == [
        Path(current["script"])
    ]
    assert not list(Path(current["script"]).parent.glob(".prepare-*"))
    assert current["python"] == saved["python"]


@pytest.mark.anyio
async def test_used_action_cannot_be_edited_but_other_actions_can(
    managed_environment: None,
) -> None:
    first, second = await actions.save_actions(
        [
            {"name": name, "pythonVersion": "3.12", "modules": [], "code": "pass"}
            for name in ("first", "second")
        ]
    )
    registry = actions.load_actions()
    with actions.use_actions([first]):
        for changes in ({"code": "print(1)"}, {"modules": ["deciflow-test-module"]}):
            with pytest.raises(ValueError, match="Stop runs"):
                await actions.save_actions([{**first, **changes}, second])
            assert actions.load_actions() == registry
        assert (await actions.save_actions([first, second])) == [first, second]
        changed = await actions.save_actions([first, {**second, "code": "print(2)"}])
        assert changed[0] == first
        assert changed[1]["script"] == second["script"]
        assert Path(second["script"]).read_text() == "print(2)"
        assert (await actions.run_action(first, {}))["status"] == "success"


@pytest.mark.anyio
async def test_action_rename_preserves_id_paths_and_environment(
    managed_environment: None,
) -> None:
    saved = (
        await actions.save_actions(
            [
                {
                    "name": "Original",
                    "pythonVersion": "3.12",
                    "modules": [],
                    "code": "pass",
                }
            ]
        )
    )[0]
    script = Path(saved["script"]).read_bytes()
    lock = (Path(saved["script"]).parent / "uv.lock").read_bytes()
    with actions.use_actions([saved]):
        renamed = (await actions.save_actions([{**saved, "name": "Renamed"}]))[0]
    assert saved["name"] == "Original"
    assert renamed["id"] == saved["id"]
    assert renamed["script"] == saved["script"] and renamed["python"] == saved["python"]
    assert Path(saved["script"]).read_bytes() == script
    assert (Path(saved["script"]).parent / "uv.lock").read_bytes() == lock
    assert actions.load_actions()[0]["name"] == "Renamed"


@pytest.mark.anyio
async def test_failed_batch_save_preserves_all_current_actions(
    managed_environment: None,
) -> None:
    saved = await actions.save_actions(
        [
            {"name": name, "pythonVersion": "3.12", "modules": [], "code": "pass"}
            for name in ("first", "second")
        ]
    )
    registry = actions.load_actions()
    with pytest.raises(ValueError, match="Could not prepare"):
        await actions.save_actions(
            [
                {
                    **saved[0],
                    "modules": ["deciflow-test-module==1.0.0"],
                    "code": "print(1)",
                },
                {**saved[1], "modules": ["unavailable-module==9.9"]},
            ]
        )
    assert actions.load_actions() == registry
    for action in saved:
        directory = actions.get_actions_directory() / action["directory"]
        assert not list(directory.glob(".prepare-*"))
        assert not (directory / "environments").exists()
        assert Path(action["script"]).read_text() == "pass"
        assert (await actions.run_action(action, {}))["status"] == "success"


@pytest.mark.anyio
async def test_registry_write_failure_preserves_current_script(
    managed_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = (
        await actions.save_actions(
            [{"name": "probe", "pythonVersion": "3.12", "modules": [], "code": "pass"}]
        )
    )[0]
    registry = actions.load_actions()

    def handle_save(kind: str, records: object) -> None:
        raise OSError("Registry unavailable")

    monkeypatch.setattr(actions, "save_records", handle_save)
    with pytest.raises(OSError, match="Registry unavailable"):
        await actions.save_actions([{**saved, "code": "raise SystemExit(1)"}])
    assert actions.load_actions() == registry
    assert list(Path(saved["script"]).parent.glob("*.py")) == [Path(saved["script"])]
    assert not list(Path(saved["script"]).parent.glob(".prepare-*"))
    assert Path(saved["script"]).read_text() == "pass"
    assert (await actions.run_action(saved, {}))["status"] == "success"


@pytest.mark.anyio
async def test_environment_replacement_blocks_new_runs_until_saved(
    managed_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = (
        await actions.save_actions(
            [{"name": "probe", "pythonVersion": "3.12", "modules": [], "code": "pass"}]
        )
    )[0]
    preparing = asyncio.Event()
    finish = asyncio.Event()
    original = actions._run_uv

    async def handle_uv(arguments: list[str], project: Path) -> None:
        preparing.set()
        await finish.wait()
        await original(arguments, project)

    monkeypatch.setattr(actions, "_run_uv", handle_uv)
    task = asyncio.create_task(
        actions.save_actions([{**saved, "modules": ["deciflow-test-module==1.0.0"]}])
    )
    try:
        await asyncio.wait_for(preparing.wait(), 5)
        with (
            pytest.raises(ValueError, match="maintenance is in progress"),
            actions.use_actions([saved]),
        ):
            pytest.fail("The Action must remain unavailable during replacement")
        assert actions.get_action_status(saved) == "preparing"
    finally:
        finish.set()
        changed = (await task)[0]
    assert changed["python"] == saved["python"]
    assert actions.get_action_status(changed) == "ready"
    assert (await actions.run_action(changed, {}))["status"] == "success"


@pytest.mark.anyio
async def test_cancelled_save_preserves_current_action_and_cleans_preparation(
    managed_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = (
        await actions.save_actions(
            [{"name": "probe", "pythonVersion": "3.12", "modules": [], "code": "pass"}]
        )
    )[0]
    registry = actions.load_actions()
    preparing = anyio.Event()

    async def handle_uv(arguments: list[str], project: Path) -> None:
        preparing.set()
        await anyio.sleep_forever()

    async def handle_save() -> None:
        await actions.save_actions([{**saved, "modules": ["deciflow-test-module"]}])

    monkeypatch.setattr(actions, "_run_uv", handle_uv)
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(handle_save)
        with anyio.fail_after(5):
            await preparing.wait()
        tasks.cancel_scope.cancel()
    assert actions.load_actions() == registry
    assert saved["id"] not in actions.ACTION_OPERATIONS
    project = Path(saved["python"]).parent.parent.parent
    assert not list(project.glob(".prepare-*"))
    assert Path(saved["python"]).is_file()
    assert Path(saved["script"]).read_text() == "pass"
    assert (await actions.run_action(saved, {}))["status"] == "success"


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_uuid_assignments_survive_rename_and_reused_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    """A reused label must never redirect an existing Task to another Action."""
    from source_registry import save_sources
    from tasks import load_tasks, save_task

    monkeypatch.setenv("DECISION_ENGINE", engine)
    source_path = tmp_path / "input.txt"
    source_path.write_text("one\n")
    source = save_sources(
        [{"name": "Input", "type": "local", "path": str(source_path)}]
    )[0]
    original = (
        await actions.save_actions(
            [make_action(tmp_path, "import sys\nsys.stdin.read()\n")]
        )
    )[0]
    task = save_task(
        {
            "name": "Analysis",
            "mode": "batch",
            "sources": [{"sourceId": source["id"], "actionId": original["id"]}],
        }
    )
    renamed = {**original, "name": "Renamed Action"}
    replacement = {**original, "id": uuid4().hex}
    await actions.save_actions([renamed, replacement])
    assert load_tasks()[0]["sources"][0]["actionId"] == original["id"]

    async def handle_classify(*args: object) -> Result:
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    settings, events = await server.prepare_file_execution("batch", task["sources"])
    assert settings["sources"][0]["actionName"] == "Renamed Action"
    rows = [json.loads(event) async for event in events]
    result = next(row["result"] for row in rows if row["type"] == "result")
    assert result["actionId"] == original["id"]
    assert result["action"] == "Renamed Action"
    assert result["actionExecution"]["id"] == original["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        blocked = await client.put("/api/actions", json=[replacement])
        assert blocked.status_code == 400 and "used" in blocked.json()["error"]
    with pytest.raises(ValueError, match="unique"):
        await actions.save_actions([renamed, {**replacement, "name": "renamed action"}])


def test_default_elasticsearch_action_is_seeded_once_without_preparation() -> None:
    """Sample registration is persistent and never downloads or executes at startup."""
    from config_store import save_records

    sample = actions.load_actions()[0]
    assert sample["id"] == actions.DEFAULT_ACTION_ID
    assert sample["name"] == "Elasticsearch"
    assert sample["pythonVersion"] == "3.12"
    assert sample["modules"] == ["elasticsearch"]
    compile(sample["code"], "sample-action", "exec")
    assert "datetime.now(timezone.utc).isoformat()" in sample["code"]
    assert "result = json.load(sys.stdin)" in sample["code"]
    assert 'Elasticsearch("http://host.docker.internal:9200")' in sample["code"]
    assert 'es.index(index="deciflow", document=doc)' in sample["code"]
    assert actions.get_action_status(sample) == "not_ready"
    assert not actions.get_actions_directory().exists()
    renamed = {**sample, "name": "My Elasticsearch", "code": "pass"}
    save_records("actions", {sample["id"]: renamed})
    assert actions.load_actions() == [renamed]
    save_records("actions", {})
    assert actions.load_actions() == []


@pytest.mark.anyio
async def test_default_action_preparation_and_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def handle_prepare(action: Result, previous: Result | None = None) -> None:
        calls.append(action["id"])
        if len(calls) == 1:
            raise ValueError("Package download failed")
        directory = Path(action["script"]).parent
        directory.mkdir(parents=True, exist_ok=True)
        interpreter = Path(action["python"])
        interpreter.parent.mkdir(parents=True, exist_ok=True)
        interpreter.touch(mode=0o755)
        (directory / ".ready").touch()
        (directory / "uv.lock").touch()

    monkeypatch.setattr(actions, "prepare_action", handle_prepare)
    await actions.initialize_default_action()
    assert "Package download failed" in actions.load_actions()[0]["preparationError"]
    await actions.initialize_default_action()
    sample = actions.load_actions()[0]
    assert actions.get_action_status(sample) == "ready"
    assert Path(sample["script"]).read_text() == actions.DEFAULT_ACTION_CODE
    assert "preparationError" not in sample
    await actions.initialize_default_action()
    assert len(calls) == 2
    Path(sample["script"]).unlink()
    await actions.initialize_default_action()
    assert Path(sample["script"]).read_text() == actions.DEFAULT_ACTION_CODE
    assert len(calls) == 3
    save_records("actions", {})
    await actions.initialize_default_action()
    assert actions.load_actions() == []
    assert len(calls) == 3


@pytest.mark.anyio
async def test_name_prefixed_directory_moves_only_after_successful_save(
    managed_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = (
        await actions.save_actions(
            [
                {
                    "name": "Original",
                    "pythonVersion": "3.12",
                    "modules": [],
                    "code": "pass",
                }
            ]
        )
    )[0]
    directory = Path(saved["script"]).parent
    legacy = directory.with_name(f"Original-{saved['id']}")
    directory.rename(legacy)
    saved.update(
        directory=legacy.name,
        script=str(legacy / "action.py"),
        python=str(legacy / ".venv" / "bin" / "python"),
    )
    save_records("actions", {saved["id"]: saved})
    original_save = actions.save_records

    def handle_failure(*args: object) -> None:
        raise OSError("Synthetic storage failure")

    monkeypatch.setattr(actions, "save_records", handle_failure)
    with pytest.raises(OSError, match="Synthetic"):
        await actions.save_actions([saved])
    assert legacy.is_dir()
    assert actions.load_actions() == [saved]
    monkeypatch.setattr(actions, "save_records", original_save)
    migrated = (await actions.save_actions([saved]))[0]
    assert migrated["directory"] == saved["id"]
    assert not legacy.exists()
    assert actions.get_action_status(migrated) == "ready"
    renamed = (await actions.save_actions([{**migrated, "name": "Renamed"}]))[0]
    assert renamed["python"] == migrated["python"]
    assert renamed["script"] == migrated["script"]
    assert list(actions.get_actions_directory().iterdir()) == [directory]


@pytest.mark.anyio
async def test_ready_and_reset_error_match_actual_environment(
    managed_environment: None,
) -> None:
    saved = (
        await actions.save_actions(
            [{"name": "Probe", "pythonVersion": "3.12", "modules": [], "code": "pass"}]
        )
    )[0]
    script = Path(saved["script"])
    script.unlink()
    assert actions.get_action_status(saved) == "not_ready"
    saved = (await actions.save_actions([saved]))[0]
    assert script.is_file()
    assert actions.get_action_status(saved) == "ready"
    saved["preparationError"] = "Earlier package download failed"
    save_records("actions", {saved["id"]: saved})
    restored = await actions.reset_action(saved["id"])
    assert "preparationError" not in restored
    assert "preparationError" not in actions.load_actions()[0]
    assert actions.get_action_status(restored) == "ready"
