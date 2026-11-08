export type Budgets = {
  max_expected_cost_usd?: number | null;
  deadline_ms?: number | null;
  max_llm_calls?: number | null;
  max_retrieval_calls?: number | null;
  price_per_usd?: number;
  price_per_second?: number;
  stop_utility?: number;
};
export interface Candidate {
  id: string;
  predicted_accuracy: number;
  expected_cost_usd: number;
  latency_p95_ms: number;
  llm_calls: number;
  retrieval_calls?: number;
}
export interface RouteResult {
  selected: string;
  selected_prediction: object | null;
  candidates: object[];
  rejected: object[];
  decision_llm_calls: number;
  reason: string;
}
export interface AnswerResult {
  selected_action: string;
  answer: string | null;
  elapsed_ms: number;
  routing?: RouteResult;
  resources?: {
    model_calls: number;
    retrieval_calls: number;
    input_tokens: number;
    output_tokens: number;
    measured_cost_usd: number;
    total_estimated_cost_usd: number | null;
  };
}
export class APIError extends Error {
  status: number | null;
  body: unknown;
}
export const DEFAULT_URL: string;
export class ClosedFormRAGClient {
  constructor(options?: {
    apiToken?: string;
    baseUrl?: string;
    timeoutMs?: number;
    routeRetries?: number;
    answerRetries?: number;
    backoffMs?: number;
    maxBackoffMs?: number;
    allowHttp?: boolean;
    fetchImpl?: typeof fetch;
  });
  health(): Promise<Record<string, unknown>>;
  ready(): Promise<Record<string, unknown>>;
  route(candidates: Candidate[], budgets?: Budgets, options?: {
    sunk_cost_usd?: number;
    sunk_latency_ms?: number;
    sunk_retrieval_calls?: number;
    signal?: AbortSignal;
  }): Promise<RouteResult>;
  answer(question: string, budgets?: Budgets, options?: {
    allowed_actions?: string[];
    action_forecasts?: Record<string, Candidate>;
    quality_estimates?: Record<string, number>;
    signal?: AbortSignal;
  }): Promise<AnswerResult>;
  batchAnswers(questions: Iterable<string>, budgets?: Budgets, options?: {
    concurrency?: number;
    returnErrors?: boolean;
    allowed_actions?: string[];
    action_forecasts?: Record<string, Candidate>;
    quality_estimates?: Record<string, number>;
    signal?: AbortSignal;
  }): Promise<(AnswerResult | Error)[]>;
}
