"""Preserve provider bodies and actionable diagnostics across both engines."""

from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from conftest import DECISION_ANSWERS

from deciflow.classifier import CRITERIA, Result, classify_batch, classify_log
from deciflow.config import get_engine
from deciflow.result_payload import compact_result
from deciflow.result_store import SQLiteResultStore


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize(
    "case",
    [
        "success",
        "missing",
        "probabilities",
        "range",
        "sum",
        "score",
        "html",
        "nan",
        "http",
        "array",
        "usage",
        "timeout",
        "preflight",
    ],
)
async def test_response_diagnostics_survive_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, engine: str, case: str
) -> None:
    """Keep raw errors and exact parsed bodies, without storing request credentials."""
    monkeypatch.setenv("DECISION_ENGINE", engine)
    monkeypatch.setenv("JEV_API_KEY", "private-provider-key")
    monkeypatch.setenv("LAYA_API_KEY", "private-provider-key")
    if case == "preflight":
        if engine == "laya":
            pytest.skip("Only Jev uses the local byte preflight guard.")
        monkeypatch.setenv("JEV_MAX_INPUT_BYTES", "1")
    body: Result = {
        "usage": {"truncated": False},
        "answers": {
            **deepcopy(DECISION_ANSWERS),
            "category": {
                "choice": "normal",
                "confidence": 1,
                "probabilities": {key: int(key == "normal") for key in CRITERIA},
            },
        },
    }
    expected_path = "answers.category"
    if case == "usage":
        body["usage"] = "invalid usage"
        expected_path = "usage"
    elif case == "missing":
        del body["answers"]["category"]
    elif case == "probabilities":
        del body["answers"]["category"]["probabilities"]["other"]
    elif case == "range":
        body["answers"]["category"]["probabilities"]["other"] = -1
    elif case == "sum":
        body["answers"]["category"]["probabilities"]["normal"] = 0.5
    elif case == "score":
        body["answers"]["urgency"]["legend"]["0"] = "Wrong level"
        expected_path = "answers.urgency"
    calls = []
    raw = (
        '{"answers": {"category": {"probabilities": {"normal": NaN}}}}'
        if case == "nan"
        else "<html>Upstream returned an invalid body</html>\n"
    )

    def handle_request(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if case == "timeout":
            raise httpx.ReadTimeout("Timeout", request=request)
        if case in {"html", "http", "nan"}:
            return httpx.Response(
                502 if case == "http" else 200,
                text=raw,
                headers={"Content-Type": "text/html"},
            )
        return httpx.Response(200, json=[] if case == "array" else body)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(text: str) -> Result:
            return await classify_log(text, get_engine(), client)

        rows = [item async for _, item in classify_batch(["Example"], handle_classify)]
    result = compact_result(rows[0])
    assert ("error" not in result) == (case == "success")
    if case in {"html", "http", "nan"}:
        assert result["providerResponseText"] == raw
        assert result["responseContentType"] == "text/html"
    elif case in {"timeout", "preflight"}:
        assert "providerResponse" not in result
        assert "providerResponseText" not in result
        assert len(calls) == (0 if case == "preflight" else 1)
    elif case == "array":
        assert result["providerResponse"] == []
        assert result["responseValidationError"]["path"] == "response"
    elif case == "success":
        assert result["providerResponse"]["answersInDecisions"] is True
        assert "answers" not in result["providerResponse"]
        assert result["decisions"] == body["answers"]
    else:
        assert result["providerResponse"] == body
        diagnostic = result["responseValidationError"]
        assert diagnostic["path"] == expected_path
        assert diagnostic["message"]
        expected = {
            "missing": "Missing required field",
            "probabilities": "missing: ['other']",
            "range": "between 0 and 1",
            "sum": "received 0.5",
            "score": "legend",
            "usage": "Usage must be a JSON object",
        }[case]
        assert expected in diagnostic["message"]
    if case in {"html", "nan"}:
        assert result["responseValidationError"]["path"] == "response"
    assert "private-provider-key" not in str(result)
    store = SQLiteResultStore(tmp_path / "responses.db")
    snapshot = {
        "state": "completed",
        "settings": {},
        "startedAt": "2026-10-17T00:00:00Z",
    }
    store.create("run", snapshot)
    store.append("run", {"type": "result", "index": 0, "result": result}, snapshot)
    reopened = SQLiteResultStore(tmp_path / "responses.db")
    restored = reopened.page("run", {}, 30)["items"][0]["result"]
    for field in (
        "providerResponse",
        "providerResponseText",
        "responseContentType",
        "responseValidationError",
    ):
        assert restored.get(field) == result.get(field)
    reopened.close()
    store.close()
