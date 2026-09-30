#!/usr/bin/env python3
"""Summarize request-level Strata oversubscription CSVs without third-party packages.

The input schema is bench/oversubscription-0.1.30-template.csv.  Percentiles use
an empirical nearest-rank definition.  p99 is emitted only with at least 100
request samples for that request-count bucket; p95 requires at least 20.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


def number(row: dict[str, str], key: str) -> float | None:
    value = (row.get(key) or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def integer(row: dict[str, str], key: str) -> int | None:
    value = number(row, key)
    return int(value) if value is not None else None


def nearest_rank(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return ordered[rank - 1]


def mean_sd(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def jain(values: list[float]) -> float | None:
    if not values or any(v < 0 for v in values):
        return None
    denom = len(values) * sum(v * v for v in values)
    return (sum(values) ** 2 / denom) if denom > 0 else None


def summarize_bucket(rows: list[dict[str, str]]) -> dict:
    by_run: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_run[row["run_id"]].append(row)

    run_aggregate: list[float] = []
    run_util: list[float] = []
    run_fairness: list[float] = []
    max_overtakes: list[int] = []
    incomplete_runs: list[str] = []

    for run_id, rr in sorted(by_run.items()):
        wall = next((number(r, "common_wall_s") for r in rr if number(r, "common_wall_s") is not None), None)
        completion = [integer(r, "completion_tokens") for r in rr]
        completion = [x for x in completion if x is not None]
        if wall and completion:
            run_aggregate.append(sum(completion) / wall)
        else:
            incomplete_runs.append(run_id)

        utils = []
        for key in ("lane0_utilization", "lane1_utilization", "lane2_utilization"):
            value = next((number(r, key) for r in rr if number(r, key) is not None), None)
            if value is not None:
                utils.append(value)
        if utils:
            run_util.extend(utils)

        service_rates = []
        for r in rr:
            service_ms = number(r, "service_ms")
            tokens = integer(r, "completion_tokens")
            if service_ms and tokens is not None:
                service_rates.append(tokens / (service_ms / 1000.0))
        fairness = jain(service_rates)
        if fairness is not None:
            run_fairness.append(fairness)

        overtakes = []
        for r in rr:
            submit = integer(r, "submit_rank")
            admit = integer(r, "admission_rank")
            if submit is not None and admit is not None:
                overtakes.append(max(0, submit - admit))
        if overtakes:
            max_overtakes.append(max(overtakes))

    queue = [v for r in rows if (v := number(r, "queue_wait_ms")) is not None]
    e2e = [v for r in rows if (v := number(r, "e2e_ms")) is not None]
    ttft = [v for r in rows if (v := number(r, "ttft_ms")) is not None]

    def latency_summary(values: list[float]) -> dict:
        out = mean_sd(values)
        out["p50"] = nearest_rank(values, 0.50)
        out["p95"] = nearest_rank(values, 0.95) if len(values) >= 20 else None
        out["p99"] = nearest_rank(values, 0.99) if len(values) >= 100 else None
        return out

    return {
        "requests": len(rows),
        "runs": len(by_run),
        "queue_wait_exact": len(queue) == len(rows) and bool(rows),
        "queue_wait_ms": latency_summary(queue),
        "e2e_ms": latency_summary(e2e),
        "ttft_ms": latency_summary(ttft),
        "common_wall_aggregate_tg": mean_sd(run_aggregate),
        "lane_utilization": mean_sd(run_util),
        "jain_service_throughput": mean_sd(run_fairness),
        "max_fifo_overtake": max(max_overtakes) if max_overtakes else None,
        "incomplete_runs": incomplete_runs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    args = ap.parse_args()

    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    buckets: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        count = integer(row, "request_count")
        if count is None:
            continue
        buckets[count].append(row)

    result = {
        "percentile_definition": "empirical nearest-rank",
        "p95_min_samples": 20,
        "p99_min_samples": 100,
        "by_request_count": {str(k): summarize_bucket(v) for k, v in sorted(buckets.items())},
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
