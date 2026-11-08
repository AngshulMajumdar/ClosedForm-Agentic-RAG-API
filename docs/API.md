# HTTP API v1 — exact deployed contract

**Base URL:** `https://angshul-closedform-agentic-rag.hf.space`

**Authentication:** `Authorization: Bearer <operator-provided gateway API_TOKEN>` for `/v1/route` and `/v1/answer`. Never send the Hugging Face provider `HF_TOKEN` as your gateway token.

The definitive machine-readable JSON schema is [api/openapi.json](../api/openapi.json), exported from the tested FastAPI app. The live service exposes `/docs` and `/openapi.json` when reachable.

## POST /v1/route

No retrieval, calibration, or model endpoint is needed. Inputs are **caller-supplied forecasts**.

```json
{
  "candidates": [
    {"id":"rag-fast","predicted_accuracy":0.77,"expected_cost_usd":0.001,"latency_p95_ms":900,"llm_calls":1,"retrieval_calls":0},
    {"id":"rag-strong","predicted_accuracy":0.88,"expected_cost_usd":0.008,"latency_p95_ms":2400,"llm_calls":1,"retrieval_calls":0}
  ],
  "budgets": {
    "max_expected_cost_usd":0.01,
    "deadline_ms":3000,
    "max_llm_calls":1,
    "max_retrieval_calls":2,
    "price_per_usd":1.0,
    "price_per_second":0.01,
    "stop_utility":-1.0
  },
  "sunk_cost_usd":0,
  "sunk_latency_ms":0,
  "sunk_retrieval_calls":0
}
```

The decision is deterministic for given inputs, scores candidates in O(number of actions) time, rejects forecast-infeasible ones and returns fields `selected`, `selected_prediction`, `candidates`, `rejected`, `decision_llm_calls` (always zero), and `reason`. If nothing is feasible, `selected` is `STOP`.

The numerical forecasts above are fictitious examples, not evaluated accuracy or pricing.

## POST /v1/answer

Requires configured retrieval and model backends plus a fitted calibration table, **or** explicit action forecasts. The initial retrieval is performed before action selection and included in elapsed time. The fast and strong model aliases are resolved from server-side environment variables; clients never provide arbitrary upstream URLs.

```json
{
  "question":"What is the capital of Japan?",
  "budgets": {
    "max_expected_cost_usd":0.02,
    "deadline_ms":12000,
    "max_llm_calls":2,
    "max_retrieval_calls":2
  },
  "allowed_actions":["retrieve_fast","retrieve_strong","iterative_strong"]
}
```

Supported top-level fields: `question` (required), `budgets`, `allowed_actions`, `quality_estimates`, and `action_forecasts`. See the 3 action IDs in `config/actions.json`.

The response on successful execution contains `answer`, `selected_action`, `bucket`, `routing`, `forecast_source`, `resources`, `elapsed_ms`, `preflight_ms`, `post_preflight_ms`, and `budget_note`.

Example of response **shape** (not an asserted live result):

```json
{
  "answer":"Tokyo",
  "selected_action":"retrieve_fast",
  "bucket":"c0_g1",
  "forecast_source":"calibrated_table",
  "routing":{"selected":"retrieve_fast","decision_llm_calls":0},
  "resources":{"model_calls":1,"retrieval_calls":1,"input_tokens":100,"output_tokens":3,"measured_cost_usd":0.001,"total_estimated_cost_usd":0.0015},
  "elapsed_ms":950,
  "preflight_ms":80,
  "post_preflight_ms":870,
  "budget_note":"Monetary feasibility is forecast-based. Provider calls may incur charges even after local deadline cancellation."
}
```

When no action is feasible, response may contain `selected_action:"STOP"` and `answer:null` instead. The zero-retrieval-cap STOP response has a minimal different shape. Do not assume all fields are present on a STOP response.

### Explicit forecasts before calibration

`action_forecasts` is an optional object mapping configured action IDs to complete candidate records. The `id`, `llm_calls`, and `retrieval_calls` **must match** the configured action definition; for the iterative action, `retrieval_calls=1` means **one additional retrieval after the initial search**, not total searches. These numbers are externally provided forecasts and are **not** learned by the API at request time.

```json
{
  "question":"What is the capital of Japan?",
  "budgets":{"deadline_ms":12000,"max_llm_calls":2,"max_retrieval_calls":2},
  "action_forecasts": {
    "retrieve_fast": {"id":"retrieve_fast","predicted_accuracy":0.70,"expected_cost_usd":0.001,"latency_p95_ms":1200,"llm_calls":1,"retrieval_calls":0},
    "retrieve_strong": {"id":"retrieve_strong","predicted_accuracy":0.82,"expected_cost_usd":0.008,"latency_p95_ms":2600,"llm_calls":1,"retrieval_calls":0},
    "iterative_strong": {"id":"iterative_strong","predicted_accuracy":0.86,"expected_cost_usd":0.012,"latency_p95_ms":5000,"llm_calls":2,"retrieval_calls":1}
  }
}
```

Numbers above are schema examples only. For production, fit calibration using `collect_calibration.py` and `fit_policy.py` on real model responses and resource measurements.

## Responses and error handling

| Status | Meaning | Client handling |
|---|---|---|
| 200 | Completed request or policy STOP | Inspect selected action and returned fields |
| 401 | Missing/wrong API token | Fix credentials; don't retry |
| 422 | Invalid payload or missing retrieval evidence | Fix request/input; don't retry |
| 429 | Admission concurrency or call budget exceeded | Backoff; **never automatically replay billable answers** |
| 502 | Upstream model/retriever failure | Report error; billability of prior attempts may be unknown |
| 503 | Missing server configuration/calibration | Ask operator to set backends; retry only after fixing |
| 504 | Deadline expired | Treat as failure; downstream provider charge may still occur |

`GET /health` and `GET /ready` do not require the bearer key. `GET /ready` is a *configuration summary*, not proof that the underlying providers are reachable.
