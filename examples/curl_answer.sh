#!/usr/bin/env bash
set -euo pipefail
: "${CLOSED_FORM_RAG_API_TOKEN:?Set CLOSED_FORM_RAG_API_TOKEN to the operator-issued gateway token}"
BASE_URL="${CLOSED_FORM_RAG_API_URL:-https://angshul-closedform-agentic-rag.hf.space}"
# This request may incur provider charges. Requires Space operator configuration.
curl --fail-with-body -sS "${BASE_URL}/v1/answer" \
  -H "Authorization: Bearer ${CLOSED_FORM_RAG_API_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data '{"question":"What is the capital of Japan?","budgets":{"max_expected_cost_usd":0.02,"deadline_ms":12000,"max_llm_calls":2,"max_retrieval_calls":2}}'
