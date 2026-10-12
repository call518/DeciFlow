"""Verify local action registration and real subprocess delivery."""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

import actions
import server
from classifier import Result
from config import get_engine
from source_settings import parse_source_settings, resolve_configured_sources


def make_action(tmp_path: Path, code: str) -> Result:
    """Create a trusted script for an isolated action test."""
    script = tmp_path / "action.py"
    script.write_text(code, encoding="utf-8")
    return {"name": "capture", "python": sys.executable, "script": str(script)}


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
    specs = parse_source_settings([{"path": str(source), "action": "capture"}])

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
    assert received["schemaVersion"] == 1
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
        yield 1, {"action": "capture", "error": "Provider failed"}

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
    monkeypatch.setattr(actions, "REGISTRY_PATH", tmp_path / "actions.json")
    action = make_action(tmp_path, "pass\n")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.get("/api/actions")).json() == {"actions": []}
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
                "sources": [{"path": "missing", "action": "unknown"}],
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
            {"path": str(source), "action": "first"},
            {"path": str(source), "action": "second"},
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
    import zipfile

    monkeypatch.setattr(
        actions, "REGISTRY_PATH", tmp_path / "registry" / "actions.json"
    )
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(tmp_path / "deciflow-venv"))
    monkeypatch.setenv("UV_OFFLINE", "1")
    monkeypatch.setenv("UV_NO_INDEX", "1")
    monkeypatch.setenv("UV_PYTHON_DOWNLOADS", "never")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
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
    assert not (tmp_path / "deciflow-venv").exists()
    assert Path(saved["python"]) != Path(sys.executable)
    assert (await actions.run_action(saved, {"category": "normal"}))[
        "status"
    ] == "success"
    assert json.loads(output.read_text())["module"] == "isolated module"
    project = Path(saved["python"]).parent.parent.parent
    assert project.parent.parent == actions.REGISTRY_PATH.parent / saved["id"]
    lock = (project / "uv.lock").read_bytes()
    unchanged = (await actions.save_actions([{**saved, "name": "renamed"}]))[0]
    assert unchanged["python"] == saved["python"]
    shutil.rmtree(project / ".venv")
    assert "missing" in (await actions.run_action(unchanged, {}))["error"]
    restored = (await actions.save_actions([unchanged]))[0]
    assert restored["python"] == unchanged["python"]
    assert (project / "uv.lock").read_bytes() == lock
    assert (await actions.run_action(restored, {}))["status"] == "success"
    changed = (await actions.save_actions([{**restored, "modules": []}]))[0]
    assert changed["id"] == saved["id"]
    assert changed["python"] != saved["python"]
    assert Path(saved["python"]).is_file()
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
    original = actions.REGISTRY_PATH.read_bytes()
    with pytest.raises(ValueError, match="Could not prepare"):
        await actions.save_actions([{**saved, "modules": ["unavailable-module==9.9"]}])
    assert actions.REGISTRY_PATH.read_bytes() == original
    assert Path(saved["python"]).is_file()
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
    assert Path(saved["python"]).exists()
    assert not (project / ".ready").exists()
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
            actions.REGISTRY_PATH.parent / saved["id"] / "scripts"
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
        assert changed["script"] != saved["script"]
        assert Path(saved["script"]).read_text() == code
        assert (await actions.run_action(changed, {}))["exitCode"] == 7
        assert (await actions.run_action(saved, {}))["status"] == "success"
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
    monkeypatch.setenv("DECIFLOW_ACTIONS_DIR", str(tmp_path / "data"))
    assert actions.get_registry_path() == tmp_path / "data" / "actions.json"


@pytest.mark.parametrize("directory", [None, "", "   "])
def test_default_action_storage(
    monkeypatch: pytest.MonkeyPatch,
    directory: str | None,
) -> None:
    if directory is None:
        monkeypatch.delenv("DECIFLOW_ACTIONS_DIR", raising=False)
    else:
        monkeypatch.setenv("DECIFLOW_ACTIONS_DIR", directory)
    assert actions.get_registry_path() == Path(
        "/var/lib/deciflow-data/actions/actions.json"
    )


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
        actions.REGISTRY_PATH.parent / "environments" / saved["id"] / saved["revision"]
    )
    shutil.copytree(project, old_project, symlinks=True)
    old_script = actions.REGISTRY_PATH.parent / "scripts" / saved["id"] / "old.py"
    old_script.parent.mkdir(parents=True)
    old_script.write_text(saved["code"])
    saved.update(
        python=str(old_project / ".venv" / "bin" / "python"), script=str(old_script)
    )
    actions.REGISTRY_PATH.write_text(json.dumps([saved]))
    shutil.rmtree(project)
    restored = (await actions.save_actions([saved]))[0]
    assert (project / "uv.lock").read_bytes() == (old_project / "uv.lock").read_bytes()
    assert old_script.is_file()
    assert Path(saved["python"]).is_file()
    assert Path(restored["script"]).parent.parent.name == saved["id"]
    assert (await actions.run_action(restored, {}))["status"] == "success"


@pytest.mark.parametrize("directory", [None, "", "   "])
def test_shared_action_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory: str | None
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    if directory is not None:
        monkeypatch.setenv("DECIFLOW_ACTIONS_DIR", directory)
    assert actions.get_registry_path() == tmp_path / "data/actions/actions.json"
    monkeypatch.setenv("DECIFLOW_ACTIONS_DIR", str(tmp_path / "custom"))
    assert actions.get_registry_path() == tmp_path / "custom/actions.json"
