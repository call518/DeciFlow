"""Verify unified configuration persistence without legacy JSON imports."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest

from app_settings import load_settings, save_settings
from config_store import (
    get_data_directory,
    get_database_path,
    load_records,
    save_record,
    save_records,
)
from profiles import DEFAULT_PROFILES, PROFILES, load_profiles
from result_store import SQLiteResultStore, close_result_store, open_result_store
from source_registry import (
    CENTRAL_GOV_SOURCE,
    LOCAL_GOV_SOURCE,
    VOC_SOURCE,
    ensure_central_gov_source,
    ensure_local_gov_source,
    ensure_voc_source,
    load_sources,
    save_sources,
)
from tasks import (
    CENTRAL_GOV_TASK_ID,
    DEFAULT_TASK_ID,
    LOCAL_GOV_TASK_ID,
    SYSTEM_MESSAGE_TASK_ID,
    VOC_TASK_ID,
    ensure_central_gov_task,
    ensure_default_task,
    ensure_local_gov_task,
    ensure_system_message_task,
    ensure_voc_task,
    load_tasks,
)


def test_fresh_defaults_are_persisted_and_empty_lists_stay_empty() -> None:
    original = deepcopy(PROFILES)
    try:
        load_profiles()
        ensure_default_task()
        assert load_tasks()[0]["id"] == DEFAULT_TASK_ID
        assert load_tasks()[0]["enabled"] is False
        assert len(load_sources()) == 7
        assert load_settings() == {"resultsPerPage": 30}
        with sqlite3.connect(get_database_path()) as connection:
            counts = dict(
                connection.execute(
                    "SELECT kind,COUNT(*) FROM configuration_records GROUP BY kind"
                )
            )
        assert counts == {"sources": 7, "criteria": 8, "tasks": 1, "settings": 1}
        save_sources([])
        assert load_sources() == []
        assert not list(get_data_directory().rglob("*.json"))
        assert not (get_data_directory() / "tasks").exists()
    finally:
        PROFILES.clear()
        PROFILES.update(original)


def test_database_reopen_preserves_settings_and_per_record_identity() -> None:
    save_settings({"resultsPerPage": 100})
    save_record("hosts", "one", {"name": "First", "hosts": ["a", "b"]})
    store = open_result_store(get_data_directory())
    store.create("test", {"state": "completed", "settings": {}})
    with sqlite3.connect(get_database_path()) as connection:
        assert connection.execute("SELECT id FROM runs").fetchone() == ("test",)
    close_result_store(get_data_directory())
    assert load_settings() == {"resultsPerPage": 100}
    assert load_records("hosts") == {"one": {"name": "First", "hosts": ["a", "b"]}}


def test_failed_collection_write_rolls_back_all_records() -> None:
    save_records("sample", {"one": {"name": "Original"}})
    with pytest.raises(TypeError):
        save_records("sample", {"two": {"name": "Valid"}, "bad": {"invalid": object()}})
    assert load_records("sample") == {"one": {"name": "Original"}}


def test_concurrent_individual_saves_preserve_unrelated_records() -> None:
    load_records("sample")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda index: save_record("sample", str(index), {"index": index}),
                range(40),
            )
        )
    assert len(load_records("sample")) == 40


def test_old_json_and_database_are_not_imported() -> None:
    root = get_data_directory()
    root.mkdir(parents=True)
    for name in [
        "sources/sources.json",
        "criteria/criteria.json",
        "tasks/tasks.json",
        "actions/actions.json",
        "ssh-hosts/hosts.json",
        "settings.json",
    ]:
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("invalid old JSON; deliberately ignored")
    (root / "results.sqlite3").write_text("old database; deliberately ignored")
    original = deepcopy(PROFILES)
    try:
        load_profiles()
        ensure_default_task()
        assert load_settings()["resultsPerPage"] == 30
        assert load_records("criteria") == DEFAULT_PROFILES
        assert len(load_sources()) == 7
        assert load_tasks()[0]["enabled"] is False
    finally:
        PROFILES.clear()
        PROFILES.update(original)


def test_configuration_reads_continue_during_result_writes() -> None:
    load_settings()
    store = SQLiteResultStore(get_database_path())
    store.create("pending", {"state": "running", "settings": {}})
    # WAL readers must not queue behind the result writer.
    with store.transaction() as connection:
        connection.execute("UPDATE runs SET state=state WHERE id='pending'")
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(load_settings).result(timeout=2) == {
                "resultsPerPage": 30
            }


@pytest.mark.parametrize("existing_sample", ["missing", "edited", "renamed_id"])
def test_startup_ensures_consultation_without_overwriting_saved_profiles(
    existing_sample: str,
) -> None:
    """Old installations receive the sample once and retain all user edits."""
    original = deepcopy(PROFILES)
    saved = deepcopy(DEFAULT_PROFILES)
    sample = saved.pop("41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72")
    saved["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["instructions"] = (
        "Keep the user's instructions."
    )
    if existing_sample == "edited":
        sample["instructions"] = "Keep the user's consultation instructions."
        saved["41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72"] = sample
    elif existing_sample == "renamed_id":
        saved["a9b5cb3b-1e1e-4559-8f71-365c651d176d"] = sample
    save_records("criteria", saved)
    expected = deepcopy(saved)
    if existing_sample == "missing":
        expected["41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72"] = DEFAULT_PROFILES[
            "41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72"
        ]
    try:
        load_profiles()
        assert PROFILES == expected
        assert load_records("criteria") == expected
        load_profiles()
        assert PROFILES == expected
        assert load_records("criteria") == expected
    finally:
        PROFILES.clear()
        PROFILES.update(original)


def test_consultation_sample_is_korean_only() -> None:
    """Only Korean consultation templates are shipped, without language suffixes."""
    for identity in (
        "41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72",
        "1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d",
        "efb7c8ca-61c1-4785-b38d-0a86764ca758",
    ):
        profile = DEFAULT_PROFILES[identity]
        assert not profile["label"].endswith(" (KOR)")
        assert f"{identity}_eng" not in DEFAULT_PROFILES
        for question in profile["questions"].values():
            if question["type"] == "choice":
                assert all(
                    any("가" <= char <= "힣" for char in key)
                    for key in question["criteria"]
                )


def test_default_voc_source_points_to_bundled_sample() -> None:
    """The seeded VOC Source references an existing sample and content field."""
    source = next(item for item in load_sources() if item["id"] == VOC_SOURCE["id"])
    sample = Path(source["path"].removeprefix("/host-logs/"))
    assert source["name"] == "Sample VOC Asia Culture Center Consulting QnA"
    assert sample == Path("sample-logs/voc-asia-culture-center-consulting-qna.jsonl")
    assert source["format"] == "jsonl"
    with sample.open() as stream:
        record = json.loads(next(stream))
    assert isinstance(record[source["contentField"]], str)
    assert record[source["contentField"]].strip()


@pytest.mark.parametrize("existing", ["missing", "edited", "same_path"])
def test_startup_adds_voc_source_without_overwriting_existing_sources(
    existing: str,
) -> None:
    """Seed JSONL settings once and preserve edited or equivalent registrations."""
    sources = [{"id": "a" * 32, "name": "My Logs", "type": "local", "path": "/logs"}]
    if existing != "missing":
        source = {**VOC_SOURCE, "name": "My VOC"}
        if existing == "same_path":
            source["id"] = "b" * 32
        sources.append(source)
    save_sources(sources)
    expected = sources if existing != "missing" else [*sources, VOC_SOURCE]
    ensure_voc_source()
    assert load_sources() == expected
    ensure_voc_source()
    assert load_sources() == expected


def test_voc_task_is_manual_disabled_and_preserves_edits() -> None:
    """Connect the default JSONL Source to KOR without scheduling execution."""
    original = deepcopy(PROFILES)
    try:
        load_profiles()
        ensure_voc_source()
        ensure_voc_task()
        task = next(task for task in load_tasks() if task["id"] == VOC_TASK_ID)
        assert task["name"] == "Sample VOC Asia Culture Center Consulting QnA"
        ensure_voc_task()
        assert load_tasks() == [task]
        assert task["mode"] == "batch"
        assert task["enabled"] is False
        assert task["cron"] == ""
        assert task["resumeOnRestart"] is False
        assert task["sources"] == [
            {
                "sourceId": VOC_SOURCE["id"],
                "profile": "41bbe1dc-85cb-4ab0-ab79-cd7c4e6f8e72",
                "chunkEvents": 1,
                "actionId": "",
            }
        ]
        task["name"] = "My VOC Task"
        task["sources"][0]["profile"] = "4e6d5417-611e-49e0-8e23-2444a0f49ee4"
        save_record("tasks", VOC_TASK_ID, task)
        ensure_voc_task()
        assert load_tasks() == [task]
    finally:
        PROFILES.clear()
        PROFILES.update(original)


@pytest.mark.parametrize("existing_source", [False, True])
def test_system_message_task_reuses_source_and_preserves_edits(
    existing_source: bool,
) -> None:
    """Reuse the plural-path Source with Sample General System, without execution."""
    if existing_source:
        save_sources(
            [
                {
                    "id": "c" * 32,
                    "name": "Existing",
                    "type": "local",
                    "path": "/host-logs/var/log/messages",
                }
            ]
        )
    ensure_system_message_task()
    task = next(task for task in load_tasks() if task["id"] == SYSTEM_MESSAGE_TASK_ID)
    assert task["mode"] == "realtime"
    assert task["enabled"] is False
    assert task["resumeOnRestart"] is False
    assert task["sources"][0]["profile"] == "4e6d5417-611e-49e0-8e23-2444a0f49ee4"
    assert task["sources"][0]["chunkEvents"] == 1
    assert task["sources"][0]["actionId"] == ""
    source = next(
        s for s in load_sources() if s["id"] == task["sources"][0]["sourceId"]
    )
    assert source["path"] == "/host-logs/var/log/messages"
    if existing_source:
        assert source["id"] == "c" * 32
        assert len(load_sources()) == 1
    task["name"] = "My System Task"
    save_record("tasks", task["id"], task)
    ensure_system_message_task()
    assert load_tasks() == [task]


@pytest.mark.parametrize("existing", ["missing", "edited", "renamed_id"])
@pytest.mark.parametrize(
    "identity",
    ["1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d", "efb7c8ca-61c1-4785-b38d-0a86764ca758"],
)
def test_government_bootstrap_preserves_saved_settings(
    existing: str, identity: str
) -> None:
    """Seed both profiles and a disabled Batch once, preserving user records."""
    source_default = (
        CENTRAL_GOV_SOURCE
        if identity == "1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d"
        else LOCAL_GOV_SOURCE
    )
    task_id = (
        CENTRAL_GOV_TASK_ID
        if identity == "1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d"
        else LOCAL_GOV_TASK_ID
    )
    ensure_source = (
        ensure_central_gov_source
        if identity == "1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d"
        else ensure_local_gov_source
    )
    ensure_task = (
        ensure_central_gov_task
        if identity == "1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d"
        else ensure_local_gov_task
    )
    original = deepcopy(PROFILES)
    profiles = deepcopy(DEFAULT_PROFILES)
    sample = profiles.pop(identity)
    if existing == "edited":
        sample["instructions"] = "Keep my government criteria."
        profiles[identity] = sample
    elif existing == "renamed_id":
        profiles["a9b5cb3b-1e1e-4559-8f71-365c651d176d"] = sample
    save_records("criteria", profiles)
    source = {**source_default, "name": "My Government Source"}
    if existing == "renamed_id":
        source["id"] = "b" * 32
    save_sources([] if existing == "missing" else [source])
    try:
        load_profiles()
        ensure_source()
        ensure_task()
        sources = load_sources()
        assert len(sources) == 1
        selected = sources[0]
        assert selected == (source_default if existing == "missing" else source)
        task = next(task for task in load_tasks() if task["id"] == task_id)
        assert task["name"] == source_default["name"]
        ensure_task()
        assert load_tasks() == [task]
        assert task["mode"] == "batch"
        assert task["enabled"] is False
        assert task["resumeOnRestart"] is False
        assert task["cron"] == ""
        profile_id = (
            "a9b5cb3b-1e1e-4559-8f71-365c651d176d"
            if existing == "renamed_id"
            else identity
        )
        assert task["sources"] == [
            {
                "sourceId": selected["id"],
                "profile": profile_id,
                "chunkEvents": 1,
                "actionId": "",
            }
        ]
        if existing != "missing":
            assert PROFILES == profiles
        expected = deepcopy(PROFILES)
        task["name"] = "My Government Task"
        save_record("tasks", task["id"], task)
        load_profiles()
        ensure_source()
        ensure_task()
        assert PROFILES == expected
        assert load_sources() == sources
        assert load_tasks() == [task]
    finally:
        PROFILES.clear()
        PROFILES.update(original)


def test_central_gov_sample_and_localized_profiles() -> None:
    """The bundled QnA matches the Source and the two profiles share a schema."""
    sample = Path(CENTRAL_GOV_SOURCE["path"].removeprefix("/host-logs/"))
    with sample.open() as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    assert len(records) == 3965
    assert all(
        isinstance(row[CENTRAL_GOV_SOURCE["contentField"]], str) for row in records
    )
    korean = DEFAULT_PROFILES["1dd02d79-f43e-49ef-a1f1-7a2ddfab1e8d"]
    assert korean["label"] == "Sample VOC Central Gov Consulting QnA"
    assert korean["defaultDecision"] == "policy_area"
    assert set(korean["questions"]) == {
        "policy_area",
        "response_type",
        "follow_up_owner",
        "urgency",
        "follow_up_required",
    }
