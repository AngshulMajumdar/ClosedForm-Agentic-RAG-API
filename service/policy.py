"""Numerical, closed-form, zero-LLM-call action selection.

This is a *contextual macro-action* relaxation. It does not solve the general POMDP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Candidate:
    id: str
    predicted_accuracy: float
    expected_cost_usd: float
    latency_p95_ms: float
    llm_calls: int
    retrieval_calls: int = 0

    def __post_init__(self) -> None:
        if not self.id or not 0 <= self.predicted_accuracy <= 1:
            raise ValueError("Invalid candidate id or accuracy")
        if (self.expected_cost_usd < 0 or self.latency_p95_ms < 0
                or self.llm_calls < 0 or self.retrieval_calls < 0):
            raise ValueError("Resources must be nonnegative")


@dataclass(frozen=True)
class Limits:
    max_expected_cost_usd: float | None = None
    deadline_ms: float | None = None
    max_llm_calls: int | None = None
    max_retrieval_calls: int | None = None
    price_per_usd: float = 1.0
    price_per_second: float = 0.01
    stop_utility: float = -1.0


def select(candidates: Iterable[Candidate], limits: Limits,
           sunk_cost_usd: float = 0.0, sunk_latency_ms: float = 0.0,
           sunk_retrieval_calls: int = 0) -> dict:
    """O(number_of_actions) deterministic selection; forecast-based feasibility.

    A hard deadline is enforced separately by the execution engine; forecasts
    alone cannot guarantee a provider's queueing-time or token-based charges.
    """
    if limits.price_per_usd < 0 or limits.price_per_second < 0:
        raise ValueError("Shadow prices must be nonnegative")
    if any(x is not None and x < 0 for x in (
        limits.max_expected_cost_usd, limits.deadline_ms,
        limits.max_llm_calls, limits.max_retrieval_calls)):
        raise ValueError("Limits must be nonnegative")
    feasible = []
    rejected = []
    for a in candidates:
        issues = []
        if limits.max_expected_cost_usd is not None and a.expected_cost_usd + sunk_cost_usd > limits.max_expected_cost_usd + 1e-12:
            issues.append("projected_cost")
        if limits.deadline_ms is not None and a.latency_p95_ms + sunk_latency_ms > limits.deadline_ms + 1e-9:
            issues.append("predicted_deadline")
        if limits.max_llm_calls is not None and a.llm_calls > limits.max_llm_calls:
            issues.append("call_limit")
        if limits.max_retrieval_calls is not None and a.retrieval_calls + sunk_retrieval_calls > limits.max_retrieval_calls:
            issues.append("retrieval_limit")
        score = a.predicted_accuracy - limits.price_per_usd * a.expected_cost_usd - limits.price_per_second * (a.latency_p95_ms / 1000.0)
        item = dict(id=a.id, score=round(score, 8), expected_accuracy=a.predicted_accuracy,
                    expected_cost_usd=a.expected_cost_usd, latency_p95_ms=a.latency_p95_ms,
                    llm_calls=a.llm_calls, retrieval_calls=a.retrieval_calls)
        if issues:
            rejected.append(dict(**item, reasons=issues))
        else:
            feasible.append(item)
    best = max(feasible, key=lambda z: (z["score"], -z["expected_cost_usd"], z["id"])) if feasible else None
    if best is None or best["score"] <= limits.stop_utility:
        return {"selected": "STOP", "selected_prediction": None, "candidates": feasible,
                "rejected": rejected, "decision_llm_calls": 0,
                "reason": "No feasible action with utility greater than stop utility"}
    return {"selected": best["id"], "selected_prediction": best,
            "candidates": feasible, "rejected": rejected, "decision_llm_calls": 0,
            "reason": "Maximum estimated scalarized utility among forecast-feasible actions"}


def query_bucket(question: str, retrieval_scores: list[float], gap_threshold: float = 0.07) -> str:
    """Matches the four-bucket feature mapping used in the Qwen pilot.

    A different retriever must be recalibrated: its scores may have different scales.
    """
    q = question.lower().strip()
    comparative = int(q.startswith(("are ", "is ", "were ", "do ", "does ", "did ",
                                      "which of ", "who is older", "who was older")))
    gap = float(retrieval_scores[0] - retrieval_scores[1]) if len(retrieval_scores) >= 2 else 0.0
    return f"c{comparative}_g{int(gap >= gap_threshold)}"
