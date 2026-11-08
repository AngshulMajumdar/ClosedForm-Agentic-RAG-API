# Test report — local code validation

The GitHub API repository was built using the tested `ClosedForm-Agentic-RAG_Docker_Final_YAML_Fixed.zip` as its exact original Space source. The server files were **not changed**; developer SDKs, docs, tests, and optional deployment guidance were added. The Space README is preserved byte for byte at `docs/HF_SPACE_README.md`.

## Reproduction commands

```bash
python -m pip install -r requirements.txt
python -m pip install -e . pytest
python scripts/verify_compatibility.py
python -m pytest -q
node --test js/tests/client.test.mjs
```

Python tests cover the original server selector and mocked end-to-end retrieval/LLM path, SDK payloads/authentication, route retry behavior, no automatic answer replay, bounded async fan-out, and exact `/openapi.json` schema. JavaScript tests cover the deployed request contract, token header, answer no-retry, route retry and bounded fan-out.

These tests do **not** invoke real paid LLM providers or demonstrate production throughput. Runtime host availability, provider inference, authentication/quotas and retrieval performance require separate deployment checks.

## Scale claim boundaries

`MAX_INFLIGHT_REQUESTS=64` is the original per-process admission setting, not throughput. The numerical policy itself is linear-time in the number of alternatives. The package includes a *route-only* load tester with conservative network concurrency. Horizontal scale requires additional replicas and gateway controls.
