---
title: Closed-Form RAG API
emoji: 🧮
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
short_description: Closed-form, LLM-free routing for agentic RAG APIs
---

# Closed-Form Agentic RAG — Docker API

**A runnable FastAPI gateway, not an LLM model checkpoint.** The controller scores
calibrated macro-actions in **O(number of actions)** time. The inference calls
are made against external OpenAI-compatible chat APIs: HF Inference Providers,
HF Inference Endpoints, vLLM, TGI, an appropriately configured provider gateway,
etc. The Docker Space needs **no GPU**, even when the remote models are 8B,
32B, 70B or larger.

> Scientific qualification: This is a finite contextual macro-action relaxation
> of the full POMDP. There is **no claim of globally optimal POMDP planning** or
> of superior accuracy on untested modern LLMs. Accuracy forecasts must be
> calibrated for the exact deployed model, prompt, retrieval backend and
> population. The earlier Qwen-0.5B training statistics should **not** be
> reused with newer models.

## API surface

| Endpoint | Function | Any controller LLM calls? |
|---|---|---|
| `GET /health` | Liveness | No |
| `GET /ready` | Configuration status (no secrets) | No |
| `GET /docs` | Auto-generated OpenAPI/Swagger | No |
| `POST /v1/route` | Select the best **provided**, forecast-feasible action | **No** |
| `POST /v1/answer` | Retrieval → select macro → execute 1–2 remote model calls | **No extra** orchestration calls |

### Route-only request (works without provider keys or calibration)

```bash
curl -s -X POST 'https://YOUR-SPACE.hf.space/v1/route' \
  -H "Authorization: Bearer $API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "candidates": [
      {"id":"rag-8b", "predicted_accuracy":0.78,
       "expected_cost_usd":0.0006,"latency_p95_ms":950,"llm_calls":1},
      {"id":"rag-70b", "predicted_accuracy":0.89,
       "expected_cost_usd":0.006,"latency_p95_ms":2100,"llm_calls":1},
      {"id":"iterative-70b", "predicted_accuracy":0.93,
       "expected_cost_usd":0.012,"latency_p95_ms":3800,"llm_calls":2}
    ],
    "budgets":{"max_expected_cost_usd":0.01,"deadline_ms":3000,
               "max_llm_calls":2,"price_per_usd":5,"price_per_second":0.01}
  }'
```

*Those input accuracies, dollar amounts and latencies are **illustrative
request values**, not benchmark results or provider price quotations.* The
service will return the chosen action, scores, rejected actions, and reasons.

### Real RAG inference request

1. Configure both remote model backends using Space secrets/variables.
2. Configure a real search backend implementing the `/search` interface below.
3. Fit a calibration policy on **real LLM traces** from the deployed models.
4. Add the generated `config/policy.json` to the Space before rebuilding,
   or supply explicit `action_forecasts` in your API request for an
   **uncalibrated, operator-estimate** first deployment.

```bash
curl -s -X POST 'https://YOUR-SPACE.hf.space/v1/answer' \
  -H "Authorization: Bearer $API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Which city is the capital of Japan?",
       "budgets":{"deadline_ms":12000,"max_llm_calls":2,
                  "max_retrieval_calls":2,"max_expected_cost_usd":0.02,
                  "price_per_usd":5,"price_per_second":0.02}}'
```

Unlike `/v1/route`, `/v1/answer` actually calls your retriever and selected
LLM(s). The response records chosen action, numerical scores, token usage and
provider-reported cost estimates, measured elapsed time and call counts.

If you do **not** have a trained calibration table yet, send an explicit
`action_forecasts` object in the request instead, using the action names in
`config/actions.json`. Each value must have the same fields as the route-only
`candidates` above. These forecasts are supplied by the operator, **not**
learned by this deployment, and must never be reported as measured accuracy.
Example:

```json
{"action_forecasts": {
  "retrieve_fast": {"id":"retrieve_fast","predicted_accuracy":0.72,
    "expected_cost_usd":0.001,"latency_p95_ms":1500,"llm_calls":1,"retrieval_calls":0},
  "retrieve_strong": {"id":"retrieve_strong","predicted_accuracy":0.83,
    "expected_cost_usd":0.006,"latency_p95_ms":2800,"llm_calls":1,"retrieval_calls":0},
  "iterative_strong": {"id":"iterative_strong","predicted_accuracy":0.87,
    "expected_cost_usd":0.011,"latency_p95_ms":4200,"llm_calls":2,"retrieval_calls":1}
}}
```

These numbers are fictitious **schema examples** and must be replaced with
real operator predictions before assessing effectiveness.

## First-start safeguard

**Do not configure `CALIBRATION_FILE` until `config/policy.json` actually exists.**
The repository intentionally does not include fabricated calibration numbers. The
route-only endpoint can run without model keys or calibration; `/v1/answer`
requires a retriever, model endpoints and either fitted calibration or
request-supplied forecasts. Setting `CALIBRATION_FILE=config/policy.json` before
creating the file prevents the application from starting.

## Set up as a Hugging Face Docker Space

1. Create a new Space, choosing **Docker** SDK (requires appropriate account
   eligibility for compute Spaces). Keep the YAML header above in `README.md`.
2. Upload **all** files at the root of this repository (including `service/`,
   `config/`, `requirements.txt`, `Dockerfile`).
3. Set the environment variables in `ENVIRONMENT.example` in the Space's
   **Settings → Variables/Secrets**, especially a strong random `API_TOKEN`.
   All model API tokens belong in **Secrets** only.
4. Set **FAST_LLM_BASE_URL** and **STRONG_LLM_BASE_URL** to the relevant
   OpenAI-compatible `/v1` URLs. Set `FAST_LLM_MODEL` and `STRONG_LLM_MODEL`
   to the model IDs supplied by those providers. Set `FAST_LLM_KEY_ENV` and
   `STRONG_LLM_KEY_ENV` to the names of the secret variables (e.g. `HF_TOKEN`).
5. Set `RETRIEVAL_URL` to your search service's full HTTPS URL.
6. Calibrate and upload `config/policy.json` (see below). Without it, the
   `/v1/answer` endpoint requires explicit `action_forecasts` supplied by the
   operator; otherwise it responds **503** rather than fake an
   accuracy/cost/latency forecast. `/v1/route` works independently.
7. Wait for the build to finish and use `https://YOUR-SPACE.hf.space/docs`.

HF Docker Spaces expose port **7860** by default. `uvicorn` listens on
`0.0.0.0:7860`; the model weights remain in external serving infrastructure.

**Provider examples:** HF Inference Providers use base URL
`https://router.huggingface.co/v1`; dedicated HF Inference Endpoints, vLLM and
TGI also expose OpenAI-compatible chat completions. Replace model IDs with
models actually supported by your provider. The gateway does not download
models, so it can route to large modern LLMs without expanding Space memory.

**Pricing:** Set model input/output prices explicitly in the environment;
prices are provider-specific and change. Set `RETRIEVAL_USD_PER_CALL`
explicitly (including `0` when the retriever is free) to track retrieval
costs alongside model charges. Monetary ceilings are **forecast**
ceilings, not hard spend caps; actual per-request charges can differ.

## Retrieval service contract

The Space sends `POST $RETRIEVAL_URL` with JSON:

```json
{"query":"What is the capital of Japan?","top_k":5}
```

Your retriever replies:

```json
{"documents":[
  {"id":"doc-101","title":"Tokyo","text":"Tokyo is the capital of Japan.","score":0.91},
  {"id":"doc-102","title":"Japan","text":"Japan is in East Asia.","score":0.42}
]}
```

Production implementations can adapt an existing Qdrant, Elasticsearch,
OpenSearch, Azure AI Search, Vespa, or other search service to this contract.
Use an **external index** for corpus sizes in the millions; do not load a
large vector index inside the CPU Space.

**Security:** The retriever URL and inference URLs are server-controlled
environment variables; clients cannot force arbitrary URLs. The Space API
requires bearer authentication. Provider secrets are not emitted to clients.
Use a separate API gateway with distributed rate limiting, audit logging,
and quotas for public multi-tenant production deployments.

## Fit the policy on real LLM outcomes

The included `fit_policy.py` expects one row **per question and action**, with
all actions tested in each calibration question, from a calibration dataset
separate from the evaluation set.

```csv
bucket,action,correct,cost_usd,latency_ms
c0_g0,retrieve_fast,1,0.0007,750
c0_g0,retrieve_strong,1,0.0051,1750
c0_g0,iterative_strong,1,0.0101,3200
```

The numbers in this CSV snippet are placeholders illustrating the schema,
**not experimental observations**. Do not use them as actual calibration.

Collect actual calibration outcomes from your running API using a
**training-only** JSONL dataset, one `question` and `answers` array per row:

```bash
python collect_calibration.py \
  --api https://YOUR-SPACE.hf.space \
  --questions calibration_train.jsonl \
  --out calibration_traces.csv \
  --raw-jsonl calibration_raw.jsonl --concurrency 4
```

The collector calls all three actions for every calibration question, using
actual model inference and returning the observed prediction, costs, tokens,
and latency. It explicitly forces each action and uses placeholder
`action_forecasts` *only to bypass missing calibration while collecting data*;
these placeholder forecasts are **not** used as empirical accuracy results.
The collector reports failed and unpriced model or retrieval calls. All
calibration actions must succeed and report priced usage before fitting a
dollar-aware policy. Set `RETRIEVAL_USD_PER_CALL` explicitly.

Then fit and upload:

```bash
python fit_policy.py --traces calibration_traces.csv --output config/policy.json
```

For benchmarking, keep calibration questions entirely separate from the
500-question evaluation set.

The empirical-Bayes estimator is

\[
\widehat p(z,a)=\frac{S_{z,a}+\kappa\widehat p_0(a)}{n_z+\kappa},
\qquad
S_a=\widehat p(z,a)-\lambda\widehat c_a-\mu\widehat t_a.
\]

The code uses per-action mean full-workflow cost and empirical p95
**post-preflight latency** from the actual models and retriever traces. This
avoids double-counting initial retrieval time when making the routing decision;
it reproduces the lightweight macro-policy family from the reported experiments. It is not a globally optimal constrained POMDP solver.

**Call budgets:** `max_llm_calls` and `max_retrieval_calls` are enforced before
downstream calls. **Deadlines:** both predicted p95 feasibility screening and
an actual wall-clock timeout are applied. Cancelled HTTP requests may still
incur provider charges. Model-token pricing is computed only if provider usage
metadata and configured prices are both present; unknown usage is disclosed.

## Scale and limitations

- API controller: **O(number of candidate actions)** and no generative LLM
  calls for routing. Numerical scoring happens on CPU.
- Async `httpx` calls with connection pooling; `MAX_INFLIGHT_REQUESTS` bounds
  simultaneous answers per process. Default admission capacity: 64.
- Large model families (8B, 32B, 70B, 120B+) are supported **as external
  OpenAI-compatible endpoints**, not hosted on the Space CPU.
- Throughput and end-to-end latency depend on retriever and model-serving
  provisioned capacity, network latency and rate limits. The supplied
  concurrency number is a **configuration limit, not a measured QPS claim**.
- Horizontal scale requires replicated paid Spaces or a conventional
  container deployment behind a load balancer; per-replica semaphores are not
  distributed quotas.
- Model-call pricing and latency forecasts need periodic recalibration; old
  Qwen-0.5B calibration cannot be assumed valid for a 70B model.
- No SSE streaming, persistent memory, multi-tenant identity, or guaranteed
  hard-dollar expenditure is claimed in this release.

## Run locally and test

```bash
python -m pip install -r requirements.txt pytest
export API_TOKEN=test-only-secret
python -m pytest -q
python bench_controller.py --requests 50000 --actions 20
uvicorn service.api:app --host 0.0.0.0 --port 7860
```

To run the local test retriever:

```bash
uvicorn examples.retriever_stub:app --host 127.0.0.1 --port 7861
```

The stub contains only four public example documents; it is not a
production-scale vector search engine.

## Docker sanity checks

```bash
docker build -t closedform-rag-api .
docker run --rm -p 7860:7860 \
  -e API_TOKEN=test-only-secret closedform-rag-api
curl http://127.0.0.1:7860/health
```

## Artifact and research integrity

The API is deployable infrastructure, not an ESWA benchmark in itself. No
commercial LLM accuracy, price, or latency is invented by this repository.
For a journal evaluation, run this exact API with real 8B/70B providers and
capture paired question-level traces with configured per-provider token prices.
