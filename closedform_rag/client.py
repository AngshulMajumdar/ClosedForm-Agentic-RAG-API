"""Reusable synchronous/asynchronous HTTP clients for the unchanged v1 API.

No model keys, provider secrets, predictions, or numeric calibration live here.
Only the caller's *gateway API token* is used.  The service itself owns all
model-inference and retrieval secrets.

/v1/route can be safely retried for transient failures.
/v1/answer is NOT retried unless the caller explicitly opts in, since the
provider may have billed the first attempt even if the response was lost.
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

import httpx

DEFAULT_URL = "https://angshul-closedform-agentic-rag.hf.space"
TRANSIENT_STATUSES = frozenset((429, 502, 503, 504))


class APIError(RuntimeError):
    """Sanitized API error; includes status and optional response data, never keys."""

    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _base(base_url: str, allow_http: bool) -> str:
    value = base_url.rstrip("/")
    parsed = urlsplit(value)
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.password:
        raise ValueError("Pass the API origin without a path, query, or credentials")
    if parsed.scheme == "https" and parsed.netloc and not parsed.username:
        return value
    if parsed.scheme == "http" and parsed.netloc and not parsed.username and (
        allow_http or parsed.hostname in ("localhost", "127.0.0.1", "::1")
    ):
        return value
    raise ValueError("Use an HTTPS API URL (HTTP permitted only for localhost or allow_http=True)")


def _token(value: str | None) -> str:
    result = value if value is not None else os.getenv("CLOSED_FORM_RAG_API_TOKEN", "")
    if not result.strip():
        raise ValueError("Supply api_token or set CLOSED_FORM_RAG_API_TOKEN")
    return result


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _error(response: httpx.Response) -> APIError:
    data = _body(response)
    detail = data.get("detail", "Request failed") if isinstance(data, dict) else "Request failed"
    if not isinstance(detail, str):
        detail = "Request failed"
    detail = detail[:250]
    return APIError(f"HTTP {response.status_code}: {detail}", status_code=response.status_code, body=data)


def _pause(response: httpx.Response | None, attempt: int, base_delay: float, max_delay: float) -> float:
    if response is not None:
        after = response.headers.get("retry-after")
        if after:
            try:
                return max(0, min(max_delay, float(after)))
            except ValueError:
                pass
    return min(max_delay, base_delay * 2**attempt) * random.uniform(0.8, 1.2)


def _payload(
    question: str,
    budgets: Mapping[str, Any] | None,
    allowed_actions: Sequence[str] | None,
    action_forecasts: Mapping[str, Any] | None,
    quality_estimates: Mapping[str, float] | None,
) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a nonempty string")
    result: dict[str, Any] = {"question": question}
    if budgets is not None:
        result["budgets"] = dict(budgets)
    if allowed_actions is not None:
        result["allowed_actions"] = list(allowed_actions)
    if action_forecasts is not None:
        result["action_forecasts"] = dict(action_forecasts)
    if quality_estimates is not None:
        result["quality_estimates"] = dict(quality_estimates)
    return result


class ClosedFormRAGClient:
    """Thread-safe connection-pooled sync client (httpx.Client shared across calls)."""

    def __init__(
        self,
        api_token: str | None = None,
        base_url: str = DEFAULT_URL,
        *,
        timeout: float = 90.0,
        route_retries: int = 2,
        answer_retries: int = 0,
        backoff: float = 0.25,
        max_backoff: float = 5.0,
        max_connections: int = 100,
        allow_http: bool = False,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = _base(base_url, allow_http)
        self._token = _token(api_token)
        self.route_retries = max(0, int(route_retries))
        self.answer_retries = max(0, int(answer_retries))
        self.backoff = float(backoff)
        self.max_backoff = float(max_backoff)
        self._own = http_client is None
        self._http = http_client or httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=min(20, max_connections)),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._own:
            self._http.close()

    def __enter__(self) -> "ClosedFormRAGClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, *, payload: Any = None, retries: int = 0) -> dict[str, Any]:
        response = None
        for attempt in range(retries + 1):
            try:
                response = self._http.request(
                    method, self.base_url + path,
                    headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"},
                    json=payload,
                )
                if response.status_code in TRANSIENT_STATUSES and attempt < retries:
                    time.sleep(_pause(response, attempt, self.backoff, self.max_backoff))
                    continue
                if response.is_error:
                    raise _error(response)
                result = _body(response)
                if not isinstance(result, dict):
                    raise APIError("API response was not a JSON object", status_code=response.status_code)
                return result
            except (httpx.TimeoutException, httpx.TransportError) as ex:
                if attempt >= retries:
                    raise APIError(f"Network error ({type(ex).__name__}); request outcome may be unknown") from ex
                time.sleep(_pause(None, attempt, self.backoff, self.max_backoff))
        raise AssertionError("unreachable")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", retries=self.route_retries)

    def ready(self) -> dict[str, Any]:
        return self._request("GET", "/ready", retries=self.route_retries)

    def route(
        self,
        candidates: Sequence[Mapping[str, Any]],
        budgets: Mapping[str, Any] | None = None,
        *,
        sunk_cost_usd: float = 0.0,
        sunk_latency_ms: float = 0.0,
        sunk_retrieval_calls: int = 0,
    ) -> dict[str, Any]:
        payload = {
            "candidates": [dict(x) for x in candidates],
            "sunk_cost_usd": sunk_cost_usd,
            "sunk_latency_ms": sunk_latency_ms,
            "sunk_retrieval_calls": sunk_retrieval_calls,
        }
        if budgets is not None:
            payload["budgets"] = dict(budgets)
        return self._request("POST", "/v1/route", payload=payload, retries=self.route_retries)

    def answer(
        self,
        question: str,
        budgets: Mapping[str, Any] | None = None,
        *,
        allowed_actions: Sequence[str] | None = None,
        action_forecasts: Mapping[str, Any] | None = None,
        quality_estimates: Mapping[str, float] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST", "/v1/answer",
            payload=_payload(question, budgets, allowed_actions, action_forecasts, quality_estimates),
            retries=self.answer_retries,
        )

    def batch_answer(
        self,
        questions: Sequence[str],
        budgets: Mapping[str, Any] | None = None,
        *,
        concurrency: int = 4,
        return_exceptions: bool = False,
        **answer_options: Any,
    ) -> list[Any]:
        """Client-side fan-out; no server batch endpoint exists. Preserves order.

        Never choose a concurrency above the service account's applicable rate
        and provider limits. Each question can incur LLM and retrieval charges.
        """
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(self.answer, q, budgets, **answer_options) for q in questions]
            output = []
            for f in futures:
                try:
                    output.append(f.result())
                except Exception as ex:
                    if not return_exceptions:
                        raise
                    output.append(ex)
            return output


class AsyncClosedFormRAGClient:
    """Connection-pooled asyncio client with bounded-concurrency batch calls."""

    def __init__(
        self,
        api_token: str | None = None,
        base_url: str = DEFAULT_URL,
        *,
        timeout: float = 90.0,
        route_retries: int = 2,
        answer_retries: int = 0,
        backoff: float = 0.25,
        max_backoff: float = 5.0,
        max_connections: int = 100,
        allow_http: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.base_url = _base(base_url, allow_http)
        self._token = _token(api_token)
        self.route_retries = max(0, int(route_retries))
        self.answer_retries = max(0, int(answer_retries))
        self.backoff = float(backoff)
        self.max_backoff = float(max_backoff)
        self._own = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=min(20, max_connections)),
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        if self._own:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncClosedFormRAGClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _request(self, method: str, path: str, *, payload: Any = None, retries: int = 0) -> dict[str, Any]:
        for attempt in range(retries + 1):
            try:
                response = await self._http.request(
                    method, self.base_url + path,
                    headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"},
                    json=payload,
                )
                if response.status_code in TRANSIENT_STATUSES and attempt < retries:
                    await asyncio.sleep(_pause(response, attempt, self.backoff, self.max_backoff))
                    continue
                if response.is_error:
                    raise _error(response)
                result = _body(response)
                if not isinstance(result, dict):
                    raise APIError("API response was not a JSON object", status_code=response.status_code)
                return result
            except (httpx.TimeoutException, httpx.TransportError) as ex:
                if attempt >= retries:
                    raise APIError(f"Network error ({type(ex).__name__}); request outcome may be unknown") from ex
                await asyncio.sleep(_pause(None, attempt, self.backoff, self.max_backoff))
        raise AssertionError("unreachable")

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health", retries=self.route_retries)

    async def ready(self) -> dict[str, Any]:
        return await self._request("GET", "/ready", retries=self.route_retries)

    async def route(
        self,
        candidates: Sequence[Mapping[str, Any]],
        budgets: Mapping[str, Any] | None = None,
        *,
        sunk_cost_usd: float = 0.0,
        sunk_latency_ms: float = 0.0,
        sunk_retrieval_calls: int = 0,
    ) -> dict[str, Any]:
        payload = {
            "candidates": [dict(x) for x in candidates],
            "sunk_cost_usd": sunk_cost_usd,
            "sunk_latency_ms": sunk_latency_ms,
            "sunk_retrieval_calls": sunk_retrieval_calls,
        }
        if budgets is not None:
            payload["budgets"] = dict(budgets)
        return await self._request("POST", "/v1/route", payload=payload, retries=self.route_retries)

    async def answer(
        self,
        question: str,
        budgets: Mapping[str, Any] | None = None,
        *,
        allowed_actions: Sequence[str] | None = None,
        action_forecasts: Mapping[str, Any] | None = None,
        quality_estimates: Mapping[str, float] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST", "/v1/answer",
            payload=_payload(question, budgets, allowed_actions, action_forecasts, quality_estimates),
            retries=self.answer_retries,
        )

    async def batch_answer(
        self,
        questions: Sequence[str],
        budgets: Mapping[str, Any] | None = None,
        *,
        concurrency: int = 4,
        return_exceptions: bool = False,
        **answer_options: Any,
    ) -> list[Any]:
        if concurrency < 1:
            raise ValueError("concurrency must be positive")
        gate = asyncio.Semaphore(concurrency)

        async def task(question: str) -> dict[str, Any]:
            async with gate:
                return await self.answer(question, budgets, **answer_options)

        return await asyncio.gather(*(task(q) for q in questions), return_exceptions=return_exceptions)
