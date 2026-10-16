"""Verify unified configuration persistence without legacy JSON imports."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

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
from source_registry import load_sources, save_sources
from tasks import DEFAULT_TASK_ID, ensure_default_task, load_tasks


def test_fresh_defaults_are_persisted_and_empty_lists_stay_empty() -> None:
    original = deepcopy(PROFILES)
    try:
        load_profiles()
        ensure_default_task()
        assert load_tasks()[0]["id"] == DEFAULT_TASK_ID
        assert load_tasks()[0]["enabled"] is False
        assert len(load_sources()) == 4
        assert load_settings() == {"resultsPerPage": 50}
        with sqlite3.connect(get_database_path()) as connection:
            counts = dict(
                connection.execute(
                    "SELECT kind,COUNT(*) FROM configuration_records GROUP BY kind"
                )
            )
        assert counts == {"sources": 4, "criteria": 5, "tasks": 1, "settings": 1}
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
        assert load_settings()["resultsPerPage"] == 50
        assert load_records("criteria") == DEFAULT_PROFILES
        assert len(load_sources()) == 4
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
                "resultsPerPage": 50
            }
