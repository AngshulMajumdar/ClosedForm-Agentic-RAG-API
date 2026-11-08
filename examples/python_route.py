"""Route candidate workflows without triggering any LLM inference."""
from closedform_rag import ClosedFormRAGClient

CANDIDATES = [
    {"id":"model-fast","predicted_accuracy":0.75,"expected_cost_usd":0.001,
     "latency_p95_ms":800,"llm_calls":1,"retrieval_calls":0},
    {"id":"model-strong","predicted_accuracy":0.86,"expected_cost_usd":0.008,
     "latency_p95_ms":2500,"llm_calls":1,"retrieval_calls":0},
]

if __name__ == "__main__":
    with ClosedFormRAGClient() as api:
        result = api.route(CANDIDATES, budgets={"deadline_ms":3000,"max_llm_calls":1})
        print("Selected:", result["selected"])
        print("Decision LLM calls:", result["decision_llm_calls"])
        print("Rejected:", result["rejected"])
