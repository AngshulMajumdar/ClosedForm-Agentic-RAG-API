# ClosedForm-Agentic-RAG-API

**An LLM-free, cost- and latency-aware orchestration API for agentic retrieval-augmented generation.**

Production-oriented FastAPI gateway plus **Python and JavaScript/TypeScript SDKs** for calling the running [Hugging Face Docker Space](https://huggingface.co/spaces/Angshul/ClosedForm-Agentic-RAG).

**API base URL:** `https://angshul-closedform-agentic-rag.hf.space`

**Interactive API docs:** https://angshul-closedform-agentic-rag.hf.space/docs

**OpenAPI JSON:** https://angshul-closedform-agentic-rag.hf.space/openapi.json

> **Compatibility:** `service/`, `config/actions.json`, `Dockerfile`, `requirements.txt`, and the calibration scripts are copied directly from the final tested Docker Space ZIP, byte for byte. This repository adds developer SDKs, examples, tests, API schema and scaling guidance; it does **not change** the running Space or its existing HTTP API. The original Space README (including Hugging Face YAML) is preserved in `docs/HF_SPACE_README.md`.

## What it does

Given candidate RAG actions with estimated accuracy, dollar cost and p95 latency, the gateway chooses

\[
 a^*(z)=\underset{a\in\mathcal A_{\mathrm{feasible}}}{\operatorname{argmax}}
 \left[\widehat p(z,a)-\lambda\widehat c(a)-\mu\widehat t(a)\right].
\]

The **numerical routing decision makes zero LLM calls** and takes linear time in the number of candidate actions. Model inference is performed by externally configured LLM endpoints (including modern 8B–120B+ models); the Docker Space only needs CPU resources. The controller is a **finite macro-action approximation**, not an exact unrestricted POMDP solver.

| HTTP endpoint | Purpose | LLM inference |
|---|---|---|
| `GET /health` | Liveness | None |
| `GET /ready` | Backend configuration status | None |
| `GET /docs` | Interactive Swagger UI | None |
| `GET /openapi.json` | Full JSON schema | None |
| `POST /v1/route` | Numerical policy selection from client-supplied candidates | **No LLM calls** |
| `POST /v1/answer` | Retrieve, select calibrated macro-action, execute selected workflow | **1–2 external LLM calls** |

Both POST endpoints require `Authorization: Bearer <API_TOKEN>`.

## 60-second start: call the live service

You need **a gateway access token provided by the Space operator**. This is the `API_TOKEN` configured as the Space secret; it is **not** the provider's `HF_TOKEN`. Store it in your application environment, never in source control.

### Python

```bash
python -m pip install .
export CLOSED_FORM_RAG_API_TOKEN="your-gateway-api-token"
```

```python
from closedform_rag import ClosedFormRAGClient

with ClosedFormRAGClient() as api:
    result = api.route(
        candidates=[
            {"id":"fast","predicted_accuracy":0.77,"expected_cost_usd":0.001,
             "latency_p95_ms":900,"llm_calls":1,"retrieval_calls":0},
            {"id":"strong","predicted_accuracy":0.88,"expected_cost_usd":0.008,
             "latency_p95_ms":2400,"llm_calls":1,"retrieval_calls":0},
        ],
        budgets={"max_llm_calls":1,"max_expected_cost_usd":0.010,"deadline_ms":3000},
    )
    print(result["selected"], result["decision_llm_calls"])
```

All sample action accuracies, costs and latency forecasts are illustrative **inputs** for demonstrating the API, not benchmark measurements or certified provider prices.

### Node.js / TypeScript (Node 18+)

```bash
npm install ./js
export CLOSED_FORM_RAG_API_TOKEN="your-gateway-api-token"
```

```js
import { ClosedFormRAGClient } from 'closedform-agentic-rag-client';
const api = new ClosedFormRAGClient();
const routed = await api.route([
  {id:'fast',predicted_accuracy:0.77,expected_cost_usd:0.001,
   latency_p95_ms:900,llm_calls:1,retrieval_calls:0},
  {id:'strong',predicted_accuracy:0.88,expected_cost_usd:0.008,
   latency_p95_ms:2400,llm_calls:1,retrieval_calls:0}
], {max_llm_calls:1,deadline_ms:3000,max_expected_cost_usd:0.010});
console.log(routed.selected, routed.decision_llm_calls);
```

### curl

```bash
curl --fail-with-body -sS 'https://angshul-closedform-agentic-rag.hf.space/v1/route' \
  -H "Authorization: Bearer $CLOSED_FORM_RAG_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"candidates":[{"id":"fast","predicted_accuracy":0.80,
       "expected_cost_usd":0.001,"latency_p95_ms":900,"llm_calls":1}],
       "budgets":{"deadline_ms":3000,"max_llm_calls":1}}'
```

The `/v1/route` API works without remote LLM providers or a retrieval service. It is useful for integrating orchestration into **existing** agent systems.

## Run complete RAG answering

Calling `/v1/answer` additionally requires the Space operator to configure two OpenAI-compatible LLM endpoints, `RETRIEVAL_URL`, and **real calibrated action forecasts** (or explicit caller-provided forecasts for exploratory tests). A running homepage alone does not establish these prerequisites.

```python
from closedform_rag import ClosedFormRAGClient

with ClosedFormRAGClient() as api:
    response = api.answer(
        "What is the capital of Japan?",
        budgets={
            "deadline_ms": 12000,
            "max_llm_calls": 2,
            "max_retrieval_calls": 2,
            "max_expected_cost_usd": 0.02,
        },
    )
    print(response["answer"])
    print(response["selected_action"])
    print(response["resources"])
```

If model/retriever settings or action calibration are absent, the service returns an explicit `503` instead of inventing results. See **[Complete API reference](docs/API.md)**.

## Scalable application integration

- **Async I/O and connection pooling:** use `AsyncClosedFormRAGClient` for a Python service and `ClosedFormRAGClient` for Node.js backends.
- **Controlled fan-out:** both SDKs provide `batch_answer` / `batchAnswers` with an explicit concurrency ceiling. These methods send individual calls; no `/v1/batch` endpoint is invented.
- **Safe retries:** `/v1/route` retries transient 429/502/503/504 responses. `/v1/answer` **does not retry by default** because a retry can duplicate paid model calls.
- **Contemporary inference:** model weights run on external endpoints, not the CPU Space; the API can target larger models without changing its routing code.
- **Multi-tenant production:** put an identity-aware API gateway in front of the Space, with per-customer API keys, quotas and audit logging. Never distribute the single Space `API_TOKEN` in a public website/mobile app.

There is no measured production QPS claim. Throughput is bounded by the HF Space replica, its local 64-request semaphore, the retriever and the model-provider limits. See **[Production scaling](docs/PRODUCTION.md)** and the conservative **[load-test script](benchmarks/load_route.py)**.

## Repository structure

```text
closedform_rag/       Python sync and async SDK
js/                   Node.js/TypeScript SDK
service/              Exact tested FastAPI server implementation (unchanged)
config/               Exact tested macro-action definitions (unchanged)
api/openapi.json       Generated from unchanged FastAPI Pydantic schema
examples/             Executable Python, Node and curl integration examples
benchmarks/           Bounded route-only HTTP load tester
reports/              Test report and server-file identity manifest
scripts/              Local validation utility
tests/                Original server tests + SDK contract tests
docs/                 API, deployment, production and original HF README
Dockerfile            Original tested Dockerfile (unchanged)
requirements.txt      Original tested server dependencies (unchanged)
pyproject.toml        Installable Python package
```

## Test from a clean checkout

```bash
python -m pip install -r requirements.txt
python -m pip install -e . pytest
python -m pytest -q
node --test js/tests/client.test.mjs
```

Node tests use its standard library; there is no npm dependency needed to run them. Local integration tests **mock upstream inference and retrieval**, and thus do not incur provider charges.

## Source deployment and compatibility

The Hugging Face Docker Space is already deployed separately and remains untouched. For a fresh HF Space deployment, **replace this GitHub-oriented README with `docs/HF_SPACE_README.md`** so Hugging Face can read its YAML metadata. Then use the exact existing `Dockerfile` and `service/` files. Secrets are added in Space Settings, never committed to the repository.

### Important scientific and operational boundaries

Accuracy forecasts require calibration on the exact models and retriever used. Budget feasibility uses **forecasts** and is not a guaranteed hard-dollar spending cap. Latency timeout enforcement cannot prevent external providers from billing already-started requests. Live answer generation is not automatically billable-free. The previously reported 0.5B HotpotQA experiments are not evidence of accuracy or throughput with newer commercial models.

## License

MIT. See [LICENSE](LICENSE). For the deployed service, the operator controls credentials, upstream inference costs, availability and access policies.
