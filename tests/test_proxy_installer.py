"""Exercise the native installer with local archives and no host installation."""

import hashlib
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from test_oauth2_proxy import PROXY_SHA256, PROXY_VERSION

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install_oauth2_proxy.sh"


def prepare_installation(
    tmp_path: Path, system: str, machine: str, release: str
) -> tuple[Path, dict[str, str], Path, Path]:
    stem = f"oauth2-proxy-v{PROXY_VERSION}.{release}"
    bundle = tmp_path / "download.tar.gz"
    content = f'#!/bin/sh\necho "oauth2-proxy v{PROXY_VERSION}"\n'.encode()
    with tarfile.open(bundle, "w:gz") as archive:
        info = tarfile.TarInfo(f"{stem}/oauth2-proxy")
        info.size = len(content)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(content))
    tools = tmp_path / "tools"
    tools.mkdir()
    uname = tools / "uname"
    uname.write_text(
        f'#!/bin/sh\ncase "$1" in -s) echo "{system}";; -m) echo "{machine}";; esac\n'
    )
    uname.chmod(0o755)
    curl = tools / "curl"
    curl.write_text(
        f"#!{sys.executable}\n"
        "import os,sys,shutil\nfrom pathlib import Path\n"
        "Path(os.environ['PROXY_TEST_REQUEST']).write_text(' '.join(sys.argv[1:]))\n"
        "if os.getenv('PROXY_TEST_FAIL_DOWNLOAD'): sys.exit(22)\n"
        "shutil.copyfile(os.environ['PROXY_TEST_ARCHIVE'], "
        "sys.argv[sys.argv.index('--output')+1])\n"
    )
    curl.chmod(0o755)
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    env = {
        **os.environ,
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
        "TMPDIR": str(temporary),
        "PROXY_TEST_ARCHIVE": str(bundle),
        "PROXY_TEST_REQUEST": str(tmp_path / "request.txt"),
    }
    return bundle, env, tmp_path / "installed", temporary


@pytest.mark.parametrize(
    "system,machine,release",
    [
        ("Linux", "x86_64", "linux-amd64"),
        ("Linux", "aarch64", "linux-arm64"),
        ("Darwin", "amd64", "darwin-amd64"),
        ("Darwin", "arm64", "darwin-arm64"),
    ],
)
def test_installer_verifies_and_installs_local_archive(
    tmp_path: Path, system: str, machine: str, release: str
) -> None:
    bundle, env, destination, temporary = prepare_installation(
        tmp_path, system, machine, release
    )
    # Replace only the pinned digest in a disposable copy to verify a synthetic archive.
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    script = tmp_path / "installer.sh"
    script.write_text(SCRIPT.read_text().replace(PROXY_SHA256[release], digest))
    result = subprocess.run(
        ["bash", str(script), str(destination)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    binary = destination / "oauth2-proxy"
    assert binary.is_file()
    assert binary.stat().st_mode & 0o777 == 0o755
    assert f"v{PROXY_VERSION}" in result.stdout
    request = (tmp_path / "request.txt").read_text()
    assert f"v{PROXY_VERSION}/oauth2-proxy-v{PROXY_VERSION}.{release}.tar.gz" in request
    assert list(temporary.iterdir()) == []


@pytest.mark.parametrize("failure", ["checksum", "download"])
def test_failed_installer_preserves_existing_binary_and_cleans_temp(
    tmp_path: Path, failure: str
) -> None:
    _, env, destination, temporary = prepare_installation(
        tmp_path, "Linux", "x86_64", "linux-amd64"
    )
    destination.mkdir()
    binary = destination / "oauth2-proxy"
    binary.write_text("existing binary")
    if failure == "download":
        env["PROXY_TEST_FAIL_DOWNLOAD"] = "1"
    result = subprocess.run(
        ["bash", str(SCRIPT), str(destination)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert binary.read_text() == "existing binary"
    assert list(temporary.iterdir()) == []


def test_unsupported_platform_does_not_download(tmp_path: Path) -> None:
    _, env, destination, temporary = prepare_installation(
        tmp_path, "Linux", "unsupported", "linux-amd64"
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), str(destination)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Unsupported CPU" in result.stderr
    assert not (tmp_path / "request.txt").exists()
    assert not destination.exists()
    assert list(temporary.iterdir()) == []


def test_installer_pins_match_the_verified_smoke_test_archives() -> None:
    source = SCRIPT.read_text()
    assert f"proxy_version={PROXY_VERSION}" in source
    for digest in PROXY_SHA256.values():
        assert digest in source
