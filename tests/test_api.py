import json
import os
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from service.api import app
from service.policy import Candidate, Limits, select, query_bucket
from fit_policy import fit


def test_closed_form_and_hard_call_cap():
    candidates=[Candidate("small",.7,.002,500,1),Candidate("large",.9,.02,1000,2)]
    b=Limits(max_llm_calls=1,deadline_ms=700,max_expected_cost_usd=.1)
    result=select(candidates,b)
    assert result["selected"]=="small"
    assert result["decision_llm_calls"]==0
    assert result["rejected"][0]["reasons"]==["predicted_deadline","call_limit"]
    assert select(candidates,Limits(max_llm_calls=0))["selected"]=="STOP"
    assert query_bucket("Who invented it?",[.1,.08])=="c0_g0"


def test_calibration_shrinkage_uses_labeled_outcomes():
    rows=[{"bucket":"c0_g0","action":"retrieve_fast","correct":"1","cost_usd":"0.001","latency_ms":"800"},
          {"bucket":"c0_g0","action":"retrieve_fast","correct":"0","cost_usd":"0.003","latency_ms":"1000"}]
    obj=fit(rows)
    assert obj["actions"]["retrieve_fast"]["global_quality"]==.5
    assert obj["actions"]["retrieve_fast"]["quality_by_bucket"]["c0_g0"]==.5
    assert obj["actions"]["retrieve_fast"]["latency_p95_ms"]==1000


def test_api_route_and_answer_with_mocked_upstreams(tmp_path,monkeypatch):
    monkeypatch.setenv("API_TOKEN","test-only-key")
    monkeypatch.setenv("ALLOW_HTTP_ENDPOINTS","1")
    monkeypatch.setenv("FAST_LLM_BASE_URL","http://mock.local/v1")
    monkeypatch.setenv("FAST_LLM_MODEL","fast-model")
    monkeypatch.setenv("FAST_INPUT_USD_PER_1M","0.1")
    monkeypatch.setenv("FAST_OUTPUT_USD_PER_1M","0.2")
    monkeypatch.setenv("STRONG_LLM_BASE_URL","http://mock.local/v1")
    monkeypatch.setenv("STRONG_LLM_MODEL","strong-model")
    monkeypatch.setenv("STRONG_INPUT_USD_PER_1M","1")
    monkeypatch.setenv("STRONG_OUTPUT_USD_PER_1M","2")
    monkeypatch.setenv("RETRIEVAL_URL","http://mock.local/search")
    monkeypatch.setenv("RETRIEVAL_USD_PER_CALL","0.0001")
    actions=str(Path(__file__).resolve().parents[1]/"config/actions.json")
    monkeypatch.setenv("ACTIONS_FILE",actions)
    cal={"format_version":1,"gap_threshold":.07,"actions":{
        "retrieve_fast":{"global_quality":.6,"expected_cost_usd":.001,"latency_p95_ms":200},
        "retrieve_strong":{"global_quality":.8,"expected_cost_usd":.003,"latency_p95_ms":300},
        "iterative_strong":{"global_quality":.92,"expected_cost_usd":.006,"latency_p95_ms":600}
    }}
    f=tmp_path/"policy.json";f.write_text(json.dumps(cal));monkeypatch.setenv("CALIBRATION_FILE",str(f))
    events=[]
    def handler(req:httpx.Request):
        events.append((req.url.path,req.headers.get("authorization"),req.content.decode()))
        if req.url.path=="/search":
            return httpx.Response(200,json={"documents":[
                {"id":"1","title":"Tokyo","text":"Tokyo is the capital of Japan","score":.91},
                {"id":"2","title":"Japan","text":"Japan is in East Asia","score":.21}]})
        if req.url.path=="/v1/chat/completions":
            data=json.loads(req.content)
            text="Tokyo" if "Answer the user's" in data["messages"][0]["content"] else "Tokyo Japan"
            return httpx.Response(200,json={"choices":[{"message":{"content":text}}],
                   "usage":{"prompt_tokens":40,"completion_tokens":2}})
        return httpx.Response(404)
    with TestClient(app) as client:
        app.state.remote.http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert client.get("/health").status_code==200
        assert client.get("/ready").json()["calibration_loaded"] is True
        route_payload={"candidates":[
            {"id":"large","predicted_accuracy":.95,"expected_cost_usd":.003,"latency_p95_ms":400,"llm_calls":2},
            {"id":"small","predicted_accuracy":.7,"expected_cost_usd":.001,"latency_p95_ms":100,"llm_calls":1}],
            "budgets":{"max_llm_calls":1}}
        assert client.post("/v1/route",json=route_payload).status_code==401
        auth={"Authorization":"Bearer test-only-key"}
        assert client.post("/v1/route",json=route_payload,headers=auth).json()["selected"]=="small"
        req={"question":"What is the capital of Japan?","budgets":{"deadline_ms":2000,"max_llm_calls":1,"max_retrieval_calls":1,"max_expected_cost_usd":.01}}
        r=client.post("/v1/answer",headers=auth,json=req)
        assert r.status_code==200,r.text
        j=r.json()
        assert j["selected_action"]=="retrieve_strong"
        assert j["answer"]=="Tokyo"
        assert j["resources"]["model_calls"]==1
        assert j["resources"]["retrieval_calls"]==1
        assert j["resources"]["unreported_usage_calls"]==0
        assert j["resources"]["measured_cost_usd"]>0
        assert j["resources"]["retrieval_cost_usd"]==.0001
        assert j["resources"]["total_estimated_cost_usd"]>0
        req["budgets"]["max_llm_calls"]=2
        req["budgets"]["max_retrieval_calls"]=2
        r2=client.post("/v1/answer",headers=auth,json=req)
        assert r2.status_code==200,r2.text
        j2=r2.json()
        assert j2["selected_action"]=="iterative_strong"
        assert j2["resources"]["model_calls"]==2
        assert j2["resources"]["retrieval_calls"]==2
        assert all(x[0] in ("/v1/chat/completions","/search") for x in events)


def test_answer_respects_zero_retrieval_limit(tmp_path,monkeypatch):
    monkeypatch.setenv("API_TOKEN","t")
    monkeypatch.setenv("ALLOW_HTTP_ENDPOINTS","1")
    monkeypatch.setenv("FAST_LLM_BASE_URL","http://mock.local/v1")
    monkeypatch.setenv("FAST_LLM_MODEL","fast")
    monkeypatch.setenv("STRONG_LLM_BASE_URL","http://mock.local/v1")
    monkeypatch.setenv("STRONG_LLM_MODEL","strong")
    monkeypatch.setenv("RETRIEVAL_URL","http://mock.local/search")
    monkeypatch.delenv("CALIBRATION_FILE",raising=False)
    monkeypatch.setenv("ACTIONS_FILE",str(Path(__file__).resolve().parents[1]/"config/actions.json"))
    with TestClient(app) as client:
        response=client.post("/v1/answer",headers={"Authorization":"Bearer t"},
                             json={"question":"Hello","budgets":{"max_retrieval_calls":0,"deadline_ms":1000}})
        assert response.status_code==200
        assert response.json()["retrieval_calls"]==0
        assert response.json()["selected_action"]=="STOP"
