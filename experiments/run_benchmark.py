"""Run the controlled benchmark against the running FastAPI service.

This script is intentionally opt-in: it makes real provider calls and therefore
can incur API charges. It does not store API keys and it never writes benchmark
results back to GitHub automatically.

Example:
    python experiments/run_benchmark.py --base-url http://localhost:8000

The script first collects one independent response per task/model. Routing
strategies can then be replayed offline from the collected observations, which
avoids making a second paid request merely to compare strategies.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "benchmarks" / "tasks.json"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "results" / "raw_results.json"


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> dict | list:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {base_url}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--task-limit", type=int, default=None)
    parser.add_argument("--min-quality", type=int, default=80)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between provider calls")
    args = parser.parse_args()

    if args.min_quality < 0 or args.min_quality > 100:
        parser.error("--min-quality must be between 0 and 100")

    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if args.task_limit:
        tasks = tasks[: args.task_limit]

    models = request_json(args.base_url, "/api/models")
    models = [m for m in models if m.get("status") == "active"]
    if not models:
        raise RuntimeError("No active models are registered in the backend.")

    print(f"Benchmarking {len(tasks)} tasks across {len(models)} active models.")
    print("WARNING: this performs real LLM API calls and may incur charges.")

    observations: list[dict] = []
    started = datetime.now(timezone.utc).isoformat()

    for task_index, task in enumerate(tasks, start=1):
        for model in models:
            print(f"[{task_index}/{len(tasks)}] {task['id']} -> {model['provider_name']} / {model['model_name']}")
            payload = {
                "prompt": task["prompt"],
                "mode": "manual",
                "min_quality": 0,
                "manual_model_id": model["model_id"],
            }
            try:
                result = request_json(args.base_url, "/api/requests", "POST", payload)
                observations.append({
                    "task_id": task["id"],
                    "category": task["category"],
                    "quality_criteria": task["quality_criteria"],
                    "model": model,
                    "result": result,
                })
            except RuntimeError as exc:
                observations.append({
                    "task_id": task["id"],
                    "category": task["category"],
                    "quality_criteria": task["quality_criteria"],
                    "model": model,
                    "error": str(exc),
                })
            time.sleep(max(0.0, args.delay))

    output = {
        "schema_version": 1,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "min_quality_for_analysis": args.min_quality,
        "task_count": len(tasks),
        "model_count": len(models),
        "observations": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved raw benchmark observations to {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Benchmark interrupted.", file=sys.stderr)
        raise SystemExit(130)
