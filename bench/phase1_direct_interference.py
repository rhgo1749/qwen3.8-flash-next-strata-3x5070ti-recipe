#!/usr/bin/env python3
"""Direct-lane matched interference probe for Strata Phase 1.

Bypasses the public scheduler so the target is physically fixed to one lane.
Only activity on the other lanes changes between solo / +1 / +2 arms.
Synthetic prompts are used; prompt text is not written to the result file.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import statistics
import threading
import time
from pathlib import Path
from typing import Any

import phase1_interference as common


ARM_ORDERS = common.ARM_ORDERS
LOCK_PATH = Path("/tmp/strata-phase1-interference.lock")


def acquire_run_lock():
    lock = LOCK_PATH.open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as e:
        lock.close()
        raise RuntimeError(f"another Phase-1 interference run holds {LOCK_PATH}") from e
    lock.seek(0)
    lock.truncate()
    lock.write(f"{common.os.getpid()}\n")
    lock.flush()
    return lock


def prompt_messages(context: str, nonce: str | None = None) -> list[dict[str, str]]:
    facts_n = 120 if context == "short" else 1500
    prefix = f"Run nonce {nonce}. " if nonce is not None else ""
    facts = " ".join(
        f"Fact {i}: node {i % 11} sends batch {i * 7 % 97} after checkpoint {i % 17}."
        for i in range(1, facts_n + 1)
    )
    return [
        {
            "role": "system",
            "content": prefix
            + "You are a deterministic systems-analysis benchmark. Reason carefully, "
            "avoid tables, and continue until the token limit if necessary.",
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


def direct_ready(host: str, ports: list[int]) -> bool:
    for port in ports:
        try:
            common.json_get(host, port, "/metrics", timeout=1.0)
        except Exception:
            return False
    return True


def touch_idle_proxy(host: str, idle_proxy_port: int, timeout: float = 300.0) -> dict[str, Any]:
    conn = common.http.client.HTTPConnection(host, idle_proxy_port, timeout=timeout)
    try:
        conn.request("POST", "/__idle_proxy/wake", body=b"", headers={"Content-Length": "0"})
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status != 200:
            raise RuntimeError(f"idle-proxy wake returned {resp.status}: {raw[:200]!r}")
        return json.loads(raw)
    finally:
        conn.close()


def idle_keepalive(host: str, idle_proxy_port: int, interval: float = 30.0) -> None:
    while True:
        try:
            touch_idle_proxy(host, idle_proxy_port, timeout=30.0)
        except Exception:
            pass
        time.sleep(interval)


def wake_backend(host: str, idle_proxy_port: int, ports: list[int]) -> None:
    # A backend may already be ready or may already be starting under the idle proxy.
    # In both cases direct lane readiness is the source of truth; a concurrent wake can
    # legitimately return 500 while another launcher owns the startup.
    if direct_ready(host, ports):
        return
    wake_error = None
    try:
        touch_idle_proxy(host, idle_proxy_port)
    except Exception as e:
        wake_error = f"{type(e).__name__}: {e}"
    deadline = time.monotonic() + 240.0
    while time.monotonic() < deadline:
        if direct_ready(host, ports):
            return
        time.sleep(1.0)
    suffix = f" (wake error: {wake_error})" if wake_error else ""
    raise RuntimeError(f"private lanes did not become ready after idle-proxy wake{suffix}")


def append_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush()


def wait_lanes_idle(host: str, ports: list[int], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        states = {}
        ok = True
        for lane, port in enumerate(ports):
            try:
                m = common.json_get(host, port, "/metrics", timeout=2.0)
                state = (m.get("live") or {}).get("state")
                states[lane] = state
                if state != "idle":
                    ok = False
            except Exception as e:
                states[lane] = type(e).__name__
                ok = False
        last = states
        if ok:
            return
        time.sleep(0.1)
    raise RuntimeError(f"lanes did not become idle: {last}")


def state_messages(state: str, context: str, run_tag: str) -> list[dict[str, str]]:
    if state == "warm":
        return prompt_messages(context)
    return prompt_messages(context, nonce=run_tag)


def peer_messages(profile: str, run_tag: str) -> list[dict[str, str]]:
    if profile == "warm-short":
        return prompt_messages("short")
    if profile == "cold-short":
        return prompt_messages("short", nonce=run_tag)
    if profile == "cold-long":
        return prompt_messages("long", nonce=run_tag)
    raise ValueError(profile)


def request_direct(
    *,
    host: str,
    port: int,
    lane: int,
    messages: list[dict[str, str]],
    max_tokens: int,
    run_id: str,
    request_id: str,
    arm: str,
    cache_state: str,
    barrier: threading.Barrier,
) -> dict[str, Any]:
    result = common.stream_request(
        host=host,
        port=port,
        session_id=f"phase1-direct-lane-{lane}",
        messages=messages,
        max_tokens=max_tokens,
        run_id=run_id,
        request_id=request_id,
        arm=arm,
        workload="phase1-direct-interference",
        cache_state=cache_state,
        start_barrier=barrier,
        timeout=300.0,
    )
    result["lane_index"] = lane
    result["direct_lane_port"] = port
    return result


def run_arm(
    *,
    host: str,
    ports: list[int],
    target_lane: int,
    peer_lanes: list[int],
    target_state: str,
    target_context: str,
    peer_profile: str,
    max_tokens: int,
    peer_max_tokens: int,
    rep: int,
    arm: str,
    run_id: str,
    sample_interval: float,
) -> dict[str, Any]:
    wait_lanes_idle(host, ports)
    active = [target_lane]
    if arm in ("plus1", "plus2"):
        active.append(peer_lanes[0])
    if arm == "plus2":
        active.append(peer_lanes[1])

    barrier = threading.Barrier(len(active) + 1)
    results: dict[int, dict[str, Any]] = {}
    errors: dict[int, str] = {}
    lock = threading.Lock()
    threads = []

    def worker(lane: int) -> None:
        is_target = lane == target_lane
        tag = f"{run_id}-r{rep}-{arm}-l{lane}"
        msgs = (
            state_messages(target_state, target_context, tag)
            if is_target
            else peer_messages(peer_profile, tag)
        )
        tokens = max_tokens if is_target else peer_max_tokens
        try:
            out = request_direct(
                host=host,
                port=ports[lane],
                lane=lane,
                messages=msgs,
                max_tokens=tokens,
                run_id=f"{run_id}-r{rep}-{arm}",
                request_id=tag,
                arm=arm,
                cache_state=target_state if is_target else peer_profile,
                barrier=barrier,
            )
            with lock:
                results[lane] = out
        except Exception as e:
            with lock:
                errors[lane] = f"{type(e).__name__}: {e}"

    for lane in active:
        t = threading.Thread(target=worker, args=(lane,), daemon=True)
        t.start()
        threads.append(t)

    samples: list[dict[str, Any]] = []
    stop = threading.Event()
    sampler = threading.Thread(
        target=common.hardware_sampler,
        kwargs={
            "host": host,
            "base_port": ports[0],
            "lane_count": len(ports),
            "interval": sample_interval,
            "stop": stop,
            "out": samples,
        },
        daemon=True,
    )
    sampler.start()
    start_ns = time.monotonic_ns()
    barrier.wait()
    for t in threads:
        t.join()
    end_ns = time.monotonic_ns()
    stop.set()
    sampler.join(timeout=max(2.0, sample_interval * 3))

    if errors:
        raise RuntimeError(f"{arm} failed: {errors}")

    lane_requests: dict[str, Any] = {}
    for lane in active:
        try:
            lane_requests[str(lane)] = common.newest_request(host, ports[lane])
        except Exception as e:
            lane_requests[str(lane)] = {"metrics_error": f"{type(e).__name__}: {e}"}

    target = results[target_lane]
    return {
        "kind": "rep",
        "rep": rep,
        "arm": arm,
        "active_lanes": active,
        "common_wall_ms": (end_ns - start_ns) / 1e6,
        "target": target,
        "peers": {str(k): v for k, v in results.items() if k != target_lane},
        "lane_requests": lane_requests,
        "resource_summary": common.summarize_samples(samples),
    }


def nums(rows: list[dict[str, Any]], getter) -> dict[str, Any]:
    values = []
    for row in rows:
        value = getter(row)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return common.summarize_numbers(values)


def summarize(rows: list[dict[str, Any]], target_lane: int) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(row["arm"], []).append(row)

    out: dict[str, Any] = {}
    for arm, arm_rows in sorted(by_arm.items()):
        lane_key = str(target_lane)
        out[arm] = {
            "target_decode_ms": nums(
                arm_rows, lambda r: (r["target"].get("timings") or {}).get("predicted_ms")
            ),
            "target_decode_tok_s": nums(
                arm_rows, lambda r: (r["target"].get("timings") or {}).get("predicted_per_second")
            ),
            "target_prompt_ms": nums(
                arm_rows, lambda r: (r["target"].get("timings") or {}).get("prompt_ms")
            ),
            "target_cache_n": nums(
                arm_rows, lambda r: (r["target"].get("timings") or {}).get("cache_n")
            ),
            "target_token_ttft_ms": nums(
                arm_rows, lambda r: r["target"].get("client_token_ttft_ms")
            ),
            "target_e2e_ms": nums(
                arm_rows, lambda r: r["target"].get("client_e2e_ms")
            ),
            "target_expert_hit_rate": nums(
                arm_rows, lambda r: (r.get("lane_requests", {}).get(lane_key) or {}).get("hit_rate")
            ),
            "target_pcie_rx_mb_s": nums(
                arm_rows,
                lambda r: (
                    r.get("resource_summary", {})
                    .get("lanes", {})
                    .get(lane_key, {})
                    .get("gpu_pcie_rx_mb", {})
                    .get("mean")
                ),
            ),
            "host_mem_available_bytes": nums(
                arm_rows,
                lambda r: (
                    r.get("resource_summary", {})
                    .get("host", {})
                    .get("mem_available_bytes", {})
                    .get("mean")
                ),
            ),
        }

    solo_ms = out.get("solo", {}).get("target_decode_ms", {}).get("mean")
    solo_tg = out.get("solo", {}).get("target_decode_tok_s", {}).get("mean")
    solo_prompt = out.get("solo", {}).get("target_prompt_ms", {}).get("mean")
    for arm in ("plus1", "plus2"):
        if isinstance(solo_ms, (int, float)) and solo_ms:
            mean = out.get(arm, {}).get("target_decode_ms", {}).get("mean")
            if isinstance(mean, (int, float)):
                out[arm]["decode_ms_vs_solo_pct"] = (mean / solo_ms - 1.0) * 100.0
        if isinstance(solo_tg, (int, float)) and solo_tg:
            mean = out.get(arm, {}).get("target_decode_tok_s", {}).get("mean")
            if isinstance(mean, (int, float)):
                out[arm]["decode_tg_vs_solo_pct"] = (mean / solo_tg - 1.0) * 100.0
        if isinstance(solo_prompt, (int, float)) and solo_prompt:
            mean = out.get(arm, {}).get("target_prompt_ms", {}).get("mean")
            if isinstance(mean, (int, float)):
                out[arm]["prompt_ms_vs_solo_pct"] = (mean / solo_prompt - 1.0) * 100.0
    return out


def warm_lane(host: str, port: int, lane: int, context: str, max_tokens: int, run_id: str) -> dict[str, Any]:
    barrier = threading.Barrier(2)
    t_result: dict[str, Any] = {}
    error: list[Exception] = []

    def go() -> None:
        try:
            t_result.update(
                request_direct(
                    host=host,
                    port=port,
                    lane=lane,
                    messages=prompt_messages(context),
                    max_tokens=max_tokens,
                    run_id=run_id,
                    request_id=f"{run_id}-warm-l{lane}",
                    arm="warmup",
                    cache_state=f"warm-{context}",
                    barrier=barrier,
                )
            )
        except Exception as e:
            error.append(e)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    barrier.wait()
    t.join()
    if error:
        raise error[0]
    return t_result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--idle-proxy-port", type=int, default=8087)
    ap.add_argument("--base-port", type=int, default=19087)
    ap.add_argument("--lanes", type=int, default=3)
    ap.add_argument("--target-lane", type=int, default=0)
    ap.add_argument("--peer-lanes", default="2,1")
    ap.add_argument("--target-state", choices=("warm", "cold"), default="warm")
    ap.add_argument("--target-context", choices=("short", "long"), default="short")
    ap.add_argument(
        "--peer-profile",
        choices=("warm-short", "cold-short", "cold-long"),
        default="warm-short",
    )
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--peer-max-tokens", type=int, default=256)
    ap.add_argument("--warm-tokens", type=int, default=32)
    ap.add_argument("--sample-interval", type=float, default=0.5)
    ap.add_argument("--prod-root", default="/home/gonus/projects/Strata-vision-production")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    run_lock = acquire_run_lock()
    ports = [args.base_port + i for i in range(args.lanes)]
    peers = [int(x.strip()) for x in args.peer_lanes.split(",") if x.strip()]
    if len(peers) != 2 or args.target_lane in peers or len(set(peers)) != 2:
        raise SystemExit("--peer-lanes must contain two distinct non-target lane indices")

    wake_backend(args.host, args.idle_proxy_port, ports)
    threading.Thread(
        target=idle_keepalive,
        args=(args.host, args.idle_proxy_port),
        daemon=True,
    ).start()
    wait_lanes_idle(args.host, ports)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = (
        f"phase1-direct-{args.target_state}-{args.target_context}-"
        f"{args.peer_profile}-{stamp}"
    )
    prompt_fingerprint = common.sha256_text(
        json.dumps(prompt_messages(args.target_context), sort_keys=True, separators=(",", ":"))
    )
    metadata = {
        "kind": "metadata",
        "experiment": "phase1-direct-matched-cross-lane-interference",
        "run_id": run_id,
        "fork_commit": common.repo_head(args.prod_root),
        "target_lane": args.target_lane,
        "peer_lanes": peers,
        "target_state": args.target_state,
        "target_context": args.target_context,
        "peer_profile": args.peer_profile,
        "prompt_hash": prompt_fingerprint,
        "max_tokens": args.max_tokens,
        "peer_max_tokens": args.peer_max_tokens,
        "reps_per_arm": args.reps,
        "arm_order_contract": ARM_ORDERS,
        "ports": ports,
        "notes": (
            "Private lane ports are used intentionally to remove scheduler/queue effects. "
            "Only peer-lane activity changes between arms. Synthetic prompt content is not retained."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("", encoding="utf-8")
    append_record(args.output, metadata)

    warm_lanes = set()
    if args.target_state == "warm":
        warm_lanes.add(args.target_lane)
    if args.peer_profile == "warm-short":
        warm_lanes.update(peers)
    for lane in sorted(warm_lanes):
        context = args.target_context if lane == args.target_lane else "short"
        warm = warm_lane(args.host, ports[lane], lane, context, args.warm_tokens, run_id)
        append_record(args.output, {"kind": "warmup", "lane": lane, "result": warm})
        wait_lanes_idle(args.host, ports)

    rows: list[dict[str, Any]] = []
    for rep in range(1, args.reps + 1):
        order = ARM_ORDERS[(rep - 1) % len(ARM_ORDERS)]
        for arm in order:
            row = run_arm(
                host=args.host,
                ports=ports,
                target_lane=args.target_lane,
                peer_lanes=peers,
                target_state=args.target_state,
                target_context=args.target_context,
                peer_profile=args.peer_profile,
                max_tokens=args.max_tokens,
                peer_max_tokens=args.peer_max_tokens,
                rep=rep,
                arm=arm,
                run_id=run_id,
                sample_interval=args.sample_interval,
            )
            rows.append(row)
            append_record(args.output, row)
            timings = row["target"].get("timings") or {}
            print(
                f"rep={rep} arm={arm} target=l{args.target_lane} "
                f"ttft={row['target'].get('client_token_ttft_ms'):.1f}ms "
                f"prompt={timings.get('prompt_ms')}ms "
                f"decode={timings.get('predicted_ms')}ms "
                f"tg={timings.get('predicted_per_second')} tok/s "
                f"cache_n={timings.get('cache_n')}",
                flush=True,
            )

    summary = {
        "kind": "summary",
        "run_id": run_id,
        "target_lane": args.target_lane,
        "target_state": args.target_state,
        "target_context": args.target_context,
        "peer_profile": args.peer_profile,
        "arms": summarize(rows, args.target_lane),
    }
    append_record(args.output, summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"wrote {args.output}")
    run_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
