#!/usr/bin/env python3
"""Phase-2 online policy A/B client for the Strata multi-lane supervisor.

The workload deliberately separates *session-start placement* from continuation
affinity:

1. Start several new sessions sequentially. Every session shares a long exact
   leading prefix but has a unique final message.
2. Submit one continuation for every session simultaneously.

A cache-only new-session policy may concentrate affinities on one cache-rich
lane. A session-start balancing policy may give up some first-turn prefix reuse
to reduce the second-wave queue. The server policy itself is selected when the
supervisor is launched; this client only labels and measures one arm.

The output is JSONL and is suitable for retaining beside the supervisor's
trace-schema-2 JSONL.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import statistics
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any


def common_messages(facts: int) -> list[dict[str, str]]:
    context = " ".join(
        f"Shared fact {i}: shard {i % 13} owns key {i * 17 % 101} at epoch {i % 19}."
        for i in range(1, facts + 1)
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a deterministic serving benchmark. Use the supplied shared "
                "context and answer the final task directly."
            ),
        },
        {
            "role": "user",
            "content": "Shared context for all independent sessions:\n" + context,
        },
    ]


def first_messages(common: list[dict[str, str]], index: int) -> list[dict[str, str]]:
    return [
        *common,
        {
            "role": "user",
            "content": (
                f"Session {index}: identify shard {index % 13} and give one short "
                "scheduling observation. Keep the answer concise."
            ),
        },
    ]


def continuation_messages(common: list[dict[str, str]], index: int) -> list[dict[str, str]]:
    return [
        *first_messages(common, index),
        {
            "role": "user",
            "content": (
                f"Session {index} continuation: now give one different short observation "
                "about queueing while preserving the previous context."
            ),
        },
    ]


def meaningful_delta(obj: dict[str, Any]) -> bool:
    for choice in obj.get("choices") or []:
        delta = choice.get("delta") or {}
        for key in ("content", "reasoning_content", "tool_calls"):
            if delta.get(key) not in (None, "", [], {}):
                return True
    return False


def stream_request(
    *,
    host: str,
    port: int,
    session_id: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    run_id: str,
    request_id: str,
    phase: str,
    start_barrier: threading.Barrier | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    body = json.dumps(
        {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
            "seed": 1234,
            "stream": True,
        },
        separators=(",", ":"),
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "X-Strata-Session-Id": session_id,
        "X-Strata-Benchmark-Run-Id": run_id,
        "X-Strata-Benchmark-Request-Id": request_id,
        "X-Strata-Benchmark-Workload": "phase2-online-policy-ab",
        "X-Strata-Benchmark-Cache-State": phase,
        "X-Strata-Benchmark-Interference-Arm": phase,
    }
    if start_barrier is not None:
        start_barrier.wait()

    start_ns = time.monotonic_ns()
    first_token_ns = None
    final_obj: dict[str, Any] | None = None
    finish_reason = None
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("POST", "/v1/chat/completions", body=body, headers=headers)
        resp = conn.getresponse()
        response_headers = {k.lower(): v for k, v in resp.getheaders()}
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
            if first_token_ns is None and meaningful_delta(obj):
                first_token_ns = time.monotonic_ns()
            if obj.get("usage") or obj.get("timings"):
                final_obj = obj
            for choice in obj.get("choices") or []:
                if choice.get("finish_reason") is not None:
                    finish_reason = choice.get("finish_reason")
        end_ns = time.monotonic_ns()
        usage = (final_obj or {}).get("usage") or {}
        timings = (final_obj or {}).get("timings") or {}
        return {
            "request_id": request_id,
            "session_id": session_id,
            "phase": phase,
            "http_status": resp.status,
            "lane_index": int(response_headers["x-strata-lane-index"])
            if response_headers.get("x-strata-lane-index") is not None else None,
            "admission_rank": int(response_headers["x-strata-admission-rank"])
            if response_headers.get("x-strata-admission-rank") is not None else None,
            "queue_wait_ms": float(response_headers["x-strata-queue-wait-ms"])
            if response_headers.get("x-strata-queue-wait-ms") is not None else None,
            "client_e2e_ms": (end_ns - start_ns) / 1e6,
            "client_token_ttft_ms": (first_token_ns - start_ns) / 1e6 if first_token_ns else None,
            "finish_reason": finish_reason,
            "usage": usage,
            "timings": timings,
        }
    finally:
        conn.close()


def json_get(host: str, port: int, path: str, timeout: float = 5.0) -> dict[str, Any]:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            raise RuntimeError(f"GET {path}: HTTP {resp.status}: {raw[:300]!r}")
        return json.loads(raw)
    finally:
        conn.close()


def wait_idle(host: str, port: int, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = json_get(host, port, "/__multigpu/status")
        queue = last.get("queue") or {}
        lanes = last.get("lanes") or []
        if (
            lanes
            and all(lane.get("alive") and not lane.get("busy") for lane in lanes)
            and int(queue.get("new_session_waiters") or 0) == 0
            and int(queue.get("affinity_waiters") or 0) == 0
        ):
            return last
        time.sleep(0.1)
    raise RuntimeError(f"server did not become idle: {last}")


def nearest_rank(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return ordered[rank - 1]


def stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18087)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--sessions", type=int, default=6)
    ap.add_argument("--facts", type=int, default=300)
    ap.add_argument("--turn1-tokens", type=int, default=32)
    ap.add_argument("--turn2-tokens", type=int, default=128)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    status = wait_idle(args.host, args.port)
    server_policy = status.get("scheduler_policy")
    if server_policy != args.policy:
        raise SystemExit(
            f"server policy mismatch: expected {args.policy!r}, got {server_policy!r}"
        )

    common = common_messages(args.facts)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"phase2-online-{args.policy}-{stamp}"
    sessions = [f"{run_id}-s{i}" for i in range(args.sessions)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = [{
        "kind": "metadata",
        "run_id": run_id,
        "policy": args.policy,
        "sessions": args.sessions,
        "facts": args.facts,
        "turn1_tokens": args.turn1_tokens,
        "turn2_tokens": args.turn2_tokens,
        "initial_status": status,
        "workload": (
            "sequential new-session starts sharing an exact leading prefix, followed by "
            "one synchronized continuation per session"
        ),
    }]

    first_rows = []
    for i, session_id in enumerate(sessions):
        row = stream_request(
            host=args.host,
            port=args.port,
            session_id=session_id,
            messages=first_messages(common, i),
            max_tokens=args.turn1_tokens,
            run_id=run_id,
            request_id=f"{run_id}-start-{i}",
            phase="session_start",
        )
        first_rows.append(row)
        records.append({"kind": "request", **row})
        wait_idle(args.host, args.port)
        print(
            f"start session={i} lane={row['lane_index']} "
            f"queue={row['queue_wait_ms']:.1f}ms "
            f"ttft={row['client_token_ttft_ms']:.1f}ms "
            f"e2e={row['client_e2e_ms']:.1f}ms",
            flush=True,
        )

    assignments = {
        sessions[i]: first_rows[i]["lane_index"]
        for i in range(args.sessions)
    }

    barrier = threading.Barrier(args.sessions + 1)
    second_rows: list[dict[str, Any] | None] = [None] * args.sessions
    errors: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        try:
            second_rows[i] = stream_request(
                host=args.host,
                port=args.port,
                session_id=sessions[i],
                messages=continuation_messages(common, i),
                max_tokens=args.turn2_tokens,
                run_id=run_id,
                request_id=f"{run_id}-continue-{i}",
                phase="continuation_wave",
                start_barrier=barrier,
            )
        except Exception as e:
            with lock:
                errors.append(f"{i}:{type(e).__name__}:{e}")

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(args.sessions)]
    for thread in threads:
        thread.start()
    common_start_ns = time.monotonic_ns()
    barrier.wait()
    for thread in threads:
        thread.join()
    common_end_ns = time.monotonic_ns()

    if errors:
        raise RuntimeError(f"continuation wave failed: {errors}")

    retained_second = [row for row in second_rows if row is not None]
    for row in retained_second:
        records.append({"kind": "request", **row})

    affinity_preserved = all(
        retained_second[i]["lane_index"] == first_rows[i]["lane_index"]
        for i in range(args.sessions)
    )
    queue_waits = [
        float(row["queue_wait_ms"])
        for row in retained_second
        if isinstance(row.get("queue_wait_ms"), (int, float))
    ]
    e2e = [
        float(row["client_e2e_ms"])
        for row in retained_second
        if isinstance(row.get("client_e2e_ms"), (int, float))
    ]
    ttft = [
        float(row["client_token_ttft_ms"])
        for row in retained_second
        if isinstance(row.get("client_token_ttft_ms"), (int, float))
    ]
    completion_tokens = sum(
        int((row.get("usage") or {}).get("completion_tokens") or 0)
        for row in retained_second
    )
    common_wall_s = (common_end_ns - common_start_ns) / 1e9
    final_status = wait_idle(args.host, args.port)

    summary = {
        "kind": "summary",
        "run_id": run_id,
        "policy": args.policy,
        "session_assignment_counts": dict(sorted(
            Counter(str(row["lane_index"]) for row in first_rows).items()
        )),
        "session_assignments": assignments,
        "affinity_preserved": affinity_preserved,
        "continuation_common_wall_s": common_wall_s,
        "continuation_completion_tokens": completion_tokens,
        "continuation_common_wall_tg": (
            completion_tokens / common_wall_s if common_wall_s > 0 else None
        ),
        "continuation_queue_wait_ms": {
            **stats(queue_waits),
            "p50": nearest_rank(queue_waits, 0.50),
            "p95": nearest_rank(queue_waits, 0.95),
        },
        "continuation_e2e_ms": {
            **stats(e2e),
            "p50": nearest_rank(e2e, 0.50),
            "p95": nearest_rank(e2e, 0.95),
        },
        "continuation_token_ttft_ms": {
            **stats(ttft),
            "p50": nearest_rank(ttft, 0.50),
            "p95": nearest_rank(ttft, 0.95),
        },
        "final_status": final_status,
        "pass": (
            len(first_rows) == args.sessions
            and len(retained_second) == args.sessions
            and affinity_preserved
            and all(row["http_status"] == 200 for row in first_rows + retained_second)
        ),
    }
    records.append(summary)

    with args.output.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
