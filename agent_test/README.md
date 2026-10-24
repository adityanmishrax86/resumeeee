# Job analyzer evaluation

This harness exercises the backend API rather than duplicating its prompt or
LLM call. For every job it:

1. `GET /api/jobs` to list jobs.
2. `GET /api/jobs/{job_id}` to retrieve the complete job.
3. `POST /api/jobs/{job_id}/analyze?background=false` to synchronously analyze it.
4. Checks that all `JobAnalysisResult` fields exist and have the expected
   string/list types, then records a Langfuse evaluation trace.

The API currently persists every successful analysis, so running the harness
again creates another analysis row for each job. Start with `--job-id` to
evaluate one job before running the full collection.

## Configure

Set these variables in `agent_test/.env` (the file is ignored by git):

```dotenv
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
JOB_API_BASE_URL=http://localhost:18000
```

All Langfuse instrumentation and dependencies for this evaluation flow are
contained in this directory. The backend only needs to be running and reachable
at the configured API URL. Traces include job ID, response schema validity, and
the normalized analysis result. Full job content is excluded by default. Set
`LANGFUSE_CAPTURE_CONTENT=true` in this directory's `.env` only when you want
the fetched job details included in trace output.

## Run

From this directory, after installing the project environment:

```powershell
uv sync
uv run main.py --job-id 497f6eca-6276-4993-bfeb-53cbbbba6f08
uv run main.py
```

Use `--base-url http://localhost:18000` to override the API base URL. Exit code
is zero when all selected jobs pass the response contract and one if any fail.

## Validation limits

The current check validates API success and output shape only. It does not
judge whether extracted skills, seniority, or responsibilities are factually
correct. For that, add reviewed reference analyses and score field-level
precision/recall or use Langfuse datasets and evaluators after collecting a
baseline. Also consider making analysis idempotent/upserted before routinely
running the full evaluator, since the current endpoint appends rows.
