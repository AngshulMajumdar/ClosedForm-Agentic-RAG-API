# Publishing this package to GitHub

**Recommended GitHub repository:** `AngshulMajumdar/ClosedForm-Agentic-RAG-API`

Repository creation page: https://github.com/new?name=ClosedForm-Agentic-RAG-API

After creating the repository on the **main** branch, open the repository's upload form:

https://github.com/AngshulMajumdar/ClosedForm-Agentic-RAG-API/upload/main

Unzip the accompanying archive. Upload all **extracted files and directories**, not the ZIP itself. Preserve `service/`, `closedform_rag/`, `js/`, `docs/`, `tests/`, `api/`, and `config/` paths. You may need to create an initial commit on a new repository before the `/upload/main` path is available. Do not include tokens or secret files.

If using Git locally instead of the web uploader:

```bash
git init -b main
git add README.md LICENSE pyproject.toml Dockerfile requirements.txt ENVIRONMENT.example \
  service config closedform_rag js docs api examples tests benchmarks deploy reports scripts \
  bench_controller.py collect_calibration.py fit_policy.py
git commit -m "Release unchanged Docker API with scalable Python and JS clients"
git remote add origin https://github.com/AngshulMajumdar/ClosedForm-Agentic-RAG-API.git
git push -u origin main
```

Use the GitHub UI if local git commands are inconvenient. The existing Hugging Face Space does not need to be redeployed for SDK users to call the **same** published API.

**Suggested GitHub description (less than 350 characters):** Closed-form agentic RAG orchestration API with cost, latency and call budgets. CPU FastAPI gateway for modern LLM endpoints, Python/TypeScript SDKs, concurrent clients, calibrated routing, OpenAPI schema and deployment tests.

**Access warning:** The existing Space has one shared `API_TOKEN`. Do not publish it in this repository. Use a separate gateway for multi-user developer keys, quotas, and billing if allowing public billable `/v1/answer` calls.
