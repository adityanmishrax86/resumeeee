"""Run the job-analyzer API for every job and emit Langfuse evaluation traces."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client


def request_json(url: str, method: str = "GET") -> Any:
    request = Request(url, method=method, headers={"Accept": "application/json"})
    with urlopen(request, timeout=120) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def evaluate(base_url: str, only_job_id: str | None = None) -> int:
    langfuse = get_client()
    jobs = request_json(f"{base_url.rstrip('/')}/api/jobs")
    if not isinstance(jobs, list):
        raise ValueError("GET /api/jobs did not return a JSON array")
    if only_job_id:
        jobs = [job for job in jobs if str(job.get("id")) == only_job_id]

    if not jobs:
        print("No jobs selected.")
        return 0

    passed = failed = 0
    for listed_job in jobs:
        job_id = str(listed_job["id"])
        encoded_id = quote(job_id, safe="")
        with langfuse.start_as_current_observation(
            as_type="span",
            name="job-analysis-evaluation",
            input={"job_id": job_id},
        ) as trace:
            try:
                job = request_json(f"{base_url.rstrip('/')}/api/jobs/{encoded_id}")
                result = request_json(
                    f"{base_url.rstrip('/')}/api/jobs/{encoded_id}/analyze?background=false",
                    method="POST",
                )
                # Basic contract validation: endpoint success and all expected
                # schema fields present with the expected scalar/list types.
                list_fields = (
                    "required_skills", "preferred_skills", "programming_languages",
                    "tools", "frameworks", "ats_keywords", "responsibilities",
                )
                string_fields = ("experience_required", "seniority_level", "domain", "summary")
                problems = [f"missing field: {key}" for key in (*list_fields, *string_fields) if key not in result]
                problems.extend(f"{key} must be an array" for key in list_fields if key in result and not isinstance(result[key], list))
                problems.extend(f"{key} must be a string" for key in string_fields if key in result and not isinstance(result[key], str))
                passed_job = not problems
                if passed_job:
                    passed += 1
                else:
                    failed += 1

                output: dict[str, Any] = {
                    "schema_valid": passed_job,
                    "problems": problems,
                    "result": result,
                }
                if os.getenv("LANGFUSE_CAPTURE_CONTENT", "false").lower() in {"1", "true", "yes"}:
                    output["job"] = job
                else:
                    output["job"] = {
                        key: job.get(key)
                        for key in ("id", "company_name", "role_title", "source", "created_at")
                    }
                trace.update(output=output, metadata={"job_id": job_id, "schema_valid": passed_job})
                print(f"{'PASS' if passed_job else 'FAIL'} {job_id}: {job.get('company_name')} / {job.get('role_title')}")
                if problems:
                    print("  " + "; ".join(problems))
            except (HTTPError, URLError, ValueError, KeyError) as exc:
                failed += 1
                trace.update(level="ERROR", status_message=f"{type(exc).__name__}: {exc}")
                print(f"FAIL {job_id}: {type(exc).__name__}: {exc}", file=sys.stderr)

    langfuse.flush()
    print(f"\nEvaluation complete: {passed} passed, {failed} failed, {passed + failed} total")
    return 1 if failed else 0


def main() -> int:
    load_dotenv(Path(__file__).with_name(".env"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=os.getenv("JOB_API_BASE_URL", "http://localhost:8000"),
        help="Backend API base URL (default: JOB_API_BASE_URL or http://localhost:18000)",
    )
    parser.add_argument("--job-id", help="Evaluate one job ID instead of all listed jobs")
    args = parser.parse_args()
    return evaluate(args.base_url, args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())
