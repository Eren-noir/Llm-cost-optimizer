"""Analyze raw benchmark observations without making new provider calls.

The analysis replays two routing policies using information that would be
available to the router before a request is sent: model registry quality,
estimated cost and, when available, historical latency. The selected model's
*observed* quality/cost/latency are then used for the outcome metrics.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


STRATEGIES = ("baseline", "weighted_scoring")


def d(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value))


def weighted_score(row: dict) -> Decimal:
    estimated_cost = d(row["result"]["estimated_cost_usd"])
    quality = d(row["model"]["estimated_quality"]) / Decimal(100)
    latency = row["result"].get("latency_ms")

    # Benchmark observations are independent manual calls, so actual latency
    # is not a valid pre-request signal. Keep the latency component neutral.
    latency_score = Decimal("0.5") if latency is not None else Decimal("0.5")
    # Cost is normalized per task below; this function is replaced by the
    # task-level scorer where min/max values are known.
    return estimated_cost + quality + latency_score


def choose(rows: list[dict], strategy: str, min_quality: int) -> dict | None:
    eligible = [
        r for r in rows
        if "result" in r
        and r["result"].get("status") == "success"
        and int(r["model"]["estimated_quality"]) >= min_quality
    ]
    if not eligible:
        return None

    if strategy == "baseline":
        return min(eligible, key=lambda r: d(r["result"]["estimated_cost_usd"]))

    costs = [d(r["result"]["estimated_cost_usd"]) for r in eligible]
    min_cost, max_cost = min(costs), max(costs)
    cost_range = max_cost - min_cost

    def score(row: dict) -> Decimal:
        cost = d(row["result"]["estimated_cost_usd"])
        cost_term = Decimal(1) if cost_range == 0 else (max_cost - cost) / cost_range
        quality_term = d(row["model"]["estimated_quality"]) / Decimal(100)
        # The independent benchmark does not have pre-request latency
        # history, so latency is held neutral rather than leaking actual
        # latency into the routing decision.
        latency_term = Decimal("0.5")
        return Decimal("0.5") * cost_term + Decimal("0.4") * quality_term + Decimal("0.1") * latency_term

    return max(eligible, key=score)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--min-quality", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    min_quality = data.get("min_quality_for_analysis", 80) if args.min_quality is None else args.min_quality

    by_task: dict[str, list[dict]] = defaultdict(list)
    for observation in data["observations"]:
        by_task[observation["task_id"]].append(observation)

    strategy_rows = {strategy: [] for strategy in STRATEGIES}
    for task_id, rows in by_task.items():
        category = rows[0]["category"]
        for strategy in STRATEGIES:
            selected = choose(rows, strategy, min_quality)
            if selected is None:
                strategy_rows[strategy].append({
                    "task_id": task_id,
                    "category": category,
                    "status": "no_eligible_model",
                })
                continue
            result = selected["result"]
            strategy_rows[strategy].append({
                "task_id": task_id,
                "category": category,
                "status": "success",
                "selected_model_id": selected["model"]["model_id"],
                "selected_model": selected["model"]["model_name"],
                "provider": selected["model"]["provider_name"],
                "actual_cost_usd": result["actual_cost_usd"],
                "quality_score": result["quality_score"],
                "latency_ms": result["latency_ms"],
            })

    summary = {}
    for strategy, rows in strategy_rows.items():
        successful = [r for r in rows if r["status"] == "success"]
        total_cost = sum((d(r["actual_cost_usd"]) for r in successful), Decimal("0"))
        avg_quality = (
            sum(r["quality_score"] for r in successful) / len(successful)
            if successful else None
        )
        avg_latency = (
            sum(r["latency_ms"] for r in successful) / len(successful)
            if successful else None
        )
        summary[strategy] = {
            "tasks": len(rows),
            "successful_tasks": len(successful),
            "no_eligible_model": len(rows) - len(successful),
            "total_actual_cost_usd": str(total_cost.quantize(Decimal("0.000001"))),
            "average_quality": avg_quality,
            "average_latency_ms": avg_latency,
            "details": rows,
        }

    baseline_cost = d(summary["baseline"]["total_actual_cost_usd"])
    for strategy in STRATEGIES:
        optimized_cost = d(summary[strategy]["total_actual_cost_usd"])
        savings = Decimal("0") if baseline_cost <= 0 else (baseline_cost - optimized_cost) / baseline_cost * 100
        summary[strategy]["savings_vs_baseline_percent"] = float(savings.quantize(Decimal("0.01")))

    output = {
        "schema_version": 1,
        "source": str(args.input),
        "min_quality": min_quality,
        "summary": summary,
        "interpretation": (
            "Results are retrospective replay estimates. The benchmark sends one independent "
            "request to each model, then evaluates what each routing strategy would have selected. "
            "No extra provider calls are made during analysis."
        ),
    }

    output_path = args.output or args.input.with_name("analysis_results.json")
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved analysis to {output_path}")
    for strategy in STRATEGIES:
        row = summary[strategy]
        print(
            f"{strategy}: cost=${row['total_actual_cost_usd']}, "
            f"quality={row['average_quality']}, latency={row['average_latency_ms']}ms, "
            f"savings_vs_baseline={row['savings_vs_baseline_percent']}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
