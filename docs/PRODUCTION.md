# Scaling, security and provider integration

The API is deployable on a CPU Docker Space because its controller runs **no local LLM weights**. The service *does* make remote calls for `/v1/answer`. The implementation and its calibrated forecasts must be the same in your deployed service as in your client integration.

## What scales today

- `/v1/route`: deterministic CPU work linear in candidate count; no provider calls.
- `/v1/answer`: asynchronous upstream requests, HTTP connection pooling and a per-process `MAX_INFLIGHT_REQUESTS` semaphore (default 64); queue wait is limited by `QUEUE_WAIT_SEC` (default 2).
- The Python async SDK and Node SDK can limit per-client concurrency. Use low concurrency first. External model endpoint and retriever quotas usually dominate.
- A model with tens or hundreds of billions of parameters can run **behind** the Space, provided it exposes an OpenAI-compatible chat endpoint and the Space has provider authorization. A CPU Space does not itself run a 70B model.

## What is NOT established

No load test here proves 64 QPS, 1,000 QPS, or any other public throughput claim. `MAX_INFLIGHT_REQUESTS=64` is an **admission limit**, not measured throughput. Free CPU hardware can sleep and may not have the availability or SLA required for production. One Space replica is not a high-availability service.

## Production deployment topology

```text
Developer / application
    -> API Gateway with per-customer authentication, throttling and quotas
       -> Load balancer / replicated FastAPI containers (or managed Space)
          -> Calibrated closed-form controller (CPU)
             -> External search service (Qdrant/OpenSearch/etc.)
             -> External modern-model endpoints (HF, vLLM, etc.)
```

The bundled `deploy/kubernetes.yaml` is an **illustrative self-hosted deployment template**, not a built/published container image. It requires a real image registry, Kubernetes cluster, metrics server, real provider secrets and a provisioned retrieval backend. For production, put customer authentication in the API gateway. The API itself accepts one shared `API_TOKEN`; that is insufficient for untrusted multi-tenant public access.

## Credential isolation

- `API_TOKEN`: authorization for the gateway API. End-users must receive access from the operator, preferably via customer-specific keys issued by a proper upstream API gateway.
- `HF_TOKEN`: token for the Hugging Face model provider; exists only inside the running Space secrets, never in browser code or the GitHub repository.
- `FAST_LLM_KEY_ENV`, `STRONG_LLM_KEY_ENV`: names of environment variables holding provider keys.
- `RETRIEVAL_API_KEY`: key used by the Space to call its retriever, not given to clients.
- Never place any token into README examples, shell history stored in shared environments, CI logs or source control.

**Do not embed the Space API_TOKEN in a public webpage or mobile app.** It would let anyone spend the operator's provider credits via `/v1/answer`.

## Timeout and billing semantics

`deadline_ms` combines forecast screening with server-side timeout enforcement. Cancelling an HTTP connection cannot cancel bills already incurred at an LLM provider. Forecast `max_expected_cost_usd` is not a bank-like hard charge cap; price changes and provider usage accounting can change the final amount.

SDK policy: retry numerical `/v1/route` on transient errors; do not retry `/v1/answer` without explicit operator approval and an idempotency mechanism. The existing server does not implement an idempotency key.

## Maintaining a calibrated model inventory

1. Configure real model IDs, endpoints and token prices in the Space secret/variable settings.
2. Configure `RETRIEVAL_URL`, a service returning scored documents with the exact contract in `API.md`.
3. Run `collect_calibration.py` against a **training-only** question sample, executing all 3 actions per question on the actual providers.
4. Fit `config/policy.json` using `fit_policy.py`, upload to the Space and set `CALIBRATION_FILE` accordingly.
5. Recalibrate whenever changing models, prompts, retriever scoring scales, pricing, traffic distribution or hardware.

Do not substitute public benchmark average accuracy for calibrated conditional action quality. Do not reuse the old Qwen-0.5B calibration table for 20B/120B endpoints.

## Load tests

Use `python benchmarks/load_route.py --requests 50 --concurrency 4` for authenticated route-only traffic. This does not consume downstream LLM inference. It reports measured client-facing HTTP latency, errors and throughput *for the network and hardware used during that test*. Avoid stress testing the public free Space without permission and rate limits.
