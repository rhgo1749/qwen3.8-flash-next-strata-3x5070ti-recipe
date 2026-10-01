#!/usr/bin/env python3
"""Phase-2D bounded-admission live A/B client.

Runs synchronized fresh-session bursts against one supervisor admission arm.
HTTP 429 is an expected benchmark outcome for the bounded challenger and is
retained beside successful lane leases.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import statistics
import threading
import time
from pathlib import Path
from typing import Any

import phase2d_overload_baseline as B


def request(
    *,
    host: str,
    port: int,
    session_id: str,
    payload_messages: list[dict[str, str]],
    max_tokens: int,
    run_id: str,
    request_id: str,
    barrier: threading.Barrier | None,
    timeout: float,
) -> dict[str, Any]:
    body = json.dumps({
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": 1234,
        "stream": True,
    }, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "X-Strata-Session-Id": session_id,
        "X-Strata-Benchmark-Run-Id": run_id,
        "X-Strata-Benchmark-Request-Id": request_id,
        "X-Strata-Benchmark-Workload": "phase2d-admission-ab",
        "X-Strata-Benchmark-Cache-State": "warm-shared-prefix",
        "X-Strata-Benchmark-Interference-Arm": run_id.split("-m", 1)[0],
    }
    if barrier:
        barrier.wait()

    start_ns = time.monotonic_ns()
    first_token_ns = None
    final_obj = None
    finish_reason = None
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("POST", "/v1/chat/completions", body=body, headers=headers)
        resp = conn.getresponse()
        response_headers = {k.lower(): v for k, v in resp.getheaders()}
        if resp.status == 429:
            raw = resp.read()
            end_ns = time.monotonic_ns()
            try:
                error_payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                error_payload = {"raw": raw[:500].decode(errors="replace")}
            return {
                "request_id": request_id,
                "status": 429,
                "start_ns": start_ns,
                "end_ns": end_ns,
                "client_e2e_ms": (end_ns - start_ns) / 1e6,
                "queue_wait_ms_header": float(response_headers["x-strata-queue-wait-ms"])
                if response_headers.get("x-strata-queue-wait-ms") else None,
                "admission_decision": response_headers.get("x-strata-admission-decision"),
                "lane_index": None,
                "admission_rank": None,
                "ttft_ms": None,
                "finish_reason": "admission_deferred",
                "usage": {},
                "timings": {},
                "error": error_payload,
            }
        if resp.status != 200:
            raw = resp.read()
            raise RuntimeError(f"HTTP {resp.status}: {raw[:500]!r}")

        while True:
            line = resp.readline()
            if not line:
                break
            line = line.strip()
            if not line or line.startswith(b":") or not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if first_token_ns is None and B.meaningful_delta(obj):
                first_token_ns = time.monotonic_ns()
            if obj.get("usage") or obj.get("timings"):
                final_obj = obj
            for choice in obj.get("choices") or []:
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]

        end_ns = time.monotonic_ns()
        usage = (final_obj or {}).get("usage") or {}
        timings = (final_obj or {}).get("timings") or {}
        return {
            "request_id": request_id,
            "status": 200,
            "start_ns": start_ns,
            "end_ns": end_ns,
            "client_e2e_ms": (end_ns - start_ns) / 1e6,
            "queue_wait_ms_header": float(response_headers["x-strata-queue-wait-ms"])
            if response_headers.get("x-strata-queue-wait-ms") else None,
            "admission_decision": response_headers.get("x-strata-admission-decision"),
            "lane_index": int(response_headers["x-strata-lane-index"])
            if response_headers.get("x-strata-lane-index") else None,
            "admission_rank": int(response_headers["x-strata-admission-rank"])
            if response_headers.get("x-strata-admission-rank") else None,
            "ttft_ms": (first_token_ns - start_ns) / 1e6 if first_token_ns else None,
            "finish_reason": finish_reason,
            "usage": usage,
            "timings": timings,
            "error": None,
        }
    finally:
        conn.close()


def read_trace(path: Path, wanted: set[str]) -> dict[str, dict]:
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("kind") in ("lane_lease", "admission_defer") and obj.get("request_id") in wanted:
                out[obj["request_id"]] = obj
    return out


def nearest_rank(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(p * len(values)) - 1)]


def stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def summarize(records: list[dict]) -> dict:
    by_count: dict[int, list[dict]] = {}
    for row in records:
        by_count.setdefault(int(row["request_count"]), []).append(row)

    out = {}
    for count, rows in sorted(by_count.items()):
        accepted = [r for r in rows if r["status"] == 200]
        deferred = [r for r in rows if r["status"] == 429]
        accepted_queue = [float(r["queue_wait_ms"]) for r in accepted]
        deferred_queue = [float(r["queue_wait_ms"]) for r in deferred]
        accepted_ttft = [float(r["ttft_ms"]) for r in accepted if r["ttft_ms"] is not None]
        accepted_e2e = [float(r["client_e2e_ms"]) for r in accepted]
        run_goodput = {}
        run_accepted = {}
        for r in rows:
            run_id = r["run_id"]
            run_goodput.setdefault(run_id, {
                "start": float(r["run_start_ns"]),
                "end": float(r["run_end_ns"]),
                "tokens": 0,
            })
            if r["status"] == 200:
                run_goodput[run_id]["tokens"] += int((r.get("usage") or {}).get("completion_tokens") or 0)
                run_accepted[run_id] = run_accepted.get(run_id, 0) + 1
        goodputs = []
        for v in run_goodput.values():
            wall = (v["end"] - v["start"]) / 1e9
            goodputs.append(v["tokens"] / wall if wall > 0 else 0.0)

        out[str(count)] = {
            "offered_requests": len(rows),
            "accepted": len(accepted),
            "deferred": len(deferred),
            "acceptance_fraction": len(accepted) / len(rows),
            "accepted_per_run": stats([float(v) for v in run_accepted.values()]),
            "successful_goodput_tok_s": stats(goodputs),
            "accepted_queue_wait_ms": {
                **stats(accepted_queue),
                "p50": nearest_rank(accepted_queue, 0.50),
                "p95": nearest_rank(accepted_queue, 0.95),
            },
            "deferred_wait_ms": {
                **stats(deferred_queue),
                "p50": nearest_rank(deferred_queue, 0.50),
                "p95": nearest_rank(deferred_queue, 0.95),
            },
            "accepted_token_ttft_ms": {
                **stats(accepted_ttft),
                "p50": nearest_rank(accepted_ttft, 0.50),
                "p95": nearest_rank(accepted_ttft, 0.95),
            },
            "accepted_e2e_ms": {
                **stats(accepted_e2e),
                "p50": nearest_rank(accepted_e2e, 0.50),
                "p95": nearest_rank(accepted_e2e, 0.95),
            },
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
    ap.add_argument("--counts", default="3:7,4:5,6:4,9:3")
    ap.add_argument("--facts", type=int, default=80)
    ap.add_argument("--max-tokens", type=int, default=256)
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

    # Equalize live state before measurement.
    for i in range(lanes):
        rid = f"phase2d-admission-warmup-{int(time.time())}-{i}"
        got = request(
            host=args.host, port=args.port, session_id=rid,
            payload_messages=B.messages(common, 10000 + i), max_tokens=16,
            run_id=rid, request_id=rid, barrier=None, timeout=args.timeout,
        )
        if got["status"] != 200:
            raise RuntimeError(f"warmup deferred unexpectedly: {got}")
    B.wait_idle(args.host, args.port)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    campaign = time.strftime("%Y%m%d-%H%M%S")
    records: list[dict] = []

    for m, reps in counts.items():
        for rep in range(1, reps + 1):
            B.wait_idle(args.host, args.port)
            run_id = f"{args.admission_policy}-m{m}-r{rep}-{campaign}"
            barrier = threading.Barrier(m)
            results: list[dict | None] = [None] * m
            errors: list[str | None] = [None] * m

            def worker(i: int) -> None:
                try:
                    results[i] = request(
                        host=args.host, port=args.port,
                        session_id=f"{run_id}-s{i}",
                        payload_messages=B.messages(common, i),
                        max_tokens=args.max_tokens,
                        run_id=run_id, request_id=f"{run_id}-q{i}",
                        barrier=barrier, timeout=args.timeout,
                    )
                except Exception as exc:
                    errors[i] = repr(exc)

            threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(m)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            if any(errors):
                raise RuntimeError(f"{run_id}: {errors}")

            rr = [r for r in results if r is not None]
            B.wait_idle(args.host, args.port)
            wanted = {r["request_id"] for r in rr}
            trace = {}
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                trace = read_trace(args.trace, wanted)
                if len(trace) == m:
                    break
                time.sleep(0.1)
            if len(trace) != m:
                raise RuntimeError(f"{run_id}: trace has {len(trace)}/{m}")

            run_start_ns = min(r["start_ns"] for r in rr)
            run_end_ns = max(r["end_ns"] for r in rr)
            accepted = 0
            deferred = 0
            for i, r in enumerate(rr):
                tr = trace[r["request_id"]]
                if r["status"] == 200:
                    accepted += 1
                elif r["status"] == 429:
                    deferred += 1
                record = {
                    "kind": "request",
                    "run_id": run_id,
                    "rep": rep,
                    "request_count": m,
                    "request_index": i,
                    "status": r["status"],
                    "admission_decision": r["admission_decision"],
                    "lane_index": r["lane_index"],
                    "admission_rank": r["admission_rank"],
                    "queue_wait_ms": tr["queue_wait_ms"],
                    "ttft_ms": r["ttft_ms"],
                    "client_e2e_ms": r["client_e2e_ms"],
                    "finish_reason": r["finish_reason"],
                    "usage": r["usage"],
                    "timings": r["timings"],
                    "trace_kind": tr["kind"],
                    "admission": (tr.get("scheduler") or {}).get("admission"),
                    "run_start_ns": run_start_ns,
                    "run_end_ns": run_end_ns,
                }
                records.append(record)

            with args.output.open("w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "kind": "metadata",
                    "scheduler_policy": args.scheduler_policy,
                    "admission_policy": args.admission_policy,
                    "admission_wait_budget_ms": status.get("admission_wait_budget_ms"),
                    "counts": counts,
                    "facts": args.facts,
                    "max_tokens": args.max_tokens,
                }, sort_keys=True) + "\n")
                for row in records:
                    f.write(json.dumps(row, sort_keys=True) + "\n")
            summary = {
                "kind": "phase2d_admission_ab",
                "scheduler_policy": args.scheduler_policy,
                "admission_policy": args.admission_policy,
                "admission_wait_budget_ms": status.get("admission_wait_budget_ms"),
                "by_request_count": summarize(records),
            }
            args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"{run_id}: accepted={accepted} deferred={deferred}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
