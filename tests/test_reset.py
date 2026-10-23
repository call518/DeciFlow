"""Verify reset safety, explicit confirmation, and shutdown ordering in isolation."""

import asyncio
from pathlib import Path

import asyncssh
import httpx
import pytest

from deciflow import server
from deciflow.reset import reset_data, reset_directory
from deciflow.result_store import open_result_store
from deciflow.tasks import load_tasks


def test_reset_clears_data_without_following_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(root))
    root.mkdir()
    outside = tmp_path / "input.log"
    outside.write_text("keep")
    (root / "external").symlink_to(outside)
    (root / ".hidden").write_text("remove")
    (root / "nested").mkdir()
    (root / "nested" / "file").write_text("remove")
    open_result_store(root)
    reset_data(reset_directory())
    assert root.is_dir() and list(root.iterdir()) == []
    assert outside.read_text() == "keep"
    assert not open_result_store(root).contains("missing")


@pytest.mark.parametrize("path", ["/", "/var/lib", "/tmp", str(server.ROOT)])
def test_reset_rejects_protected_roots(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", path)
    with pytest.raises(ValueError, match="directory|application"):
        reset_directory()


@pytest.mark.parametrize("parent", [False, True])
def test_reset_preserves_installed_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, parent: bool
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("DECISION_ENGINE=laya\n")
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path if parent else workspace))
    with pytest.raises(ValueError, match="directory|application"):
        reset_directory()
    assert (workspace / ".env").is_file()


def test_reset_rejects_symlink_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(link))
    with pytest.raises(ValueError, match="dedicated"):
        reset_directory()


@pytest.mark.anyio
async def test_reset_requires_origin_confirmation_and_defers_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    marker = root / "keep-until-shutdown"
    marker.write_text("test")
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(root))
    monkeypatch.setattr(server.app.state, "reset_requested", False, raising=False)
    called = asyncio.Event()

    async def handle_shutdown() -> None:
        called.set()

    monkeypatch.setattr(server, "handle_reset_shutdown", handle_shutdown)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.post("/api/reset", json={})).status_code == 403
        client.headers["Origin"] = "http://localhost"
        assert (await client.post("/api/reset", json={})).status_code == 400
        assert marker.exists() and not called.is_set()
        response = await client.post(
            "/api/reset", json={"confirmation": "RESET DECIFLOW"}
        )
        assert response.status_code == 202
        assert called.is_set() and marker.exists()
        assert (await client.post("/api/reset", json={})).status_code == 409
        status = (await client.post("/api/reset/status")).json()
        assert status["resetting"] is True
        assert status["dataDirectory"] == str(root)


@pytest.mark.anyio
async def test_reset_deletes_after_jobs_stop_and_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(root))
    monkeypatch.setattr(server.app.state, "reset_requested", False, raising=False)
    calls: list[str] = []
    original_reset = server.reset_data

    def handle_reset(path: Path) -> None:
        assert not server.JOBS
        calls.append("delete")
        original_reset(path)

    def handle_restart() -> None:
        calls.append("restart")

    monkeypatch.setattr(server, "reset_data", handle_reset)
    monkeypatch.setattr(server, "restart_process", handle_restart)

    async def handle_initialize() -> None:
        server.load_actions()

    monkeypatch.setattr(server, "initialize_default_action", handle_initialize)
    async with server.lifespan(server.app):
        await asyncio.sleep(0.05)
        assert load_tasks()
        server.app.state.reset_root = root
        server.app.state.reset_requested = True
    assert calls == ["delete", "restart"]
    assert root.is_dir()
    assert [entry.name for entry in root.iterdir()] == ["ssh-keys"]
    assert not list((root / "ssh-keys").iterdir())


@pytest.mark.anyio
async def test_reset_reports_incomplete_cleanup_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("_DECIFLOW_RESET_ERROR", raising=False)
    monkeypatch.setattr(server.app.state, "reset_requested", False, raising=False)
    restarted: list[bool] = []

    def handle_failure(root: Path) -> None:
        raise OSError("Synthetic cleanup failure")

    monkeypatch.setattr(server, "reset_data", handle_failure)
    monkeypatch.setattr(server, "restart_process", lambda: restarted.append(True))

    async def handle_initialize() -> None:
        server.load_actions()

    monkeypatch.setattr(server, "initialize_default_action", handle_initialize)
    async with server.lifespan(server.app):
        await asyncio.sleep(0.05)
        server.app.state.reset_root = tmp_path / "data"
        server.app.state.reset_requested = True
    assert restarted == [True]
    assert "incomplete" in server.os.environ["_DECIFLOW_RESET_ERROR"]


def test_reset_preserves_ssh_key_files_and_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserved keys remain visible and usable after other app data is reset."""
    from deciflow.config_store import save_records
    from deciflow.ssh_keys import add_key, get_key, list_keys

    root = tmp_path / "data"
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(root))
    key = add_key(
        "Keep Key",
        asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode(),
    )
    private_path = Path(key["privatePath"])
    before = private_path.read_bytes()
    save_records("tasks", {"old": {"name": "Remove"}})
    reset_data(reset_directory())
    assert private_path.read_bytes() == before
    assert get_key(key["id"])["name"] == "Keep Key"
    assert [item["id"] for item in list_keys()] == [key["id"]]
    assert load_tasks() == []
