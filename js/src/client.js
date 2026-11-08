/** Node.js 18+ client for the deployed, unchanged HTTP v1 service. */
export const DEFAULT_URL = "https://angshul-closedform-agentic-rag.hf.space";

const transient = new Set([429, 502, 503, 504]);

export class APIError extends Error {
  constructor(message, { status = null, body = null } = {}) {
    super(message);
    this.name = "APIError";
    this.status = status;
    this.body = body;
  }
}

function validatedUrl(input, allowHttp) {
  const url = new URL(input);
  const isLocal = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.username || url.password || !(url.protocol === "https:" ||
        (url.protocol === "http:" && (allowHttp || isLocal)))) {
    throw new Error("Use HTTPS, or localhost HTTP for development");
  }
  if (url.pathname !== "/" || url.search || url.hash) {
    throw new Error("Pass the API origin, without a path or query");
  }
  return url.origin;
}

function delay(attempt, base, cap, response) {
  const retryAfter = response?.headers?.get?.("retry-after");
  const numeric = Number(retryAfter);
  if (retryAfter && Number.isFinite(numeric) && numeric >= 0) {
    return Math.min(cap, numeric * 1000);
  }
  return Math.min(cap, base * 2 ** attempt) * (0.8 + Math.random() * 0.4);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export class ClosedFormRAGClient {
  constructor({
    baseUrl = DEFAULT_URL,
    apiToken = typeof process !== "undefined" ? process.env.CLOSED_FORM_RAG_API_TOKEN : undefined,
    timeoutMs = 90000,
    routeRetries = 2,
    answerRetries = 0,
    backoffMs = 250,
    maxBackoffMs = 5000,
    allowHttp = false,
    fetchImpl = globalThis.fetch,
  } = {}) {
    if (typeof apiToken !== "string" || !apiToken.trim()) {
      throw new Error("Supply apiToken or CLOSED_FORM_RAG_API_TOKEN");
    }
    if (typeof fetchImpl !== "function") throw new Error("A fetch implementation is required");
    this.baseUrl = validatedUrl(baseUrl, allowHttp);
    this.apiToken = apiToken;
    this.timeoutMs = timeoutMs;
    this.routeRetries = Math.max(0, Math.floor(routeRetries));
    this.answerRetries = Math.max(0, Math.floor(answerRetries));
    this.backoffMs = backoffMs;
    this.maxBackoffMs = maxBackoffMs;
    this.fetchImpl = fetchImpl;
  }

  async request(path, payload, { method = "POST", retries = 0, signal } = {}) {
    for (let attempt = 0; attempt <= retries; ++attempt) {
      const timer = new AbortController();
      let abortedByTimeout = false;
      const listener = () => timer.abort();
      if (signal) {
        if (signal.aborted) timer.abort();
        else signal.addEventListener("abort", listener, { once: true });
      }
      const deadline = setTimeout(() => { abortedByTimeout = true; timer.abort(); }, this.timeoutMs);
      let response = null;
      try {
        response = await this.fetchImpl(this.baseUrl + path, {
          method,
          headers: {
            Authorization: `Bearer ${this.apiToken}`,
            Accept: "application/json",
            ...(payload === undefined ? {} : { "Content-Type": "application/json" }),
          },
          ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
          signal: timer.signal,
        });
        if (transient.has(response.status) && attempt < retries) {
          await sleep(delay(attempt, this.backoffMs, this.maxBackoffMs, response));
          continue;
        }
        let value = null;
        try { value = await response.json(); } catch { /* invalid JSON */ }
        if (!response.ok) {
          const detail = typeof value?.detail === "string" ? value.detail.slice(0, 250) : "Request failed";
          throw new APIError(`HTTP ${response.status}: ${detail}`, { status: response.status, body: value });
        }
        if (!value || Array.isArray(value) || typeof value !== "object") {
          throw new APIError("API response is not a JSON object", { status: response.status });
        }
        return value;
      } catch (err) {
        if (err instanceof APIError) throw err;
        if (signal?.aborted) throw new APIError("Request cancelled by caller; outcome may be unknown");
        if (attempt >= retries) {
          throw new APIError(abortedByTimeout ? "Request timed out; outcome may be unknown" :
            "Network error; outcome may be unknown");
        }
        await sleep(delay(attempt, this.backoffMs, this.maxBackoffMs, response));
      } finally {
        clearTimeout(deadline);
        signal?.removeEventListener?.("abort", listener);
      }
    }
    throw new Error("unreachable");
  }

  health() { return this.request("/health", undefined, { method: "GET", retries: this.routeRetries }); }
  ready() { return this.request("/ready", undefined, { method: "GET", retries: this.routeRetries }); }

  route(candidates, budgets, options = {}) {
    const payload = {
      candidates,
      ...(budgets ? { budgets } : {}),
      sunk_cost_usd: options.sunk_cost_usd ?? 0,
      sunk_latency_ms: options.sunk_latency_ms ?? 0,
      sunk_retrieval_calls: options.sunk_retrieval_calls ?? 0,
    };
    return this.request("/v1/route", payload, { retries: this.routeRetries, signal: options.signal });
  }

  answer(question, budgets, options = {}) {
    if (typeof question !== "string" || !question.trim()) throw new Error("question is required");
    const payload = {
      question,
      ...(budgets ? { budgets } : {}),
      ...(options.allowed_actions ? { allowed_actions: options.allowed_actions } : {}),
      ...(options.action_forecasts ? { action_forecasts: options.action_forecasts } : {}),
      ...(options.quality_estimates ? { quality_estimates: options.quality_estimates } : {}),
    };
    // No automatic retries of billable model calls without explicit opt-in.
    return this.request("/v1/answer", payload, { retries: this.answerRetries, signal: options.signal });
  }

  async batchAnswers(questions, budgets, { concurrency = 4, returnErrors = false, ...options } = {}) {
    if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error("concurrency must be positive");
    const inputs = Array.from(questions);
    const results = new Array(inputs.length);
    let cursor = 0;
    let firstFailure = null;
    const worker = async () => {
      while (cursor < inputs.length && (returnErrors || firstFailure === null)) {
        const i = cursor++;
        try { results[i] = await this.answer(inputs[i], budgets, options); }
        catch (err) {
          if (!returnErrors) firstFailure ??= err;
          results[i] = err;
        }
      }
    };
    // Wait for already-started requests before reporting an error. Otherwise a
    // caller could see an exception while billable requests were still active.
    await Promise.all(Array.from({ length: Math.min(concurrency, inputs.length) }, worker));
    if (firstFailure !== null) throw firstFailure;
    return results;
  }
}
