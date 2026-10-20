"""Validate CPU, CUDA, and UI-only Compose deployments without starting containers."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("profile", ["cpu", "cuda", ""])
def test_compose_deployment(profile: str, tmp_path: Path) -> None:
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
        "PORT=4567\n"
        "LAYA_API_KEY=compose-test-key\n"
        "DECIFLOW_DATA_DIR=/custom/data\n"
        "DECIFLOW_LOG_DIR=/custom/logs\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COMPOSE_", "LAYA_", "DECIFLOW_")) and key != "PORT"
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
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    services = config["services"]
    assert set(services) == ({"ui", f"laya-{profile}"} if profile else {"ui"})
    ui = services["ui"]
    assert ui["image"] == "call518/deciflow-ui:0.0.2"
    assert ui["ports"][0]["target"] == 4567
    assert ui["ports"][0]["published"] == "4567"
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
