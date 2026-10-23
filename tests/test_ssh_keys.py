"""Check key storage, secret handling, and deletion boundaries."""

import json
from pathlib import Path
from types import SimpleNamespace

import asyncssh
import httpx
import pytest

from deciflow import server
from deciflow.source_registry import save_sources
from deciflow.ssh_hosts import delete_host, load_hosts, save_host
from deciflow.ssh_keys import add_key, delete_key, get_keys_directory, list_keys


@pytest.fixture
def key_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path))
    return get_keys_directory()


def test_pair_storage_and_deletion(key_storage: Path) -> None:
    private = asyncssh.generate_private_key("ssh-ed25519")
    add_key("production", private.export_private_key().decode())
    pair = list_keys()[0]
    assert pair["publicKey"] == private.export_public_key().decode()
    assert "PRIVATE KEY" not in json.dumps(pair)
    assert key_storage.stat().st_mode & 0o777 == 0o700
    assert Path(pair["privatePath"]).stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="already exists"):
        add_key("production", private.export_private_key().decode())
    source = {
        "name": "Logs",
        "type": "ssh",
        "path": "/logs/app.log",
        "host": "example.com",
        "port": 22,
        "username": "reader",
        "keyId": pair["id"],
    }
    host = save_host(source)
    save_sources([{**source, "hostId": host["id"]}])
    with pytest.raises(ValueError, match="used"):
        delete_key(pair["id"], [])
    save_sources([])
    with pytest.raises(ValueError, match="SSH Host"):
        delete_key(pair["id"], [])
    delete_host(load_hosts()[0]["id"], [])
    with pytest.raises(ValueError, match="used"):
        delete_key(pair["id"], [source])
    delete_key(pair["id"], [])
    assert list_keys() == []


@pytest.mark.parametrize("name", ["../escape", "/tmp/key", ".", "", "   ", "x" * 65])
def test_invalid_key_names(key_storage: Path, name: str) -> None:
    with pytest.raises(ValueError):
        add_key(name, "invalid private key")
    with pytest.raises(ValueError):
        delete_key(name, [])
    assert not list(key_storage.iterdir())


def test_invalid_and_encrypted_keys_leave_no_files(key_storage: Path) -> None:
    key = asyncssh.generate_private_key("ssh-ed25519")
    for contents in [
        "not a key",
        "x" * 65537,
        key.export_private_key("pkcs8-pem", passphrase="test-only").decode(),
    ]:
        with pytest.raises(ValueError):
            add_key("invalid", contents)
    assert list_keys() == []


@pytest.mark.anyio
async def test_api_origin_secret_responses_and_active_job_guard(
    key_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
    ) as client:
        for method in ["POST", "PUT", "DELETE"]:
            assert (await client.request(method, "/api/ssh-keys")).status_code == 403
        headers = {"Origin": "http://localhost"}
        response = await client.put(
            "/api/ssh-keys",
            headers=headers,
            json={"name": "test", "privateKey": private},
        )
        assert response.status_code == 200
        assert "PRIVATE KEY" not in response.text
        assert private not in response.text
        pair = response.json()["keys"][0]
        listing = await client.post("/api/ssh-keys", headers=headers)
        assert listing.json()["keys"] == [pair]
        job = SimpleNamespace(
            state="running",
            settings={"sources": [{"type": "ssh", "keyId": pair["id"]}]},
        )
        monkeypatch.setattr(server, "JOBS", {"test": job})
        blocked = await client.request(
            "DELETE", "/api/ssh-keys", headers=headers, json={"id": pair["id"]}
        )
        assert blocked.status_code == 400
        job.state = "completed"
        deleted = await client.request(
            "DELETE", "/api/ssh-keys", headers=headers, json={"id": pair["id"]}
        )
        assert deleted.status_code == 200 and deleted.json()["keys"] == []
        invalid = await client.put(
            "/api/ssh-keys",
            headers=headers,
            json={"name": "test", "privateKey": "SECRET sentinel"},
        )
        assert invalid.status_code == 400 and "SECRET sentinel" not in invalid.text
        oversized = await client.put(
            "/api/ssh-keys", headers=headers, content="x" * 131073
        )
        assert oversized.status_code == 413


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["paste", "path", "upload"])
async def test_registration_methods_copy_key_and_derive_public(
    key_storage: Path,
    tmp_path: Path,
    method: str,
) -> None:
    key = asyncssh.generate_private_key("ssh-ed25519")
    private = key.export_private_key().decode()
    original = tmp_path / "original_key"
    original.write_text(private)
    body = {"name": f"DeciFlow SSH Key {method}", "inputMethod": method}
    if method == "path":
        body["privateKeyPath"] = str(original)
    else:
        body["privateKey"] = private
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.put("/api/ssh-keys", json=body)
    assert response.status_code == 200
    pair = response.json()["keys"][0]
    assert pair["publicKey"] == key.export_public_key().decode()
    assert Path(pair["privatePath"]).parent.parent == key_storage
    assert (
        asyncssh.read_private_key(pair["privatePath"]).export_public_key()
        == key.export_public_key()
    )
    assert original.read_text() == private
    assert "PRIVATE KEY" not in response.text
    delete_key(pair["id"], [])
    assert original.read_text() == private


@pytest.mark.anyio
async def test_path_and_method_validation(key_storage: Path, tmp_path: Path) -> None:
    large = tmp_path / "large"
    large.write_bytes(b"x" * 65537)
    binary = tmp_path / "binary"
    binary.write_bytes(b"\xff")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        for path in [
            "",
            str(tmp_path / "missing"),
            str(tmp_path),
            str(large),
            str(binary),
        ]:
            response = await client.put(
                "/api/ssh-keys",
                json={
                    "name": "invalid",
                    "inputMethod": "path",
                    "privateKeyPath": path,
                },
            )
            assert response.status_code == 400
        response = await client.put(
            "/api/ssh-keys",
            json={
                "name": "invalid",
                "inputMethod": "unsupported",
                "privateKey": "SECRET",
            },
        )
        assert response.status_code == 400 and "SECRET" not in response.text
    assert list_keys() == []


@pytest.mark.anyio
async def test_uuid_key_rename_preserves_host_references_and_key_files(
    key_storage: Path,
) -> None:
    """Renaming/reusing display names must not change connections or key material."""
    from deciflow.config_store import load_records

    private = asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
    pair = add_key("Original", private)
    before = Path(pair["privatePath"]).read_bytes()
    host = save_host(
        {
            "name": "Remote",
            "host": "localhost",
            "port": 22,
            "username": "reader",
            "keyId": pair["id"],
        }
    )
    assert Path(pair["privatePath"]).parent.name == pair["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.patch(
            "/api/ssh-keys", json={"id": pair["id"], "name": "Renamed"}
        )
        assert response.status_code == 200
        renamed = response.json()["keys"][0]
        assert (
            renamed["name"] == "Renamed"
            and renamed["privatePath"] == pair["privatePath"]
        )
        replacement = add_key("Original", private)
        assert replacement["id"] != pair["id"]
        assert load_hosts() == [host]
        assert Path(pair["privatePath"]).read_bytes() == before
        assert load_records("ssh_keys")[pair["id"]] == {
            "id": pair["id"],
            "name": "Renamed",
        }
        duplicate = await client.patch(
            "/api/ssh-keys", json={"id": pair["id"], "name": "original"}
        )
        assert duplicate.status_code == 400
        blocked = await client.request(
            "DELETE", "/api/ssh-keys", json={"id": pair["id"]}
        )
        assert blocked.status_code == 400
        assert private not in response.text
