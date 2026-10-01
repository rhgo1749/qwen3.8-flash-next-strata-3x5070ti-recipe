#!/usr/bin/env python3
"""Phase-2D retry-aware completion A/B.

Each logical request keeps the same session ID across attempts. A benchmark
HTTP 429 admission defer is retried immediately after the bounded wait has
already elapsed. Metrics are measured from the logical request's original
submission until its eventual successful completion.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from pathlib import Path

import phase2d_admission_ab as A
import phase2d_overload_baseline as B


def nearest_rank(values: list[float], p: float) -> float | None:
    if not values:
        return None
    vals = sorted(values)
    return vals[max(0, math.ceil(p * len(vals)) - 1)]


def scalar_stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None,
                "p50": None, "p95": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "p50": nearest_rank(values, 0.50),
        "p95": nearest_rank(values, 0.95),
    }


def summarize(records: list[dict]) -> dict:
    by_count: dict[int, list[dict]] = {}
    for row in records:
        by_count.setdefault(int(row["request_count"]), []).append(row)

    out = {}
    for m, rows in sorted(by_count.items()):
        total_e2e = [float(r["logical_e2e_ms"]) for r in rows]
        total_ttft = [float(r["logical_ttft_ms"]) for r in rows if r["logical_ttft_ms"] is not None]
        retries = [float(r["retry_count"]) for r in rows]
        attempts = [float(r["attempt_count"]) for r in rows]
        deferred_wait = [float(r["deferred_wait_total_ms"]) for r in rows]
        completion_tokens = [int((r.get("final_usage") or {}).get("completion_tokens") or 0) for r in rows]

        run_ids = sorted({r["run_id"] for r in rows})
        run_goodput = []
        run_amplification = []
        run_wall = []
        for run_id in run_ids:
            rr = [r for r in rows if r["run_id"] == run_id]
            wall_s = (max(int(r["logical_end_ns"]) for r in rr) -
                      min(int(r["logical_start_ns"]) for r in rr)) / 1e9
            run_wall.append(wall_s)
            tokens = sum(int((r.get("final_usage") or {}).get("completion_tokens") or 0) for r in rr)
            run_goodput.append(tokens / wall_s if wall_s > 0 else 0.0)
            run_amplification.append(sum(int(r["attempt_count"]) for r in rr) / len(rr))

        out[str(m)] = {
            "logical_requests": len(rows),
            "all_completed": all(r["final_status"] == 200 for r in rows),
            "logical_e2e_ms": scalar_stats(total_e2e),
            "logical_ttft_ms": scalar_stats(total_ttft),
            "retry_count": scalar_stats(retries),
            "attempt_count": scalar_stats(attempts),
            "deferred_wait_total_ms": scalar_stats(deferred_wait),
            "requests_with_retry": sum(1 for r in rows if int(r["retry_count"]) > 0),
            "retry_request_fraction": sum(1 for r in rows if int(r["retry_count"]) > 0) / len(rows),
            "attempt_amplification_per_run": scalar_stats(run_amplification),
            "successful_goodput_tok_s": scalar_stats(run_goodput),
            "run_wall_s": scalar_stats(run_wall),
            "completion_tokens": sum(completion_tokens),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18187)
    ap.add_argument("--scheduler-policy", required=True)
    ap.add_argument("--admission-policy", required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--counts", default="6:4,9:3")
    ap.add_argument("--facts", type=int, default=80)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--max-attempts", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=180.0)
    args = ap.parse_args()

    counts = B.parse_counts(args.counts)
    status = B.wait_idle(args.host, args.port)
    if status.get("scheduler_policy") != args.scheduler_policy:
        raise SystemExit(f"scheduler mismatch: {status.get('scheduler_policy')}")
    if status.get("admission_policy") != args.admission_policy:
        raise SystemExit(f"admission mismatch: {status.get('admission_policy')}")
    lanes = len(status.get("lanes") or [])
    common = B.common_messages(args.facts)

    # Equalize retained state before measurement.
    for i in range(lanes):
        rid = f"phase2d-retry-warmup-{int(time.time())}-{i}"
        got = A.request(
            host=args.host, port=args.port, session_id=rid,
            payload_messages=B.messages(common, 10000 + i),
            max_tokens=16, run_id=rid, request_id=rid,
            barrier=None, timeout=args.timeout,
        )
        if got["status"] != 200:
            raise RuntimeError(f"warmup not accepted: {got}")
    B.wait_idle(args.host, args.port)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    all_records: list[dict] = []

    for m, reps in counts.items():
        for rep in range(1, reps + 1):
            B.wait_idle(args.host, args.port)
            run_id = f"retry-{args.admission_policy}-m{m}-r{rep}-{stamp}"
            barrier = threading.Barrier(m)
            results: list[dict | None] = [None] * m
            errors: list[str | None] = [None] * m

            def worker(i: int) -> None:
                logical_id = f"{run_id}-q{i}"
                session_id = f"{run_id}-s{i}"
                logical_start_ns = None
                attempts = []
                try:
                    for attempt_index in range(args.max_attempts):
                        attempt_request_id = f"{logical_id}-a{attempt_index}"
                        got = A.request(
                            host=args.host,
                            port=args.port,
                            session_id=session_id,
                            payload_messages=B.messages(common, i),
                            max_tokens=args.max_tokens,
                            run_id=run_id,
                            request_id=attempt_request_id,
                            barrier=barrier if attempt_index == 0 else None,
                            timeout=args.timeout,
                        )
                        if logical_start_ns is None:
                            logical_start_ns = got["start_ns"]
                        attempts.append({
                            "attempt_index": attempt_index,
                            **got,
                        })
                        if got["status"] == 200:
                            logical_end_ns = got["end_ns"]
                            logical_ttft_ms = (
                                ((got["start_ns"] - logical_start_ns) / 1e6) + got["ttft_ms"]
                                if got["ttft_ms"] is not None else None
                            )
                            results[i] = {
                                "logical_id": logical_id,
                                "session_id": session_id,
                                "logical_start_ns": logical_start_ns,
                                "logical_end_ns": logical_end_ns,
                                "logical_e2e_ms": (logical_end_ns - logical_start_ns) / 1e6,
                                "logical_ttft_ms": logical_ttft_ms,
                                "attempt_count": len(attempts),
                                "retry_count": len(attempts) - 1,
                                "deferred_wait_total_ms": sum(
                                    float(a.get("queue_wait_ms_header") or 0.0)
                                    for a in attempts if a["status"] == 429
                                ),
                                "final_status": 200,
                                "final_lane_index": got["lane_index"],
                                "final_usage": got["usage"],
                                "final_timings": got["timings"],
                                "attempts": attempts,
                            }
                            return
                    errors[i] = f"max attempts exceeded for {logical_id}"
                except Exception as exc:
                    errors[i] = repr(exc)

            threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(m)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            if any(errors):
                raise RuntimeError(f"{run_id}: {errors}")

            B.wait_idle(args.host, args.port)
            rr = [x for x in results if x is not None]
            for row in rr:
                row["kind"] = "logical_request"
                row["run_id"] = run_id
                row["rep"] = rep
                row["request_count"] = m
                all_records.append(row)

            # Require one trace record per attempt before advancing.
            wanted = {
                attempt["request_id"]
                for row in rr
                for attempt in row["attempts"]
            }
            deadline = time.monotonic() + 5.0
            trace = {}
            while time.monotonic() < deadline:
                trace = A.read_trace(args.trace, wanted)
                if len(trace) == len(wanted):
                    break
                time.sleep(0.1)
            if len(trace) != len(wanted):
                raise RuntimeError(f"{run_id}: trace has {len(trace)}/{len(wanted)} attempts")

            with args.output.open("w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "kind": "metadata",
                    "scheduler_policy": args.scheduler_policy,
                    "admission_policy": args.admission_policy,
                    "admission_wait_budget_ms": status.get("admission_wait_budget_ms"),
                    "counts": counts,
                    "facts": args.facts,
                    "max_tokens": args.max_tokens,
                    "max_attempts": args.max_attempts,
                    "retry_strategy": "immediate_after_defer_response",
                }, sort_keys=True) + "\n")
                for row in all_records:
                    f.write(json.dumps(row, sort_keys=True) + "\n")

            summary = {
                "kind": "phase2d_retry_completion_ab",
                "scheduler_policy": args.scheduler_policy,
                "admission_policy": args.admission_policy,
                "admission_wait_budget_ms": status.get("admission_wait_budget_ms"),
                "retry_strategy": "immediate_after_defer_response",
                "by_request_count": summarize(all_records),
            }
            args.summary.write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(
                f"{run_id}: completed={len(rr)}/{m} "
                f"attempts={sum(r['attempt_count'] for r in rr)} "
                f"retried={sum(1 for r in rr if r['retry_count'] > 0)}",
                flush=True,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
