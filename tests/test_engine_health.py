"""HTTP-only provider probes do not submit inference requests."""

import httpx
import pytest

from deciflow import server
from deciflow.config import Engine


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["laya", "jev"])
@pytest.mark.parametrize(
    ("response_kind", "expected"),
    [
        (200, "connected"),
        (401, "authentication_error"),
        (403, "authentication_error"),
        (500, "api_error"),
        (302, "api_error"),
        ("timeout", "timeout"),
        ("disconnected", "disconnected"),
        ("html", "api_error"),
        ("shape", "api_error"),
    ],
)
async def test_provider_probe(
    name: str, response_kind: int | str, expected: str
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if response_kind == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if response_kind == "disconnected":
            raise httpx.ConnectError("unreachable", request=request)
        if response_kind == "html":
            return httpx.Response(200, text="<html>proxy error</html>")
        if response_kind == "shape":
            return httpx.Response(200, json={"unexpected": True})
        payload = {"status": "ok"} if name == "laya" else {"models": []}
        return httpx.Response(int(response_kind), json=payload)

    engine = Engine(name, "http://provider/proxy/v1/systemone", "test-key", "test", 120)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await server._check_engine_connection(engine, client) == expected
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url.path == ("/proxy/health" if name == "laya" else "/v1/models")
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.content == b""


@pytest.mark.anyio
async def test_jev_missing_key_does_not_contact_provider() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        pytest.fail("Missing credentials must not send a provider request")

    engine = Engine("jev", "https://api.typesafe.ai/v1/systemone", "", "test", 120)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (
            await server._check_engine_connection(engine, client)
            == "authentication_error"
        )


@pytest.mark.anyio
async def test_health_route(monkeypatch: pytest.MonkeyPatch) -> None:
    async def probe(engine: Engine, client: httpx.AsyncClient) -> str:
        return "connected"

    monkeypatch.setattr(server, "_check_engine_connection", probe)
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/engine-health")
    assert response.status_code == 200
    assert response.json() == {"engine": "laya", "connection": "connected"}
    assert response.headers["cache-control"] == "no-store"
