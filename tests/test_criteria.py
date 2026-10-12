"""Criteria persistence, validation, trusted access, and run isolation."""

import json
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

import server
from classifier import Result, classify_log
from config import get_engine
from profiles import (
    PROFILES,
    get_criteria_path,
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
    values["custom"] = deepcopy(values["general"])
    values["custom"]["label"] = "Custom criteria"
    values.pop("network")
    save_profiles(values)
    PROFILES.pop("custom")
    load_profiles()
    assert PROFILES == values
    assert "network" not in PROFILES
    saved = get_criteria_path().read_bytes()
    values["custom"]["criteria"]["normal"] = ""
    with pytest.raises(ValueError, match="nonempty"):
        save_profiles(values)
    assert get_criteria_path().read_bytes() == saved
    assert PROFILES["custom"]["criteria"]["normal"]


@pytest.mark.parametrize("invalid", ["categories", "general", "id", "instructions"])
def test_fixed_categories_and_required_fields(invalid: str) -> None:
    values = deepcopy(PROFILES)
    if invalid == "categories":
        values["general"]["criteria"]["score"] = "extra"
    elif invalid == "general":
        values.pop("general")
    elif invalid == "id":
        values["../outside"] = values["general"]
    else:
        values["general"]["instructions"] = " "
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
        values["custom"] = deepcopy(values["general"])
        values["custom"]["label"] = "Custom"
        response = await client.put("/api/criteria", headers=headers, json=values)
        assert response.status_code == 200
        assert response.json()["profiles"]["custom"]["label"] == "Custom"
        assert (await client.get("/api/status")).json()["profiles"][
            "custom"
        ] == "Custom"
        values.pop("custom")
        assert (
            await client.put("/api/criteria", headers=headers, json=values)
        ).status_code == 200
        assert "custom" not in PROFILES
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
    values["custom"] = deepcopy(values["general"])
    values["custom"]["instructions"] = "Original custom instructions"
    save_profiles(values)
    snapshot = deepcopy(PROFILES)
    values.pop("custom")
    save_profiles(values)

    def handle_request(request: httpx.Request) -> httpx.Response:
        question = json.loads(request.content)["questions"]["category"]
        assert "Original custom instructions" in question["instructions"]
        assert question["criteria"] == snapshot["custom"]["criteria"]
        return httpx.Response(
            200,
            json={
                "usage": {"truncated": False},
                "answers": {
                    "category": {
                        "choice": "normal",
                        "confidence": 1,
                        "probabilities": {
                            key: int(key == "normal") for key in question["criteria"]
                        },
                    }
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with use_profile_snapshot(snapshot):
            result = await classify_log("event", get_engine(), client, "custom")
    assert result["category"] == "normal"
    assert "custom" not in PROFILES


@pytest.mark.parametrize("mode", ["paste", "batch", "configured_batch"])
@pytest.mark.anyio
async def test_started_runs_keep_original_criteria(
    criteria_storage: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    observed: list[str] = []
    profile = "general"
    if mode == "configured_batch":
        values = deepcopy(PROFILES)
        values["custom"] = deepcopy(values["general"])
        save_profiles(values)
        profile = "custom"
    original = PROFILES[profile]["instructions"]

    async def handle_classify(
        log: str, engine: object, client: object, profile: str = "general"
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
            {path: {"profile": "custom", "chunkEvents": 1}}
            if mode == "configured_batch"
            else [path]
        )
        events = server.handle_file_events([str(path)], paths, "batch", get_engine())
    await anext(events)
    values = deepcopy(PROFILES)
    values["general"]["instructions"] = "Changed instructions"
    if mode == "configured_batch":
        values.pop("custom")
    save_profiles(values)
    async for _ in events:
        pass
    assert observed == [original, original]
    assert get_profile("general")["instructions"] == "Changed instructions"


@pytest.mark.parametrize("directory", [None, "", "   "])
def test_default_criteria_storage(
    monkeypatch: pytest.MonkeyPatch, directory: str | None
) -> None:
    if directory is not None:
        monkeypatch.setenv("DECIFLOW_DATA_DIR", directory)
    assert get_criteria_path() == Path("/var/lib/deciflow-data/criteria/criteria.json")


def test_separate_criteria_storage(
    criteria_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import actions

    monkeypatch.setenv("DECIFLOW_ACTIONS_DIR", str(criteria_storage / "custom-actions"))
    save_profiles(deepcopy(PROFILES))
    assert get_criteria_path() == criteria_storage / "criteria/criteria.json"
    assert (
        actions.get_registry_path() == criteria_storage / "custom-actions/actions.json"
    )
    assert not (criteria_storage / "custom-actions").exists()


def test_startup_creates_criteria_and_preserves_existing_file(
    criteria_storage: Path,
) -> None:
    expected = deepcopy(PROFILES)
    path = get_criteria_path()
    assert not path.exists()
    load_profiles()
    assert json.loads(path.read_text()) == expected
    assert PROFILES == expected

    expected["general"]["label"] = "Saved custom name"
    expected.pop("network")
    path.write_text(json.dumps(expected))
    saved = path.read_bytes()
    load_profiles()
    assert PROFILES == expected
    assert path.read_bytes() == saved
    assert "network" not in PROFILES


def test_startup_does_not_replace_invalid_existing_criteria(
    criteria_storage: Path,
) -> None:
    path = get_criteria_path()
    path.parent.mkdir(parents=True)
    path.write_text("invalid JSON")
    with pytest.raises(ValueError):
        load_profiles()
    assert path.read_text() == "invalid JSON"
