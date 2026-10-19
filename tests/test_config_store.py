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
    SYSTEM_MESSAGE_SOURCE_ID,
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
            assert expected["label"] == "Sample VOC Asia Culture Center Consulting QnA"
            assert expected["questions"]["inquiry_type"]["label"] == "문의 유형"
    finally:
        PROFILES.clear()
        PROFILES.update(original)


@pytest.mark.parametrize("old_label", ["VOC 상담 판단", "VOC 상담 판단 (KOR)"])
def test_existing_korean_sample_is_updated_without_language_suffix(
    old_label: str,
) -> None:
    """Upgrade the unedited sample without adding an English counterpart."""
    original = deepcopy(PROFILES)
    saved = deepcopy(DEFAULT_PROFILES)
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


def test_consultation_sample_is_korean_only() -> None:
    """Only Korean consultation templates are shipped, without language suffixes."""
    for identity in ("consultation", "central_gov", "local_gov"):
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
        save_record("tasks", task["id"], {**task, "name": f"{task['name']} (KOR)"})
        ensure_voc_task()
        assert load_tasks() == [task]
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
        task["sources"][0]["profile"] = "general"
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
        "name": "Sample System Messages",
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
    assert records[SYSTEM_MESSAGE_TASK_ID]["name"] == "Sample System Messages"
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


@pytest.mark.parametrize("existing", ["missing", "edited", "renamed_id"])
@pytest.mark.parametrize("identity", ["central_gov", "local_gov"])
def test_government_bootstrap_preserves_saved_settings(
    existing: str, identity: str
) -> None:
    """Seed both profiles and a disabled Batch once, preserving user records."""
    source_default = (
        CENTRAL_GOV_SOURCE if identity == "central_gov" else LOCAL_GOV_SOURCE
    )
    task_id = CENTRAL_GOV_TASK_ID if identity == "central_gov" else LOCAL_GOV_TASK_ID
    ensure_source = (
        ensure_central_gov_source
        if identity == "central_gov"
        else ensure_local_gov_source
    )
    ensure_task = (
        ensure_central_gov_task if identity == "central_gov" else ensure_local_gov_task
    )
    original = deepcopy(PROFILES)
    profiles = deepcopy(DEFAULT_PROFILES)
    sample = profiles.pop(identity)
    if existing == "edited":
        sample["instructions"] = "Keep my government criteria."
        profiles[identity] = sample
    elif existing == "renamed_id":
        profiles[f"custom_{identity}"] = sample
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
        save_record("tasks", task["id"], {**task, "name": f"{task['name']} (KOR)"})
        ensure_task()
        assert load_tasks() == [task]
        assert task["mode"] == "batch"
        assert task["enabled"] is False
        assert task["resumeOnRestart"] is False
        assert task["cron"] == ""
        profile_id = f"custom_{identity}" if existing == "renamed_id" else identity
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
    korean = DEFAULT_PROFILES["central_gov"]
    assert korean["label"] == "Sample VOC Central Gov Consulting QnA"
    assert korean["primaryQuestion"] == "policy_area"
    assert set(korean["questions"]) == {
        "policy_area",
        "response_type",
        "follow_up_owner",
        "urgency",
        "follow_up_required",
    }


@pytest.mark.parametrize("renamed_id", [False, True])
@pytest.mark.parametrize("identity", ["consultation", "central_gov"])
def test_retired_english_sample_relinks_tasks_and_preserves_custom_profiles(
    identity: str,
    renamed_id: bool,
) -> None:
    """Remove shipped English Criteria and preserve custom profile definitions."""
    original = deepcopy(PROFILES)
    saved = deepcopy(DEFAULT_PROFILES)
    saved[identity]["label"] += " (KOR)"
    saved[identity]["instructions"] = "Keep my Korean edits."
    english_id = f"{identity}_eng"
    saved[english_id] = {**deepcopy(saved[identity]), "label": "Old English sample"}
    saved["custom_english"] = {
        **deepcopy(saved[identity]),
        "label": "My English Criteria",
    }
    target = f"custom_{identity}" if renamed_id else identity
    if renamed_id:
        saved[target] = saved.pop(identity)
        saved[target]["label"] = DEFAULT_PROFILES[identity]["label"]
    save_records("criteria", saved)
    task = {"id": "a" * 32, "name": "My Task", "sources": [{"profile": english_id}]}
    save_record("tasks", task["id"], task)
    try:
        load_profiles()
        assert english_id not in PROFILES
        assert PROFILES[target]["label"] == DEFAULT_PROFILES[identity]["label"]
        assert PROFILES[target]["instructions"] == "Keep my Korean edits."
        assert PROFILES["custom_english"] == saved["custom_english"]
        expected = {**task, "sources": [{"profile": target}]}
        assert load_tasks() == [expected]
        assert load_records("criteria") == PROFILES
        load_profiles()
        assert load_tasks() == [expected]
    finally:
        PROFILES.clear()
        PROFILES.update(original)


@pytest.mark.parametrize("saved_names", ["legacy", "custom"])
def test_sample_names_migrate_without_changing_configuration(saved_names: str) -> None:
    """Rename shipped labels across registries while preserving settings and IDs."""
    from actions import load_actions

    original = deepcopy(PROFILES)
    try:
        load_profiles()
        ensure_default_task()
        ensure_voc_task()
        ensure_central_gov_task()
        ensure_local_gov_task()
        ensure_system_message_task()
        registries = {
            "sources": {row["id"]: row for row in load_sources()},
            "criteria": deepcopy(PROFILES),
            "tasks": {row["id"]: row for row in load_tasks()},
            "actions": {row["id"]: row for row in load_actions()},
        }
        expected = deepcopy(registries)
        for kind, records in registries.items():
            field = "label" if kind == "criteria" else "name"
            for identity, row in records.items():
                assert row[field].startswith("Sample ")
                if kind == "criteria":
                    row["instructions"] = "Keep my rules."
                    expected[kind][identity]["instructions"] = "Keep my rules."
                if saved_names == "custom":
                    row[field] = f"My {row[field]}"
                    expected[kind][identity][field] = row[field]
                elif (
                    row[field].startswith("Sample VOC ")
                    or row[field]
                    in {
                        "Sample General System",
                        "Sample System Messages",
                        "Sample Elasticsearch",
                    }
                    or (kind == "tasks" and row[field] == "Sample DeciFlow Server Log")
                ):
                    row[field] = row[field].removeprefix("Sample ")
                    if kind == "criteria" and identity == "general":
                        row[field] = "General system"
                    if kind == "sources" and row[field] == "System Messages":
                        row[field] = "System messages"
            save_records(kind, records)
        for _ in range(2):
            load_profiles()
            load_sources()
            load_actions()
            ensure_default_task()
            ensure_voc_task()
            ensure_central_gov_task()
            ensure_local_gov_task()
            ensure_system_message_task()
            for kind, records in expected.items():
                assert load_records(kind) == records
    finally:
        PROFILES.clear()
        PROFILES.update(original)


def test_sample_name_migration_preserves_name_collisions() -> None:
    """Do not overwrite a user record that already owns the new sample name."""
    from config_store import rename_sample_records

    records = {
        "old": {"name": "Original", "setting": 1},
        "custom": {"name": "Sample Original", "setting": 2},
    }
    save_records("sources", records)
    expected = deepcopy(records)
    rename_sample_records("sources", records, {"Original": "Sample Original"})
    assert records == expected
    assert load_records("sources") == expected
