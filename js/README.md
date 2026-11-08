# Node.js / TypeScript client

Requires Node.js 18+. Calls the **existing** `/v1/route` and `/v1/answer` endpoints; it does not deploy any model.

```bash
npm install ./js
export CLOSED_FORM_RAG_API_TOKEN=YOUR_GATEWAY_TOKEN
```

```js
import { ClosedFormRAGClient } from 'closedform-agentic-rag-client';
const client = new ClosedFormRAGClient();
const result = await client.route([
  {id:'fast',predicted_accuracy:0.72,expected_cost_usd:0.001,latency_p95_ms:800,llm_calls:1},
  {id:'strong',predicted_accuracy:0.86,expected_cost_usd:0.008,latency_p95_ms:2400,llm_calls:1}
], {max_llm_calls:1,deadline_ms:3000,max_expected_cost_usd:0.01});
console.log(result.selected, result.decision_llm_calls);
```

For live RAG answering, the Space operator must configure model backends, a retrieval endpoint, and calibrated action forecasts. See `../docs/API.md`.

`routeRetries` defaults to 2; `answerRetries` defaults to **0** to prevent accidental duplicate chargeable requests. `batchAnswers` bounds the number of concurrent requests on the *client*. Server quotas are independent.

Use **server-side Node.js**, not browser code embedding a shared Space bearer token.
