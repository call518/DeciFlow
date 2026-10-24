"""Verify installed CLI setup, configuration isolation, and actionable failures."""

import os
import sys
from pathlib import Path

import pytest

from deciflow import cli, cli_config, server


@pytest.fixture(autouse=True)
def preserve_process_invocation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "orig_argv", list(sys.orig_argv))
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    monkeypatch.setenv("DECIFLOW_LOG_DIR", str(tmp_path / "logs"))

    async def available(engine: object) -> None:
        pass

    monkeypatch.setattr(cli_config, "probe_engine", available)
    monkeypatch.setattr(cli_config, "check_listener", lambda host, port: None)
    monkeypatch.setattr(cli_config, "require_executable", lambda name: None)


def test_workspace_templates_preserve_user_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert cli.prepare_workspace(workspace)
    env = workspace / ".env"
    text = env.read_text()
    assert "LAYA_API_URL=http://127.0.0.1:8000/v1/systemone" in text
    assert "DECIFLOW_DATA_DIR=\n" in text
    assert "DECIFLOW_LOG_DIR=/var/log/deciflow\n" in text
    assert env.stat().st_mode & 0o777 == 0o600
    env.write_text("JEV_API_KEY=disposable-user-value\n")
    policy = workspace / "oauth2-proxy" / "oauth2-proxy.cfg"
    policy.write_text("custom-policy")
    assert not cli.prepare_workspace(workspace)
    assert env.read_text() == "JEV_API_KEY=disposable-user-value\n"
    assert policy.read_text() == "custom-policy"


def test_init_creates_templates_without_starting_or_testing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr("sys.argv", ["deciflow", "init", "--config-dir", str(tmp_path)])
    monkeypatch.setattr(
        cli_config, "run_config_test", lambda path: pytest.fail("init must not test")
    )
    monkeypatch.setattr(
        server, "main", lambda **kwargs: pytest.fail("init must not start")
    )
    cli.main()
    output = capsys.readouterr().out
    assert "Created" in output and "config test" in output


@pytest.mark.parametrize("key", ["DECIFLOW_DATA_DIR", "DECIFLOW_LOG_DIR"])
def test_missing_storage_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str
) -> None:
    missing = tmp_path / "missing"
    monkeypatch.setenv(key, str(missing))
    with pytest.raises(ValueError, match=f"{key} directory does not exist"):
        cli.check_storage_directory(key, missing)
    assert not missing.exists()
    assert os.environ[key] == str(missing)


def test_unwritable_storage_has_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def denied(**kwargs: object) -> None:
        raise PermissionError("test permission denied")

    monkeypatch.setattr(cli.tempfile, "TemporaryFile", denied)
    with pytest.raises(ValueError, match="Cannot write to DECIFLOW_DATA_DIR"):
        cli.check_storage_directory(
            "DECIFLOW_DATA_DIR", cli.storage_directories()[0][1]
        )


def test_empty_log_directory_keeps_console_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECIFLOW_LOG_DIR", "")
    assert all(key != "DECIFLOW_LOG_DIR" for key, _ in cli.storage_directories())


@pytest.mark.parametrize("engine", ["laya", "jev"])
def test_cli_runs_native_server_from_workspace(
    engine: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        f"DECISION_ENGINE={engine}\nJEV_API_KEY=disposable-test-key\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["deciflow", "start", "--config-dir", str(tmp_path)]
    )
    monkeypatch.setattr(server, "ROOT", server.ROOT)
    called = []
    monkeypatch.setattr(server, "main", lambda **kwargs: called.append(kwargs))
    cli.main()
    assert server.ROOT == tmp_path
    assert Path.cwd() == tmp_path
    assert os.environ["DECISION_ENGINE"] == engine
    assert called[0]["manage_proxy"] is True
    assert callable(called[0]["on_started"])
    assert not called[0]["stop"].is_set()
    assert sys.orig_argv[-2:] == ["--config-dir", str(tmp_path)]


def test_relative_workspace_survives_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("DECISION_ENGINE=laya\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["deciflow", "start", "--config-dir", "workspace"])
    monkeypatch.setattr(server, "ROOT", server.ROOT)
    monkeypatch.setattr(server, "main", lambda **kwargs: None)
    cli.main()
    assert Path.cwd() == workspace
    assert sys.orig_argv == [
        sys.executable,
        "-m",
        "deciflow.cli",
        "start",
        "--config-dir",
        str(workspace),
    ]


def test_missing_jev_key_stops_with_guidance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    (tmp_path / ".env").write_text("DECISION_ENGINE=jev\nJEV_API_KEY=\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["deciflow", "start", "--config-dir", str(tmp_path)]
    )
    monkeypatch.setattr(server, "ROOT", server.ROOT)
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 1
    output = capsys.readouterr()
    assert "Config Test Failed" in output.out
    assert "Run: deciflow config test" in output.err


def test_server_startup_exit_points_to_configtest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    (tmp_path / ".env").write_text("DECISION_ENGINE=laya\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["deciflow", "start", "--config-dir", str(tmp_path)]
    )
    monkeypatch.setattr(server, "ROOT", server.ROOT)

    def fail(**kwargs: object) -> None:
        raise SystemExit(1)

    monkeypatch.setattr(server, "main", fail)
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1
    assert "Run: deciflow config test" in capsys.readouterr().err


def test_runtime_does_not_create_missing_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["deciflow", "start", "--config-dir", str(tmp_path)]
    )
    monkeypatch.setattr(
        server, "main", lambda **kwargs: pytest.fail("failed test must block runtime")
    )
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1
    assert not (tmp_path / ".env").exists()
    assert "deciflow init" in capsys.readouterr().err


@pytest.mark.parametrize("status", [0, 1])
def test_configuration_check_gates_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: int
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["deciflow", "start", "--config-dir", str(tmp_path)]
    )
    monkeypatch.setattr(server, "ROOT", server.ROOT)
    events = []

    def check(path: Path, *, detailed: bool = True) -> int:
        assert not detailed
        events.append("test")
        return status

    monkeypatch.setattr(cli_config, "run_config_test", check)
    monkeypatch.setattr(server, "main", lambda **kwargs: events.append("runtime"))
    if status:
        with pytest.raises(SystemExit) as result:
            cli.main()
        assert result.value.code == 1 and events == ["test"]
    else:
        cli.main()
        assert events == ["test", "runtime"]


@pytest.mark.parametrize("position", [0, 1, 2])
def test_config_directory_option_at_each_command_level(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, position: int
) -> None:
    args = ["config", "list"]
    args[position:position] = ["--config-dir", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", ["deciflow", *args])
    calls = []
    monkeypatch.setattr(
        cli_config, "list_configuration", lambda path: calls.append(path)
    )
    monkeypatch.setattr(
        cli_config, "run_config_test", lambda path: pytest.fail("list must not test")
    )
    cli.main()
    assert calls == [tmp_path]


def test_no_command_shows_help_without_testing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["deciflow"])
    monkeypatch.setattr(
        cli_config,
        "run_config_test",
        lambda *args, **kwargs: pytest.fail("help must not test"),
    )
    cli.main()
    assert "start" in capsys.readouterr().out


def test_run_is_not_a_start_alias(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["deciflow", "run"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 2
    assert "invalid choice: 'run'" in capsys.readouterr().err
