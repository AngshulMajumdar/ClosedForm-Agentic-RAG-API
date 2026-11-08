/** Run from the repository root: node examples/node_route.mjs */
import { ClosedFormRAGClient } from '../js/src/client.js';
const api = new ClosedFormRAGClient();
const selection = await api.route([
  {id:'fast',predicted_accuracy:.76,expected_cost_usd:.001,latency_p95_ms:900,llm_calls:1},
  {id:'strong',predicted_accuracy:.87,expected_cost_usd:.009,latency_p95_ms:2200,llm_calls:1},
], {max_expected_cost_usd:.01,deadline_ms:3000,max_llm_calls:1});
console.log(selection.selected, 'decision LLM calls:', selection.decision_llm_calls);
