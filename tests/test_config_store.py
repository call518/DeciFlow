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
    VOC_SOURCE,
    ensure_voc_source,
    load_sources,
    save_sources,
)
from tasks import (
    DEFAULT_TASK_ID,
    SYSTEM_MESSAGE_SOURCE_ID,
    SYSTEM_MESSAGE_TASK_ID,
    VOC_TASK_ID,
    ensure_default_task,
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
        assert len(load_sources()) == 5
        assert load_settings() == {"resultsPerPage": 10}
        with sqlite3.connect(get_database_path()) as connection:
            counts = dict(
                connection.execute(
                    "SELECT kind,COUNT(*) FROM configuration_records GROUP BY kind"
                )
            )
        assert counts == {"sources": 5, "criteria": 7, "tasks": 1, "settings": 1}
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
        assert load_settings()["resultsPerPage"] == 10
        assert load_records("criteria") == DEFAULT_PROFILES
        assert len(load_sources()) == 5
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
                "resultsPerPage": 10
            }


@pytest.mark.parametrize("existing_sample", ["missing", "edited", "renamed_id"])
def test_startup_ensures_consultation_without_overwriting_saved_profiles(
    existing_sample: str,
) -> None:
    """Old installations receive the sample once and retain all user edits."""
    original = deepcopy(PROFILES)
    saved = deepcopy(DEFAULT_PROFILES)
    sample = saved.pop("consultation")
    saved["general"]["instructions"] = "Keep the user's instructions."
    if existing_sample == "edited":
        sample["instructions"] = "Keep the user's consultation instructions."
        saved["consultation"] = sample
    elif existing_sample == "renamed_id":
        saved["custom_consultation"] = sample
    save_records("criteria", saved)
    expected = deepcopy(saved)
    if existing_sample == "missing":
        expected["consultation"] = DEFAULT_PROFILES["consultation"]
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


@pytest.mark.parametrize("edited", [False, True])
def test_english_consultation_updates_only_when_untouched(edited: bool) -> None:
    """Translate the shipped sample without replacing user edits or its ID."""
    original = deepcopy(PROFILES)
    saved = deepcopy(DEFAULT_PROFILES)
    legacy = json.loads(
        (Path(__file__).parent / "fixtures/consultation-english.json").read_text()
    )
    if edited:
        legacy["instructions"] = "My custom instructions."
    saved["consultation"] = legacy
    save_records("criteria", saved)
    try:
        load_profiles()
        expected = legacy if edited else DEFAULT_PROFILES["consultation"]
        assert PROFILES["consultation"] == expected
        assert load_records("criteria")["consultation"] == expected
        assert set(PROFILES) == set(saved)
        if not edited:
            assert expected["label"] == "VOC Consultation Review (KOR)"
            assert expected["questions"]["inquiry_type"]["label"] == "문의 유형"
    finally:
        PROFILES.clear()
        PROFILES.update(original)


@pytest.mark.parametrize("old_label", ["VOC 상담 판단", "VOC 상담 판단 (KOR)"])
def test_existing_korean_sample_gets_language_label_and_english_sample(
    old_label: str,
) -> None:
    """Upgrade the unedited Korean sample and add its English counterpart."""
    original = deepcopy(PROFILES)
    saved = deepcopy(DEFAULT_PROFILES)
    saved.pop("consultation_eng")
    saved["consultation"] = json.loads(
        (
            Path(__file__).parent / "fixtures/consultation-korean-english-options.json"
        ).read_text()
    )
    saved["consultation"]["label"] = old_label
    save_records("criteria", saved)
    try:
        load_profiles()
        assert PROFILES == DEFAULT_PROFILES
        assert load_records("criteria") == DEFAULT_PROFILES
        load_profiles()
        assert PROFILES == DEFAULT_PROFILES
    finally:
        PROFILES.clear()
        PROFILES.update(original)


def test_consultation_languages_share_decision_structure() -> None:
    """Both samples keep decision IDs and structure while localizing option names."""
    korean = DEFAULT_PROFILES["consultation"]
    english = DEFAULT_PROFILES["consultation_eng"]
    assert korean["primaryQuestion"] == english["primaryQuestion"]
    assert list(korean["questions"]) == list(english["questions"])
    for identity, question in korean["questions"].items():
        translated = english["questions"][identity]
        assert question["type"] == translated["type"]
        assert question["summary"] == translated["summary"]
        if question["type"] == "choice":
            assert len(question["criteria"]) == len(translated["criteria"])
            assert all(
                any("가" <= char <= "힣" for char in key)
                for key in question["criteria"]
            )
        elif question["type"] == "score":
            assert len(question["criteria"]) == len(translated["criteria"])
        assert question["label"] != translated["label"]
        assert question["instructions"] != translated["instructions"]


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
        assert task["mode"] == "batch"
        assert task["enabled"] is False
        assert task["cron"] == ""
        assert task["resumeOnRestart"] is False
        assert task["sources"] == [
            {
                "sourceId": VOC_SOURCE["id"],
                "profile": "consultation",
                "chunkEvents": 1,
                "actionId": "",
            }
        ]
        task["name"] = "My VOC Task"
        task["sources"][0]["profile"] = "consultation_eng"
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
    """Reuse the plural-path Source with General system, without execution."""
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
    assert task["sources"][0]["profile"] == "general"
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


@pytest.mark.parametrize("edited_legacy", [False, True])
def test_system_messages_duplicate_repair_preserves_custom_settings(
    edited_legacy: bool,
) -> None:
    """Only the exact erroneous sample is removed; all Task assignments survive."""
    canonical = {
        "id": f"{1:032x}",
        "name": "System messages",
        "type": "ssh",
        "path": "/custom/remote/messages",
    }
    legacy = {
        "id": SYSTEM_MESSAGE_SOURCE_ID,
        "name": "System Message",
        "type": "local",
        "path": "/host-logs/var/log/message",
        "format": "text",
    }
    if edited_legacy:
        legacy["path"] = "/my/log"
    save_sources([canonical, legacy])
    task = {
        "id": SYSTEM_MESSAGE_TASK_ID,
        "name": "System Message",
        "enabled": True,
        "mode": "realtime",
        "sources": [
            {
                "sourceId": SYSTEM_MESSAGE_SOURCE_ID,
                "profile": "general",
                "chunkEvents": 3,
                "actionId": "custom-action",
            }
        ],
    }
    other = {**deepcopy(task), "id": "other", "name": "My Task"}
    save_record("tasks", task["id"], task)
    save_record("tasks", other["id"], other)
    ensure_system_message_task()
    records = {item["id"]: item for item in load_tasks()}
    assert records[SYSTEM_MESSAGE_TASK_ID]["name"] == "System Messages"
    for record in records.values():
        assert record["enabled"] is True
        assert record["sources"][0] == {
            **task["sources"][0],
            "sourceId": SYSTEM_MESSAGE_SOURCE_ID if edited_legacy else canonical["id"],
        }
    assert load_sources() == ([canonical, legacy] if edited_legacy else [canonical])
    ensure_system_message_task()
    assert {item["id"]: item for item in load_tasks()} == records


@pytest.mark.parametrize("edited", [False, True])
def test_korean_option_sample_updates_only_when_untouched(edited: bool) -> None:
    """Localized options replace only the unedited shipped sample."""
    original = deepcopy(PROFILES)
    values = deepcopy(DEFAULT_PROFILES)
    legacy = json.loads(
        (
            Path(__file__).parent / "fixtures/consultation-korean-english-options.json"
        ).read_text()
    )
    if edited:
        legacy["instructions"] = "Keep custom rules."
    values["consultation"] = legacy
    save_records("criteria", values)
    try:
        load_profiles()
        assert PROFILES["consultation"] == (
            legacy if edited else DEFAULT_PROFILES["consultation"]
        )
        assert load_records("criteria")["consultation"] == PROFILES["consultation"]
    finally:
        PROFILES.clear()
        PROFILES.update(original)
