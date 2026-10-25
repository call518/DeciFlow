"""Validate both access modes without starting containers."""

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def compose_project(tmp_path: Path) -> Path:
    """Validate public deployment files without the developer's private .env."""
    shutil.copytree(ROOT / "compose", tmp_path / "compose")
    shutil.copy(ROOT / "docker-compose.yml", tmp_path / "docker-compose.yml")
    (tmp_path / ".env").touch()
    return tmp_path


@pytest.mark.parametrize("profile", ["cpu", "cuda", ""])
def test_compose_deployment(
    profile: str, tmp_path: Path, compose_project: Path
) -> None:
    """Select only the requested engine and preserve mounts and GPU isolation."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required for configuration validation")
    version = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, check=False
    )
    if version.returncode:
        pytest.skip("Docker Compose is required for configuration validation")
    env_file = tmp_path / "compose.env"
    env_file.write_text(
        f"COMPOSE_PROFILES={profile}\n"
        "OAUTH2_PROXY_ENABLED=true\n"
        "PORT=4567\n"
        "LAYA_API_KEY=compose-test-key\n"
        "DECIFLOW_DATA_DIR=/custom/data\n"
        "DECIFLOW_LOG_DIR=/custom/logs\n"
        "OAUTH2_PROXY_PUBLIC_URL=https://deciflow.example.com:4443\n"
        "OAUTH2_PROXY_CLIENT_ID=test-client\n"
        "OAUTH2_PROXY_CLIENT_SECRET=test-secret\n"
        "OAUTH2_PROXY_COOKIE_SECRET=test-cookie-secret\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COMPOSE_", "LAYA_", "DECIFLOW_", "OAUTH2_"))
        and key != "PORT"
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "config",
            "--no-env-resolution",
            "--format",
            "json",
        ],
        cwd=compose_project,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    services = config["services"]
    assert set(services) == (
        {"ui", "oauth2-proxy", f"laya-{profile}"} if profile else {"ui", "oauth2-proxy"}
    )
    ui = services["ui"]
    assert ui["image"] == "call518/deciflow-ui:0.0.2"
    assert not ui.get("ports")
    assert ui["environment"]["DECIFLOW_DATA_DIR"] == "/custom/data"
    mounts = {mount["target"]: mount for mount in ui["volumes"]}
    assert mounts["/app"]["read_only"] is True
    assert mounts["/host-logs/var/log"]["read_only"] is True
    assert mounts["/custom/data"]["source"] == "data"
    assert mounts["/custom/logs"]["source"] == "logs"
    assert config["volumes"]["data"]["name"] == "deciflow-data"
    if not profile:
        assert "laya-model-cache" not in config["volumes"]
        return
    assert config["volumes"]["laya-model-cache"]["name"] == (
        "deciflow-laya-model-cache"
    )
    laya = services[f"laya-{profile}"]
    assert laya["image"] == f"call518/deciflow-laya-{profile}:0.0.1"
    assert laya["environment"]["LAYA_DEVICE"] == profile
    assert laya["environment"]["LAYA_API_KEY"] == "compose-test-key"
    assert "laya" in laya["networks"]["default"]["aliases"]
    assert laya["ports"][0]["published"] == "8000"
    if profile == "cpu":
        assert "deploy" not in laya
        assert "gpus" not in laya
        return
    devices = laya["deploy"]["resources"]["reservations"]["devices"]
    assert devices == [{"driver": "nvidia", "count": -1, "capabilities": ["gpu"]}]


@pytest.mark.parametrize("profile", ["cpu", "cuda", ""])
@pytest.mark.parametrize(
    "extra_origins", ["", "https://admin.example.com,https://console.example.com"]
)
def test_google_auth_compose(
    profile: str, extra_origins: str, tmp_path: Path, compose_project: Path
) -> None:
    """Protect all UI routes without exposing an alternate application port."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required for configuration validation")
    env_file = tmp_path / "oauth2.env"
    env_file.write_text(
        f"COMPOSE_PROFILES={profile}\n"
        "OAUTH2_PROXY_ENABLED=true\n"
        "PORT=4567\n"
        f"DECIFLOW_CSRF_TRUSTED_ORIGINS={extra_origins}\n"
        "OAUTH2_PROXY_PUBLIC_URL=https://deciflow.example.com:4443\n"
        "OAUTH2_PROXY_CLIENT_ID=test-client\n"
        "OAUTH2_PROXY_CLIENT_SECRET=test-secret\n"
        "OAUTH2_PROXY_COOKIE_SECRET=test-cookie-secret\n"
    )
    (compose_project / ".env").write_text(env_file.read_text())
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COMPOSE_", "OAUTH2_", "DECIFLOW_")) and key != "PORT"
    }
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        "docker-compose.yml",
        "config",
        "--format",
        "json",
    ]
    result = subprocess.run(
        command,
        cwd=compose_project,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    services = json.loads(result.stdout)["services"]
    expected = {"ui", "oauth2-proxy"}
    if profile:
        expected.add(f"laya-{profile}")
    assert set(services) == expected
    assert not services["ui"].get("ports")
    ui_environment = services["ui"]["environment"]
    assert ui_environment["OAUTH2_PROXY_PUBLIC_URL"] == (
        "https://deciflow.example.com:4443"
    )
    assert ui_environment["DECIFLOW_CSRF_TRUSTED_ORIGINS"] == extra_origins
    proxy = services["oauth2-proxy"]
    assert proxy["container_name"] == "DeciFlow-OAuth2-Proxy"
    assert proxy["image"] == "quay.io/oauth2-proxy/oauth2-proxy:v7.15.5"
    assert "--upstream=http://ui:4567/" in proxy["command"]
    assert proxy["environment"]["OAUTH2_PROXY_REDIRECT_URL"] == (
        "https://deciflow.example.com:4443/oauth2/callback"
    )
    assert [(port["published"], port["target"]) for port in proxy["ports"]] == [
        ("4443", 4443)
    ]
    assert all(mount["read_only"] for mount in proxy["volumes"])
    assert proxy["read_only"]
    assert proxy["cap_drop"] == ["ALL"]

    # Missing credentials must stop configuration instead of enabling public access.
    env_file.write_text(
        env_file.read_text().replace(
            "OAUTH2_PROXY_CLIENT_SECRET=test-secret", "OAUTH2_PROXY_CLIENT_SECRET="
        )
    )
    missing = subprocess.run(
        command,
        cwd=compose_project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    assert "OAUTH2_PROXY_CLIENT_SECRET" in missing.stderr


def test_google_auth_policy() -> None:
    """Keep email admission restrictive and API/streaming behavior explicit."""
    # Compose versions serialize false bind options differently; check the source.
    deployment = yaml.safe_load((ROOT / "compose/oauth2-true.yml").read_text())
    mounts = deployment["services"]["oauth2-proxy"]["volumes"]
    assert mounts
    assert all(
        mount["type"] == "bind"
        and mount["read_only"] is True
        and mount["bind"]["create_host_path"] is False
        for mount in mounts
    )
    policy = tomllib.loads((ROOT / "oauth2-proxy/oauth2-proxy.cfg").read_text())
    assert policy["provider"] == "google"
    assert policy["authenticated_emails_file"].endswith("/allowed-emails.txt")
    assert policy["email_domains"] == []
    assert policy["api_routes"] == ["^/api(?:/|$)"]
    assert policy["cookie_secure"] and policy["cookie_httponly"]
    assert policy["cookie_name"].startswith("__Host-")
    assert policy["cookie_path"] == "/" and "cookie_domains" not in policy
    assert policy["cookie_samesite"] == "lax"
    assert policy["code_challenge_method"] == "S256"
    assert policy["upstream_timeout"] == "0s"
    assert policy["flush_interval"] == "100ms"
    assert not policy["reverse_proxy"]
    assert not policy["pass_access_token"]
    assert not policy["pass_authorization_header"]
    assert not policy["pass_basic_auth"]
    assert not policy["pass_user_headers"]
    assert not any(key.startswith(("skip_auth", "trusted_ip")) for key in policy)


@pytest.mark.parametrize("profile", ["cpu", "cuda", ""])
@pytest.mark.parametrize("bind_host", ["127.0.0.1", "0.0.0.0"])
def test_http_demo_without_oauth(tmp_path: Path, profile: str, bind_host: str) -> None:
    """A fresh checkout needs neither private OAuth files nor credentials."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required")
    # Copy only public deployment files: no actual .env, TLS or email allow list.
    shutil.copytree(ROOT / "compose", tmp_path / "compose")
    shutil.copy(ROOT / "docker-compose.yml", tmp_path / "docker-compose.yml")
    (tmp_path / ".env").write_text(
        f"COMPOSE_PROFILES={profile}\n"
        "OAUTH2_PROXY_ENABLED=false\n"
        f"DECIFLOW_BIND_HOST={bind_host}\nPORT=4567\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COMPOSE_", "OAUTH2_", "DECIFLOW_")) and key != "PORT"
    }
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    services = json.loads(result.stdout)["services"]
    assert set(services) == ({"ui", f"laya-{profile}"} if profile else {"ui"})
    port = services["ui"]["ports"][0]
    assert (port["host_ip"], port["published"], port["target"]) == (
        bind_host,
        "4567",
        4567,
    )
    assert services["ui"]["environment"].get("OAUTH2_PROXY_CLIENT_SECRET") is None
    assert str(tmp_path) in services["ui"]["volumes"][0]["source"]
