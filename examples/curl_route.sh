#!/usr/bin/env bash
set -euo pipefail
: "${CLOSED_FORM_RAG_API_TOKEN:?Set CLOSED_FORM_RAG_API_TOKEN to the operator-issued gateway token}"
BASE_URL="${CLOSED_FORM_RAG_API_URL:-https://angshul-closedform-agentic-rag.hf.space}"
curl --fail-with-body -sS "${BASE_URL}/v1/route" \
  -H "Authorization: Bearer ${CLOSED_FORM_RAG_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data '{"candidates":[{"id":"fast","predicted_accuracy":0.80,"expected_cost_usd":0.001,"latency_p95_ms":900,"llm_calls":1}],"budgets":{"max_llm_calls":1,"deadline_ms":3000}}'
