#!/usr/bin/env python3
"""Matched cross-lane interference probe for Strata multi-GPU serving.

Runs one stable target session on one lane while varying concurrent work on the
other lanes. The primary warm-reuse campaign interleaves solo / +1 / +2 arms,
captures token-level TTFT from SSE (ignoring keep-alives), engine timings, the
private lane /metrics history, and sampled hardware pressure.

Stdlib only; intended for the reference host and post-paper Phase-1 evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import statistics
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


ARM_ORDERS = [
    ("solo", "plus1", "plus2"),
    ("plus2", "plus1", "solo"),
    ("plus1", "solo", "plus2"),
    ("plus2", "solo", "plus1"),
    ("plus1", "plus2", "solo"),
    ("solo", "plus2", "plus1"),
]

SAMPLE_KEYS = (
    "gpu_util",
    "gpu_power",
    "gpu_pcie_rx_mb",
    "gpu_pcie_tx_mb",
    "cpu",
    "ram_used",
    "tok_s",
    "tok_s_mean",
    "prefill_tok_s_mean",
)


def deterministic_prompt() -> list[dict[str, str]]:
    facts = " ".join(
        f"Fact {i}: node {i % 11} sends batch {i * 7 % 97} after checkpoint {i % 17}."
        for i in range(1, 121)
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a deterministic systems-analysis benchmark. Reason carefully, "
                "avoid tables, and continue until the token limit if necessary."
            ),
        },
        {
            "role": "user",
            "content": (
                "Analyze the synthetic distributed-system trace below. Explain likely "
                "bottlenecks, dependencies, and two plausible failure cascades. "
                "Use the facts exactly as given and do not ask questions.\n\n" + facts
            ),
        },
    ]


def json_get(host: str, port: int, path: str, timeout: float = 3.0) -> dict[str, Any]:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            raise RuntimeError(f"GET {path} on {port} returned {resp.status}: {raw[:200]!r}")
        return json.loads(raw)
    finally:
        conn.close()


def repo_head(path: str) -> str | None:
    try:
        p = subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return p.stdout.strip() or None
    except Exception:
        return None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def meaningful_delta(obj: dict[str, Any]) -> bool:
    for choice in obj.get("choices") or []:
        delta = choice.get("delta") or {}
        for key in ("content", "reasoning_content", "tool_calls"):
            value = delta.get(key)
            if value not in (None, "", [], {}):
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
    arm: str,
    workload: str,
    cache_state: str,
    start_barrier: threading.Barrier | None = None,
    timeout: float = 180.0,
) -> dict[str, Any]:
    body_obj = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": 1234,
        "stream": True,
    }
    body = json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "X-Strata-Session-Id": session_id,
        "X-Strata-Benchmark-Run-Id": run_id,
        "X-Strata-Benchmark-Request-Id": request_id,
        "X-Strata-Benchmark-Workload": workload,
        "X-Strata-Benchmark-Cache-State": cache_state,
        "X-Strata-Benchmark-Interference-Arm": arm,
    }
    if start_barrier is not None:
        start_barrier.wait()
    start_ns = time.monotonic_ns()
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    first_token_ns = None
    final_obj: dict[str, Any] | None = None
    finish_reason = None
    chunks = 0
    try:
        conn.request("POST", "/v1/chat/completions", body=body, headers=headers)
        resp = conn.getresponse()
        response_headers = {k.lower(): v for k, v in resp.getheaders()}
        if resp.status != 200:
            raw = resp.read()
            raise RuntimeError(f"POST returned {resp.status}: {raw[:500]!r}")
        while True:
            line = resp.readline()
            if not line:
                break
            line = line.strip()
            if not line or line.startswith(b":"):
                continue
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            chunks += 1
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
            "session_id": session_id,
            "request_id": request_id,
            "http_status": resp.status,
            "lane_index": int(response_headers["x-strata-lane-index"])
            if response_headers.get("x-strata-lane-index") is not None else None,
            "admission_rank": int(response_headers["x-strata-admission-rank"])
            if response_headers.get("x-strata-admission-rank") is not None else None,
            "queue_wait_ms_header": float(response_headers["x-strata-queue-wait-ms"])
            if response_headers.get("x-strata-queue-wait-ms") is not None else None,
            "client_e2e_ms": (end_ns - start_ns) / 1e6,
            "client_token_ttft_ms": (first_token_ns - start_ns) / 1e6 if first_token_ns else None,
            "finish_reason": finish_reason,
            "chunks": chunks,
            "usage": usage,
            "timings": timings,
        }
    finally:
        conn.close()


def summarize_numbers(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_lane: dict[int, dict[str, list[float]]] = {}
    host_values: dict[str, list[float]] = {"mem_available_bytes": [], "memory_psi_avg10": []}
    for sample in samples:
        for lane_index, hw in (sample.get("lanes") or {}).items():
            lane_index = int(lane_index)
            dst = by_lane.setdefault(lane_index, {key: [] for key in SAMPLE_KEYS})
            for key in SAMPLE_KEYS:
                value = hw.get(key)
                if isinstance(value, (int, float)):
                    dst[key].append(float(value))
        for key in host_values:
            value = sample.get("host", {}).get(key)
            if isinstance(value, (int, float)):
                host_values[key].append(float(value))
    return {
        "lanes": {
            str(lane): {key: summarize_numbers(values) for key, values in metrics.items()}
            for lane, metrics in sorted(by_lane.items())
        },
        "host": {key: summarize_numbers(values) for key, values in host_values.items()},
        "samples": len(samples),
    }


def read_host_pressure() -> dict[str, float | None]:
    mem_available = None
    psi_avg10 = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                mem_available = float(line.split()[1]) * 1024.0
                break
    except OSError:
        pass
    try:
        for line in Path("/proc/pressure/memory").read_text().splitlines():
            if line.startswith("some "):
                for field in line.split()[1:]:
                    if field.startswith("avg10="):
                        psi_avg10 = float(field.split("=", 1)[1])
                        break
    except OSError:
        pass
    return {"mem_available_bytes": mem_available, "memory_psi_avg10": psi_avg10}


def hardware_sampler(
    *,
    host: str,
    base_port: int,
    lane_count: int,
    interval: float,
    stop: threading.Event,
    out: list[dict[str, Any]],
) -> None:
    while not stop.is_set():
        point: dict[str, Any] = {"mono_ns": time.monotonic_ns(), "lanes": {}, "host": read_host_pressure()}
        for lane in range(lane_count):
            try:
                metrics = json_get(host, base_port + lane, "/metrics", timeout=1.0)
                point["lanes"][str(lane)] = metrics.get("hardware") or {}
            except Exception as e:
                point["lanes"][str(lane)] = {"sample_error": type(e).__name__}
        out.append(point)
        stop.wait(interval)


def newest_request(host: str, port: int) -> dict[str, Any]:
    metrics = json_get(host, port, "/metrics", timeout=3.0)
    requests = metrics.get("requests") or []
    return requests[0] if requests else {}


def lane_width(host: str, port: int) -> int:
    metrics = json_get(host, port, "/metrics", timeout=3.0)
    value = (metrics.get("hardware") or {}).get("gpu_pcie_width")
    return int(value) if isinstance(value, (int, float)) else 0


def wait_public_idle(host: str, public_port: int, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        status = json_get(host, public_port, "/__multigpu/status", timeout=5.0)
        last = status
        queue = status.get("queue") or {}
        lanes = status.get("lanes") or []
        if (
            lanes
            and all(lane.get("alive") and not lane.get("busy") for lane in lanes)
            and int(queue.get("new_session_waiters") or 0) == 0
            and int(queue.get("affinity_waiters") or 0) == 0
        ):
            return status
        time.sleep(0.25)
    raise RuntimeError(f"public supervisor did not become idle within {timeout}s: {last}")


def warm_session(
    *,
    host: str,
    public_port: int,
    session_id: str,
    messages: list[dict[str, str]],
    run_id: str,
    request_id: str,
    warm_tokens: int,
) -> dict[str, Any]:
    return stream_request(
        host=host,
        port=public_port,
        session_id=session_id,
        messages=messages,
        max_tokens=warm_tokens,
        run_id=run_id,
        request_id=request_id,
        arm="warmup",
        workload="phase1-interference",
        cache_state="warmup",
    )


def run_arm(
    *,
    host: str,
    public_port: int,
    base_port: int,
    lane_count: int,
    messages: list[dict[str, str]],
    max_tokens: int,
    run_id: str,
    rep: int,
    arm: str,
    target_session: str,
    peer_sessions: list[str],
    target_lane: int,
    primary_peer: str,
    cache_state: str,
    sample_interval: float,
) -> dict[str, Any]:
    sessions = [target_session]
    if arm in ("plus1", "plus2"):
        sessions.append(primary_peer)
    if arm == "plus2":
        sessions.extend(x for x in peer_sessions if x != primary_peer)

    wait_public_idle(host, public_port)
    barrier = threading.Barrier(len(sessions) + 1)
    results: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    lock = threading.Lock()
    threads = []

    def worker(session_id: str) -> None:
        role = "target" if session_id == target_session else "peer"
        request_id = f"{run_id}-r{rep}-{arm}-{role}-{session_id[-4:]}"
        try:
            result = stream_request(
                host=host,
                port=public_port,
                session_id=session_id,
                messages=messages,
                max_tokens=max_tokens,
                run_id=f"{run_id}-r{rep}-{arm}",
                request_id=request_id,
                arm=arm,
                workload="phase1-interference-warm",
                cache_state=cache_state,
                start_barrier=barrier,
            )
            with lock:
                results[session_id] = result
        except Exception as e:
            with lock:
                errors[session_id] = f"{type(e).__name__}: {e}"

    for session_id in sessions:
        t = threading.Thread(target=worker, args=(session_id,), daemon=True)
        t.start()
        threads.append(t)

    samples: list[dict[str, Any]] = []
    stop = threading.Event()
    sampler = threading.Thread(
        target=hardware_sampler,
        kwargs={
            "host": host,
            "base_port": base_port,
            "lane_count": lane_count,
            "interval": sample_interval,
            "stop": stop,
            "out": samples,
        },
        daemon=True,
    )
    sampler.start()
    common_start_ns = time.monotonic_ns()
    barrier.wait()
    for t in threads:
        t.join()
    common_end_ns = time.monotonic_ns()
    stop.set()
    sampler.join(timeout=max(2.0, sample_interval * 3))

    if errors:
        raise RuntimeError(f"arm {arm} failed: {errors}")
    target = results[target_session]
    if target.get("lane_index") != target_lane:
        raise RuntimeError(
            f"target affinity drifted: expected lane {target_lane}, got {target.get('lane_index')}"
        )

    lane_requests = {}
    for session_id, result in results.items():
        lane = result.get("lane_index")
        if lane is not None:
            try:
                lane_requests[str(lane)] = newest_request(host, base_port + lane)
            except Exception as e:
                lane_requests[str(lane)] = {"metrics_error": f"{type(e).__name__}: {e}"}

    return {
        "kind": "rep",
        "rep": rep,
        "arm": arm,
        "active_sessions": sessions,
        "common_wall_ms": (common_end_ns - common_start_ns) / 1e6,
        "target": target,
        "peers": {sid: result for sid, result in results.items() if sid != target_session},
        "lane_requests": lane_requests,
        "resource_summary": summarize_samples(samples),
    }


def arm_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(row["arm"], []).append(row)

    result: dict[str, Any] = {}
    for arm, arm_rows in sorted(by_arm.items()):
        service = [
            float(r["target"]["timings"]["predicted_ms"])
            for r in arm_rows
            if isinstance((r["target"].get("timings") or {}).get("predicted_ms"), (int, float))
        ]
        tg = [
            float(r["target"]["timings"]["predicted_per_second"])
            for r in arm_rows
            if isinstance((r["target"].get("timings") or {}).get("predicted_per_second"), (int, float))
        ]
        ttft = [
            float(r["target"]["client_token_ttft_ms"])
            for r in arm_rows
            if isinstance(r["target"].get("client_token_ttft_ms"), (int, float))
        ]
        e2e = [
            float(r["target"]["client_e2e_ms"])
            for r in arm_rows
            if isinstance(r["target"].get("client_e2e_ms"), (int, float))
        ]
        hit = []
        reused = []
        for r in arm_rows:
            lane = str(r["target"].get("lane_index"))
            req = (r.get("lane_requests") or {}).get(lane) or {}
            if isinstance(req.get("hit_rate"), (int, float)):
                hit.append(float(req["hit_rate"]))
            if isinstance(req.get("reused"), (int, float)):
                reused.append(float(req["reused"]))
        result[arm] = {
            "target_decode_ms": summarize_numbers(service),
            "target_decode_tok_s": summarize_numbers(tg),
            "target_client_token_ttft_ms": summarize_numbers(ttft),
            "target_client_e2e_ms": summarize_numbers(e2e),
            "target_expert_hit_rate": summarize_numbers(hit),
            "target_reused_tokens": summarize_numbers(reused),
        }

    solo = result.get("solo", {})
    solo_ms = ((solo.get("target_decode_ms") or {}).get("mean"))
    solo_tg = ((solo.get("target_decode_tok_s") or {}).get("mean"))
    if isinstance(solo_ms, (int, float)) and solo_ms:
        for arm in ("plus1", "plus2"):
            mean = (((result.get(arm) or {}).get("target_decode_ms") or {}).get("mean"))
            if isinstance(mean, (int, float)):
                result[arm]["decode_ms_vs_solo_pct"] = (mean / solo_ms - 1.0) * 100.0
    if isinstance(solo_tg, (int, float)) and solo_tg:
        for arm in ("plus1", "plus2"):
            mean = (((result.get(arm) or {}).get("target_decode_tok_s") or {}).get("mean"))
            if isinstance(mean, (int, float)):
                result[arm]["decode_tg_vs_solo_pct"] = (mean / solo_tg - 1.0) * 100.0
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--public-port", type=int, default=18087)
    ap.add_argument("--base-port", type=int, default=19087)
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--warm-tokens", type=int, default=64)
    ap.add_argument("--sample-interval", type=float, default=0.5)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--prod-root", default="/home/gonus/projects/Strata-vision-production")
    ap.add_argument("--expected-target-lane", type=int, default=0)
    args = ap.parse_args()

    status = wait_public_idle(args.host, args.public_port)
    lanes = status.get("lanes") or []
    if len(lanes) < 3:
        raise SystemExit(f"need at least 3 ready lanes, got {len(lanes)}")
    if not all(lane.get("alive") for lane in lanes):
        raise SystemExit(f"not all lanes are healthy: {lanes}")

    messages = deterministic_prompt()
    prompt_text = json.dumps(messages, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    prompt_hash = sha256_text(prompt_text)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"phase1-warm-{stamp}"
    target_session = f"{run_id}-target"
    peer_sessions = [f"{run_id}-peer-a", f"{run_id}-peer-b"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    metadata = {
        "kind": "metadata",
        "experiment": "phase1-matched-cross-lane-interference",
        "cache_state": "warm_repeated_prefix",
        "run_id": run_id,
        "fork_commit": repo_head(args.prod_root),
        "prompt_hash": prompt_hash,
        "max_tokens": args.max_tokens,
        "warm_tokens": args.warm_tokens,
        "reps_per_arm": args.reps,
        "arm_order_contract": ARM_ORDERS,
        "public_port": args.public_port,
        "base_port": args.base_port,
        "status": status,
        "notes": (
            "Target request and target session remain fixed across arms. "
            "Hardware sampler polls every lane for every arm so instrumentation overhead is matched. "
            "Client TTFT is first meaningful SSE model delta, excluding keep-alive comments and role-only chunks."
        ),
    }
    records.append(metadata)

    warmups = []
    for index, session_id in enumerate([target_session, *peer_sessions]):
        warm = warm_session(
            host=args.host,
            public_port=args.public_port,
            session_id=session_id,
            messages=messages,
            run_id=run_id,
            request_id=f"{run_id}-warm-{index}",
            warm_tokens=args.warm_tokens,
        )
        warmups.append(warm)
        records.append({"kind": "warmup", "index": index, "result": warm})

    mapped = {x["session_id"]: x["lane_index"] for x in warmups}
    if len(set(mapped.values())) != 3:
        raise SystemExit(f"warmup sessions did not map to three distinct lanes: {mapped}")
    target_lane = mapped[target_session]
    if target_lane != args.expected_target_lane:
        raise SystemExit(
            f"target session mapped to lane {target_lane}, expected clean-start lane "
            f"{args.expected_target_lane}; restart/reset before retaining this run"
        )

    widths = {}
    for session_id, lane in mapped.items():
        widths[session_id] = lane_width(args.host, args.base_port + lane)
    peer_sessions_sorted = sorted(peer_sessions, key=lambda s: (-widths[s], mapped[s]))
    primary_peer = peer_sessions_sorted[0]
    records.append({
        "kind": "mapping",
        "sessions_to_lanes": mapped,
        "pcie_widths": widths,
        "target_session": target_session,
        "target_lane": target_lane,
        "plus1_primary_peer": primary_peer,
        "plus1_primary_peer_lane": mapped[primary_peer],
    })

    rep_rows = []
    for rep in range(1, args.reps + 1):
        order = ARM_ORDERS[(rep - 1) % len(ARM_ORDERS)]
        for arm in order:
            row = run_arm(
                host=args.host,
                public_port=args.public_port,
                base_port=args.base_port,
                lane_count=len(lanes),
                messages=messages,
                max_tokens=args.max_tokens,
                run_id=run_id,
                rep=rep,
                arm=arm,
                target_session=target_session,
                peer_sessions=peer_sessions,
                target_lane=target_lane,
                primary_peer=primary_peer,
                cache_state="warm_repeated_prefix",
                sample_interval=args.sample_interval,
            )
            rep_rows.append(row)
            records.append(row)
            t = row["target"]
            timings = t.get("timings") or {}
            print(
                f"rep={rep} arm={arm} lane={t.get('lane_index')} "
                f"queue={t.get('queue_wait_ms_header'):.3f}ms "
                f"ttft={t.get('client_token_ttft_ms'):.1f}ms "
                f"decode={timings.get('predicted_ms')}ms "
                f"tg={timings.get('predicted_per_second')} tok/s",
                flush=True,
            )

    summary = {
        "kind": "summary",
        "run_id": run_id,
        "target_lane": target_lane,
        "primary_peer_lane": mapped[primary_peer],
        "arms": arm_summary(rep_rows),
    }
    records.append(summary)

    with args.output.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
