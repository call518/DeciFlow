"""Check aggregate diagnostics, safe probes, and configuration preservation."""

import base64
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from dotenv import dotenv_values

from deciflow import cli, cli_config
from deciflow.config import Engine
from deciflow.config_store import save_records


@pytest.fixture
def configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, list[str]]:
    directory = tmp_path / "settings"
    directory.mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    path = directory / ".env"
    path.write_text(
        "DECISION_ENGINE=laya\nLAYA_API_URL=http://engine.test/v1/systemone\n"
        "OAUTH2_PROXY_ENABLED=false\n"
        f"DECIFLOW_DATA_DIR={tmp_path / 'data'}\n"
        f"DECIFLOW_LOG_DIR={tmp_path / 'logs'}\n"
    )
    for key in [*dotenv_values(path), "JEV_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DECIFLOW_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("NO_COLOR", raising=False)
    calls = []

    async def probe(engine: Engine) -> None:
        calls.append(engine.name)

    monkeypatch.setattr(cli_config, "probe_engine", probe)
    monkeypatch.setattr(cli_config, "check_listener", lambda host, port: None)
    monkeypatch.setattr(cli_config, "require_executable", lambda name: None)
    return directory, calls


def test_success_is_read_only_and_restores_working_directory(
    configuration: tuple[Path, list[str]], capsys: pytest.CaptureFixture
) -> None:
    directory, calls = configuration
    original = Path.cwd()
    env = (directory / ".env").read_bytes()
    assert cli_config.run_config_test(directory) == 0
    output = capsys.readouterr().out
    assert "[Passed] Laya Connection" in output
    assert "[Passed] OAuth2-Proxy Disabled" in output
    assert "Config Test Passed" in output
    assert "\033[" not in output
    assert calls == ["laya"]
    assert Path.cwd() == original
    assert (directory / ".env").read_bytes() == env
    assert not (directory.parent / "data" / "deciflow.sqlite3").exists()
    assert not (directory / "oauth2-proxy").exists()


def test_failures_do_not_stop_other_checks_and_have_terminal_colors(
    configuration: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    directory, calls = configuration
    (directory.parent / "data").rmdir()
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert cli_config.run_config_test(directory) == 1
    output = capsys.readouterr().out
    assert "\033[91mFailed\033[0m] DECIFLOW_DATA_DIR" in output
    assert "\033[32mPassed\033[0m] DECIFLOW_LOG_DIR" in output
    assert "Config Test \033[91mFailed" in output
    assert calls == ["laya"]


def test_missing_workspace_is_not_created(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    directory = tmp_path / "missing"
    assert cli_config.run_config_test(directory) == 1
    assert not directory.exists()
    assert "Config Test Failed" in capsys.readouterr().out


def test_invalid_env_does_not_print_secret(
    configuration: tuple[Path, list[str]], capsys: pytest.CaptureFixture
) -> None:
    directory, calls = configuration
    secret = "disposable-malformed-secret"
    (directory / ".env").write_text(f'JEV_API_KEY="{secret}\n')
    assert cli_config.run_config_test(directory) == 1
    output = capsys.readouterr().out
    assert "[Failed] Environment File" in output
    assert secret not in output and calls == []


def test_saved_ui_engine_is_checked(
    configuration: tuple[Path, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, calls = configuration
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(directory.parent / "data"))
    monkeypatch.setenv("JEV_API_KEY", "disposable-test-key")
    save_records(
        "settings", {"application": {"runtimeOverrides": {"DECISION_ENGINE": "jev"}}}
    )
    assert cli_config.run_config_test(directory) == 0
    assert calls == ["jev"]


def test_enabled_proxy_reports_all_missing_prerequisites(
    configuration: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    directory, _ = configuration
    path = directory / ".env"
    path.write_text(
        path.read_text().replace(
            "OAUTH2_PROXY_ENABLED=false", "OAUTH2_PROXY_ENABLED=true"
        )
    )
    for key in (
        "OAUTH2_PROXY_CLIENT_ID",
        "OAUTH2_PROXY_CLIENT_SECRET",
        "OAUTH2_PROXY_COOKIE_SECRET",
        "OAUTH2_PROXY_PUBLIC_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    assert cli_config.run_config_test(directory) == 1
    output = capsys.readouterr().out
    for label in (
        "OAuth2-Proxy Client ID",
        "OAuth2-Proxy Client Secret",
        "OAuth2-Proxy Cookie Secret",
        "Public HTTPS Origin",
        "OAuth2-Proxy Policy",
        "Email Allow-List",
        "TLS Certificate and Key",
    ):
        assert f"[Failed] {label}" in output


@pytest.mark.parametrize("valid", [False, True])
def test_cookie_key_validation_does_not_expose_value(
    monkeypatch: pytest.MonkeyPatch, valid: bool
) -> None:
    monkeypatch.setenv(
        "OAUTH2_PROXY_COOKIE_SECRET",
        base64.urlsafe_b64encode(b"x" * (32 if valid else 3)).decode(),
    )
    if valid:
        cli_config.validate_proxy_setting("OAUTH2_PROXY_COOKIE_SECRET")
    else:
        with pytest.raises(ValueError, match="16, 24, or 32"):
            cli_config.validate_proxy_setting("OAUTH2_PROXY_COOKIE_SECRET")


@pytest.mark.parametrize(
    "expired, hostname",
    [
        (False, "demo.example.test"),
        (True, "demo.example.test"),
        (False, "wrong.example.test"),
    ],
)
def test_tls_dates_and_public_hostname(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, expired: bool, hostname: str
) -> None:
    directory = tmp_path / "tls"
    directory.mkdir()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "demo.example.test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=-1 if expired else 1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("demo.example.test")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (directory / "fullchain.pem").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
    )
    (directory / "privkey.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setenv("OAUTH2_PROXY_PUBLIC_URL", f"https://{hostname}")
    if expired or hostname != "demo.example.test":
        with pytest.raises(ValueError, match="expired|does not match"):
            cli_config.check_tls(tmp_path)
    else:
        cli_config.check_tls(tmp_path)


def test_cli_dispatch_does_not_initialize_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "missing"
    monkeypatch.setattr(
        sys, "argv", ["deciflow", "config", "test", "--config-dir", str(directory)]
    )
    monkeypatch.setattr(cli_config, "run_config_test", lambda path: 1)
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 1 and not directory.exists()


@pytest.mark.parametrize(
    "address, valid",
    [("0.0.0.0:4443", True), ("0.0.0.0:4000", False), ("invalid", False)],
)
def test_proxy_policy_checks_listener_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, address: str, valid: bool
) -> None:
    monkeypatch.setenv("PORT", "4000")
    path = tmp_path / "policy.cfg"
    path.write_text(f'provider="google"\nemail_domains=[]\nhttps_address="{address}"\n')
    if valid:
        assert cli_config.read_proxy_policy(path)["https_address"] == address
    else:
        with pytest.raises(ValueError, match="port|https_address"):
            cli_config.read_proxy_policy(path)


def test_config_list_redacts_secrets_and_does_not_create_database(
    configuration: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    directory, calls = configuration
    path = directory / ".env"
    for key in (
        "JEV_API_KEY",
        "OAUTH2_PROXY_CLIENT_SECRET",
        "OAUTH2_PROXY_COOKIE_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    path.write_text(
        path.read_text() + "JEV_API_KEY=disposable-private-key\n"
        "OAUTH2_PROXY_CLIENT_SECRET=disposable-client-secret\n"
        "OAUTH2_PROXY_COOKIE_SECRET=disposable-cookie-secret\n"
        "LAYA_API_URL=https://user:url-password@engine.test/v1/systemone?token=query-secret#fragment-secret\n"
    )
    before = path.read_bytes()
    original = Path.cwd()
    cli_config.list_configuration(directory)
    output = capsys.readouterr().out
    for value in (
        "disposable-private-key",
        "disposable-client-secret",
        "disposable-cookie-secret",
        "url-password",
        "query-secret",
        "fragment-secret",
    ):
        assert value not in output
    assert "JEV_API_KEY=[Redacted]" in output
    assert "engine.test/v1/systemone" in output
    assert calls == [] and Path.cwd() == original
    assert path.read_bytes() == before
    assert not (directory.parent / "data" / "deciflow.sqlite3").exists()


def test_config_list_shows_saved_override_source(
    configuration: tuple[Path, list[str]], capsys: pytest.CaptureFixture
) -> None:
    directory, calls = configuration
    save_records(
        "settings", {"application": {"runtimeOverrides": {"LAYA_MODEL": "english"}}}
    )
    cli_config.list_configuration(directory)
    assert "LAYA_MODEL=english [UI Override]" in capsys.readouterr().out
    assert calls == []


@pytest.mark.parametrize("failure", [False, True])
def test_startup_report_only_shows_summary(
    configuration: tuple[Path, list[str]], capsys: pytest.CaptureFixture, failure: bool
) -> None:
    directory, calls = configuration
    if failure:
        (directory.parent / "data").rmdir()
    assert cli_config.run_config_test(directory, detailed=False) == int(failure)
    output = capsys.readouterr().out
    assert f"Config Test {'Failed' if failure else 'Passed'}" in output
    assert "[Passed]" not in output and "[Failed]" not in output
    assert "Create this directory" not in output and "Setup guide" not in output
    assert calls == ["laya"]


@pytest.mark.parametrize("error_type", [ValueError, OSError, RuntimeError])
def test_diagnostics_do_not_print_exception_values(
    configuration: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    error_type: type[Exception],
) -> None:
    directory, calls = configuration
    secret = "disposable-exception-credential"

    def fail() -> None:
        raise error_type(f"Invalid setting: {secret}")

    monkeypatch.setattr(cli_config, "check_resources", fail)
    assert cli_config.run_config_test(directory) == 1
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "[Failed] Application Resources" in captured.out
    assert "Config Test Failed" in captured.out
    assert calls == ["laya"]


@pytest.mark.parametrize(
    "key, value, label",
    [
        ("OAUTH2_PROXY_CLIENT_ID", "disposable-client-id", "Client ID"),
        ("OAUTH2_PROXY_CLIENT_SECRET", "disposable-client-value", "Client Secret"),
        (
            "OAUTH2_PROXY_COOKIE_SECRET",
            base64.urlsafe_b64encode(b"x" * 32).decode(),
            "Cookie Secret",
        ),
    ],
)
def test_proxy_validation_never_returns_or_prints_setting_values(
    configuration: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    key: str,
    value: str,
    label: str,
) -> None:
    directory, _ = configuration
    path = directory / ".env"
    path.write_text(
        path.read_text().replace(
            "OAUTH2_PROXY_ENABLED=false", "OAUTH2_PROXY_ENABLED=true"
        )
    )
    monkeypatch.setenv(key, value)
    assert cli_config.validate_proxy_setting(key) is None
    # Other missing proxy prerequisites may fail; this credential must pass safely.
    assert cli_config.run_config_test(directory) == 1
    captured = capsys.readouterr()
    assert f"[Passed] OAuth2-Proxy {label}" in captured.out
    assert value not in captured.out + captured.err
