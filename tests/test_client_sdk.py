"""Client-side contract tests use the unchanged server's HTTP schema.

No external model calls, no Hugging Face credentials, no network calls.
"""
import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from closedform_rag import APIError, AsyncClosedFormRAGClient, ClosedFormRAGClient
from service.api import app


def test_openapi_contract_matches_unchanged_server():
    p = Path(__file__).resolve().parents[1]/"api/openapi.json"
    assert json.loads(p.read_text(encoding="utf-8")) == app.openapi()
    assert "/v1/route" in app.openapi()["paths"]
    assert "/v1/answer" in app.openapi()["paths"]
    assert "/v1/batch" not in app.openapi()["paths"]


def test_route_sync_request_includes_auth_budget_and_no_llm():
    seen = []
    def handler(req: httpx.Request):
        seen.append(req)
        assert req.url.path == "/v1/route"
        assert req.headers["authorization"] == "Bearer client-secret"
        data = json.loads(req.content)
        assert data["budgets"]["max_expected_cost_usd"] == 0.01
        assert data["candidates"][0]["id"] == "fast"
        return httpx.Response(200,json={"selected":"fast","decision_llm_calls":0,"rejected":[],"candidates":[]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with ClosedFormRAGClient(api_token="client-secret",http_client=http) as client:
            answer = client.route([{"id":"fast","predicted_accuracy":0.7,"expected_cost_usd":0.001,
                                    "latency_p95_ms":700,"llm_calls":1}],
                                   budgets={"max_expected_cost_usd":.01})
            assert answer["selected"] == "fast"
            assert answer["decision_llm_calls"] == 0
    finally:
        http.close()
    assert len(seen) == 1


def test_answer_never_automatically_retries_billable_503():
    n = 0
    def handler(req):
        nonlocal n
        n += 1
        assert req.url.path == "/v1/answer"
        return httpx.Response(503,json={"detail":"Missing retriever"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with ClosedFormRAGClient(api_token="secret",http_client=http) as client:
        with pytest.raises(APIError) as ex:
            client.answer("What is a graph?",budgets={"max_llm_calls":2})
        assert ex.value.status_code == 503
    http.close()
    assert n == 1


def test_route_retries_transient_429_only():
    n = 0
    def handler(req):
        nonlocal n
        n += 1
        if n == 1:
            return httpx.Response(429,headers={"retry-after":"0"},json={"detail":"At capacity"})
        return httpx.Response(200,json={"selected":"a","decision_llm_calls":0})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with ClosedFormRAGClient(api_token="secret",http_client=http) as client:
        assert client.route([{"id":"a"}])["selected"] == "a"
    http.close()
    assert n == 2


def test_answer_has_exact_supported_request_fields():
    def handler(req):
        data = json.loads(req.content)
        assert set(data) == {"question","budgets","allowed_actions","action_forecasts","quality_estimates"}
        assert data["allowed_actions"] == ["retrieve_fast"]
        assert data["action_forecasts"]["retrieve_fast"]["id"] == "retrieve_fast"
        return httpx.Response(200,json={"answer":"Tokyo","selected_action":"retrieve_fast"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with ClosedFormRAGClient(api_token="secret",http_client=http) as client:
        result = client.answer("What is Japan's capital?",budgets={"deadline_ms":8000},
            allowed_actions=["retrieve_fast"],
            quality_estimates={"retrieve_fast":.8},
            action_forecasts={"retrieve_fast":{
                "id":"retrieve_fast","predicted_accuracy":.8,"expected_cost_usd":.001,
                "latency_p95_ms":1200,"llm_calls":1,"retrieval_calls":0}})
        assert result["answer"] == "Tokyo"
    http.close()


def test_async_batch_has_bounded_concurrency_and_preserves_order():
    async def scenario():
        active = 0
        peak = 0
        async def handler(req):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            q = json.loads(req.content)["question"]
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(200,json={"answer":q,"selected_action":"retrieve_fast"})
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        async with AsyncClosedFormRAGClient(api_token="secret",http_client=http) as client:
            results = await client.batch_answer(["a","b","c","d","e"],concurrency=2)
            assert [r["answer"] for r in results] == ["a","b","c","d","e"]
        await http.aclose()
        assert peak <= 2
        assert peak >= 1
    asyncio.run(scenario())


def test_route_against_real_app_with_mocked_transport(monkeypatch):
    """Wire test: SDK -> ASGI app -> original route, no model calls."""
    monkeypatch.setenv("API_TOKEN","contract-key")
    # original app route does not use lifespan resources
    with TestClient(app) as server:
        def handler(req):
            return httpx.Response(200,json=server.post(
                req.url.path,
                headers={"Authorization":req.headers["authorization"]},
                json=json.loads(req.content),
            ).json())
        http = httpx.Client(transport=httpx.MockTransport(handler))
        with ClosedFormRAGClient(api_token="contract-key",http_client=http) as client:
            answer = client.route([
                {"id":"small","predicted_accuracy":0.7,"expected_cost_usd":0.001,
                 "latency_p95_ms":500,"llm_calls":1},
                {"id":"large","predicted_accuracy":0.9,"expected_cost_usd":0.03,
                 "latency_p95_ms":1200,"llm_calls":1},
            ],budgets={"max_expected_cost_usd":0.01})
            assert answer["selected"] == "small"
            assert answer["decision_llm_calls"] == 0
        http.close()
