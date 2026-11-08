# Integrating the orchestrator into existing RAG and agentic systems

The low-friction integration point is **POST /v1/route**: your system predicts quality, price, and latency for its available tool or model workflows, calls the gateway to pick one, then **executes that workflow in its own application**. This keeps your document store, agent memory, tools, and provider keys where they already live.

For a ready-to-run full workflow, **POST /v1/answer** has a fixed set of macros and requires the server operator to configure remote LLM and search backends. The SDK does not invent a new action schema or dynamic agent graph.

## Production request flow

```text
User question -> your RAG system -> candidate forecasting
                                     |
                                     v
              POST /v1/route (no LLM) -> SELECT / STOP
                                     |
                                  SELECT
                                     v
                         your retriever + LLM chain
```

The service can work with many LLM model families because `/v1/route` does not invoke any LLM or restrict candidate names; candidate IDs are free strings and each candidate supplies its own quality/cost/latency forecasts. `/v1/answer` is limited to the three configured actions shipped in `config/actions.json`.

### Calibrated route input example

```python
candidate = {
    "id": "team-agent-70b",
    "predicted_accuracy": 0.88,  # Replace with calibrated conditional estimate
    "expected_cost_usd": 0.01,  # Replace with real provider/model forecast
    "latency_p95_ms": 3000,      # Replace with measured forecast
    "llm_calls": 2,
    "retrieval_calls": 1,
}
```

The numbers above are placeholders. Use your own calibration datasets. This module makes **no promises** about the accuracy of these sample candidates.

## Responsible developer access

A GitHub release makes the **code** public, not necessarily the paid `/v1/answer` endpoint. The user-hosted Space requires its own private bearer token. Its operator should manage developer subscriptions, authentication, quotas and credit policies using a gateway before permitting third-party billable calls.
