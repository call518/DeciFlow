"""Criteria persistence, validation, trusted access, and run isolation."""

import json
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import DECISION_ANSWERS

from deciflow import server
from deciflow.classifier import Result, classify_log
from deciflow.config import get_engine
from deciflow.config_store import (
    get_database_path,
    load_records,
    save_records,
)
from deciflow.profiles import (
    PROFILES,
    get_profile,
    load_profiles,
    save_profiles,
    use_profile_snapshot,
    validate_profiles,
)


@pytest.fixture
def criteria_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Restore shared profiles after each test and use disposable storage."""
    original = deepcopy(PROFILES)
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path))
    yield tmp_path
    PROFILES.clear()
    PROFILES.update(original)


def test_persistence_and_invalid_save(criteria_storage: Path) -> None:
    values = deepcopy(PROFILES)
    values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"] = deepcopy(
        values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
    )
    values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["label"] = "Custom criteria"
    values.pop("0181af82-c1ed-41c8-8cd3-22a385746b32")
    save_profiles(values)
    PROFILES.pop("a9b5cb3b-1e1e-4559-8f71-365c651d176d")
    load_profiles()
    assert PROFILES == values
    assert "0181af82-c1ed-41c8-8cd3-22a385746b32" not in PROFILES
    saved = load_records("criteria")
    values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["questions"]["category"]["criteria"][
        "normal"
    ] = ""
    with pytest.raises(ValueError, match="nonempty"):
        save_profiles(values)
    assert load_records("criteria") == saved
    assert PROFILES["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["questions"]["category"][
        "criteria"
    ]["normal"]


@pytest.mark.parametrize("invalid", ["categories", "id", "instructions"])
def test_invalid_options_and_required_fields(invalid: str) -> None:
    values = deepcopy(PROFILES)
    if invalid == "categories":
        values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["questions"]["category"][
            "criteria"
        ]["all"] = "reserved"
    elif invalid == "id":
        values["../outside"] = values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
    else:
        values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["instructions"] = " "
    with pytest.raises(ValueError):
        validate_profiles(values)


@pytest.mark.anyio
async def test_criteria_api_trust_and_crud(criteria_storage: Path) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.post("/api/criteria")).status_code == 403
        assert (
            await client.put("/api/criteria", headers={"Origin": "https://evil.test"})
        ).status_code == 403
        headers = {"Origin": "http://localhost"}
        response = await client.post("/api/criteria", headers=headers)
        values = response.json()["profiles"]
        values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"] = deepcopy(
            values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
        )
        values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["label"] = "Custom"
        response = await client.put("/api/criteria", headers=headers, json=values)
        assert response.status_code == 200
        assert (
            response.json()["profiles"]["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["label"]
            == "Custom"
        )
        assert (await client.get("/api/status")).json()["profiles"][
            "a9b5cb3b-1e1e-4559-8f71-365c651d176d"
        ] == "Custom"
        values.pop("a9b5cb3b-1e1e-4559-8f71-365c651d176d")
        assert (
            await client.put("/api/criteria", headers=headers, json=values)
        ).status_code == 200
        assert "a9b5cb3b-1e1e-4559-8f71-365c651d176d" not in PROFILES
        assert (
            await client.put("/api/criteria", headers=headers, content="bad JSON")
        ).status_code == 400


@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.anyio
async def test_custom_criteria_snapshot_reaches_both_engines(
    criteria_storage: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    values = deepcopy(PROFILES)
    values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"] = deepcopy(
        values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
    )
    values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["label"] = "Custom"
    values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["instructions"] = (
        "Original custom instructions"
    )
    save_profiles(values)
    snapshot = deepcopy(PROFILES)
    values.pop("a9b5cb3b-1e1e-4559-8f71-365c651d176d")
    save_profiles(values)

    def handle_request(request: httpx.Request) -> httpx.Response:
        question = json.loads(request.content)["questions"]["category"]
        assert "Original custom instructions" in question["instructions"]
        assert (
            question["criteria"]
            == snapshot["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["questions"][
                "category"
            ]["criteria"]
        )
        return httpx.Response(
            200,
            json={
                "usage": {"truncated": False},
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": "normal",
                        "confidence": 1,
                        "probabilities": {
                            key: int(key == "normal") for key in question["criteria"]
                        },
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with use_profile_snapshot(snapshot):
            result = await classify_log(
                "event", get_engine(), client, "a9b5cb3b-1e1e-4559-8f71-365c651d176d"
            )
    assert result["decisions"]["category"]["choice"] == "normal"
    assert "a9b5cb3b-1e1e-4559-8f71-365c651d176d" not in PROFILES


@pytest.mark.parametrize("mode", ["paste", "batch", "configured_batch"])
@pytest.mark.anyio
async def test_started_runs_keep_original_criteria(
    criteria_storage: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    observed: list[str] = []
    profile = "4e6d5417-611e-49e0-8e23-2444a0f49ee4"
    if mode == "configured_batch":
        values = deepcopy(PROFILES)
        values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"] = deepcopy(
            values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
        )
        values["a9b5cb3b-1e1e-4559-8f71-365c651d176d"]["label"] = "Custom"
        save_profiles(values)
        profile = "a9b5cb3b-1e1e-4559-8f71-365c651d176d"
    original = PROFILES[profile]["instructions"]

    async def handle_classify(
        log: str,
        engine: object,
        client: object,
        profile: str = "4e6d5417-611e-49e0-8e23-2444a0f49ee4",
    ) -> Result:
        observed.append(get_profile(profile)["instructions"])
        return {"category": "normal", "log": log, "elapsedMs": 1}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    if mode == "paste":
        events = server.handle_events(["first", "second"], get_engine())
    else:
        path = criteria_storage / "events.log"
        path.write_text("first\nsecond\n")
        paths = (
            {
                path: {
                    "profile": "a9b5cb3b-1e1e-4559-8f71-365c651d176d",
                    "chunkEvents": 1,
                }
            }
            if mode == "configured_batch"
            else [path]
        )
        events = server.handle_file_events([str(path)], paths, "batch", get_engine())
    await anext(events)
    values = deepcopy(PROFILES)
    values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["instructions"] = (
        "Changed instructions"
    )
    if mode == "configured_batch":
        values.pop("a9b5cb3b-1e1e-4559-8f71-365c651d176d")
    save_profiles(values)
    async for _ in events:
        pass
    assert observed == [original, original]
    assert (
        get_profile("4e6d5417-611e-49e0-8e23-2444a0f49ee4")["instructions"]
        == "Changed instructions"
    )


@pytest.mark.parametrize("directory", [None, "", "   "])
def test_default_criteria_storage(
    monkeypatch: pytest.MonkeyPatch, directory: str | None
) -> None:
    monkeypatch.delenv("DECIFLOW_DATA_DIR", raising=False)
    if directory is not None:
        monkeypatch.setenv("DECIFLOW_DATA_DIR", directory)
    assert get_database_path() == Path("/var/lib/deciflow-data/deciflow.sqlite3")


def test_shared_criteria_and_action_storage(criteria_storage: Path) -> None:
    from deciflow import actions
    save_profiles(deepcopy(PROFILES))
    assert get_database_path() == criteria_storage / "deciflow.sqlite3"
    assert actions.get_actions_directory() == criteria_storage / "actions"
    assert not (criteria_storage / "actions").exists()


def test_startup_creates_criteria_and_preserves_existing_records(
    criteria_storage: Path,
) -> None:
    expected = deepcopy(PROFILES)
    assert not get_database_path().exists()
    load_profiles()
    assert load_records("criteria") == expected
    expected["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["label"] = "Saved custom name"
    expected.pop("0181af82-c1ed-41c8-8cd3-22a385746b32")
    save_records("criteria", expected)
    load_profiles()
    assert PROFILES == expected
    assert not list(criteria_storage.rglob("*.json"))


def test_startup_does_not_replace_invalid_existing_criteria(
    criteria_storage: Path,
) -> None:
    save_records(
        "criteria", {"4e6d5417-611e-49e0-8e23-2444a0f49ee4": {"label": "Invalid"}}
    )
    with pytest.raises(ValueError):
        load_profiles()
    assert load_records("criteria") == {
        "4e6d5417-611e-49e0-8e23-2444a0f49ee4": {"label": "Invalid"}
    }


def test_all_criteria_keep_uuid_identity_after_rename_and_reload(
    criteria_storage: Path,
) -> None:
    """Names are editable metadata; saved and sample UUIDs stay unchanged."""
    values = deepcopy(PROFILES)
    identity = str(uuid4())
    assert UUID(identity).version == 4
    values[identity] = deepcopy(values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"])
    values[identity]["label"] = "한글 Criteria"
    save_profiles(values)
    load_profiles()
    assert PROFILES == values
    assert get_profile(identity)["label"] == "한글 Criteria"
    values[identity]["label"] = "Renamed Criteria"
    save_profiles(values)
    load_profiles()
    assert get_profile(identity)["label"] == "Renamed Criteria"
    assert set(PROFILES) == set(values)
    assert all(UUID(key).version == 4 for key in PROFILES)
    assert (
        get_profile("4e6d5417-611e-49e0-8e23-2444a0f49ee4")
        == values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
    )


@pytest.mark.anyio
async def test_general_is_optional_but_task_assignments_still_block_deletion(
    criteria_storage: Path,
) -> None:
    """General follows the same editing, deletion, and persistence rules as any profile."""
    values = deepcopy(PROFILES)
    values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["instructions"] = (
        "Custom system rules."
    )
    save_profiles(values)
    task = {
        "id": "task",
        "name": "System Task",
        "sources": [{"profile": "4e6d5417-611e-49e0-8e23-2444a0f49ee4"}],
    }
    save_records("tasks", {"task": task})
    del values["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        headers = {"Origin": "http://localhost"}
        blocked = await client.put("/api/criteria", headers=headers, json=values)
        assert blocked.status_code == 400
        assert "System Task" in blocked.json()["error"]
        assert (
            PROFILES["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["instructions"]
            == "Custom system rules."
        )
        task["sources"][0]["profile"] = "2e44ae00-7a3a-492d-8806-9177a8973582"
        save_records("tasks", {"task": task})
        saved = await client.put("/api/criteria", headers=headers, json=values)
        assert saved.status_code == 200
        assert "4e6d5417-611e-49e0-8e23-2444a0f49ee4" not in saved.json()["profiles"]
        load_profiles()
        assert PROFILES == values
        assert "4e6d5417-611e-49e0-8e23-2444a0f49ee4" not in load_records("criteria")
        save_records("tasks", {})
        empty = await client.put("/api/criteria", headers=headers, json={})
        assert empty.status_code == 200
        assert empty.json()["profiles"] == {}
        assert load_records("criteria") == {}
        assert (await client.get("/api/status")).status_code == 200


@pytest.mark.anyio
async def test_main_status_reads_persisted_chart_default_after_reload(
    criteria_storage: Path,
) -> None:
    identity = "efb7c8ca-61c1-4785-b38d-0a86764ca758"
    values = deepcopy(PROFILES)
    values[identity]["defaultDecision"] = "response_type"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        response = await client.put(
            "/api/criteria", headers={"Origin": "http://localhost"}, json=values
        )
        assert response.status_code == 200
        PROFILES.clear()
        load_profiles()
        status = await client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["chartDefaults"][identity] == "response_type"
        assert load_records("criteria")[identity]["defaultDecision"] == "response_type"
