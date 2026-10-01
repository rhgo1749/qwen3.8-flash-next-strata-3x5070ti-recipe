#!/usr/bin/env python3
"""Phase-2D overload baseline client for the Strata multi-lane supervisor.

Runs synchronized independent-session bursts at configurable M>N request counts.
The supervisor must be launched with --bench-trace-jsonl; this client joins its
request IDs against the server lease trace so queue/service timings remain
server-authoritative.
"""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import math
import statistics
import threading
import time
from pathlib import Path
from typing import Any


FIELDS = [
    "run_id","rep","request_count","lane_count","request_index","submit_rank",
    "admission_rank","lane_index","engine_version","fork_commit","upstream_commit",
    "binary_sha256","quant","prompt_id","prompt_sha256","warm_state",
    "submit_offset_ms","queue_wait_ms","ttft_ms","service_ms","e2e_ms",
    "prompt_tokens","completion_tokens","pp_tok_s","tg_tok_s","reused_tokens",
    "finish_reason","common_wall_s","aggregate_tg_tok_s","lane0_utilization",
    "lane1_utilization","lane2_utilization","jain_service_throughput",
    "max_fifo_overtake","notes",
]


def common_messages(facts: int) -> list[dict[str, str]]:
    context = " ".join(
        f"Fact {i}: shard {i % 11} maps key {i * 19 % 97} at epoch {i % 17}."
        for i in range(1, facts + 1)
    )
    return [
        {"role":"system","content":"You are a deterministic serving benchmark. Answer directly."},
        {"role":"user","content":"Shared benchmark context: " + context},
    ]


def messages(common: list[dict[str, str]], index: int) -> list[dict[str, str]]:
    return [
        *common,
        {"role":"user","content":f"Independent session {index}: give a concise scheduling observation."},
    ]


def meaningful_delta(obj: dict[str, Any]) -> bool:
    for choice in obj.get("choices") or []:
        delta = choice.get("delta") or {}
        if any(delta.get(k) not in (None, "", [], {}) for k in ("content","reasoning_content","tool_calls")):
            return True
    return False


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
        "Content-Type":"application/json",
        "Content-Length":str(len(body)),
        "X-Strata-Session-Id":session_id,
        "X-Strata-Benchmark-Run-Id":run_id,
        "X-Strata-Benchmark-Request-Id":request_id,
        "X-Strata-Benchmark-Workload":"phase2d-overload-baseline",
        "X-Strata-Benchmark-Cache-State":"warm-shared-prefix",
        "X-Strata-Benchmark-Interference-Arm":f"m{run_id.split('-m')[-1].split('-')[0]}",
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
        response_headers = {k.lower():v for k,v in resp.getheaders()}
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
                    finish_reason = choice["finish_reason"]
        end_ns = time.monotonic_ns()
        usage = (final_obj or {}).get("usage") or {}
        timings = (final_obj or {}).get("timings") or {}
        return {
            "request_id":request_id,
            "start_ns":start_ns,
            "end_ns":end_ns,
            "http_status":resp.status,
            "lane_index_header":int(response_headers["x-strata-lane-index"]) if response_headers.get("x-strata-lane-index") else None,
            "admission_rank_header":int(response_headers["x-strata-admission-rank"]) if response_headers.get("x-strata-admission-rank") else None,
            "queue_wait_ms_header":float(response_headers["x-strata-queue-wait-ms"]) if response_headers.get("x-strata-queue-wait-ms") else None,
            "ttft_ms":(first_token_ns-start_ns)/1e6 if first_token_ns else None,
            "e2e_ms":(end_ns-start_ns)/1e6,
            "usage":usage,
            "timings":timings,
            "finish_reason":finish_reason,
        }
    finally:
        conn.close()


def json_get(host: str, port: int, path: str, timeout: float = 5.0) -> dict:
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


def wait_idle(host: str, port: int, timeout: float = 180.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = json_get(host, port, "/__multigpu/status")
        q = last.get("queue") or {}
        lanes = last.get("lanes") or []
        if lanes and all(x.get("alive") and not x.get("busy") for x in lanes) and not int(q.get("new_session_waiters") or 0) and not int(q.get("affinity_waiters") or 0):
            return last
        time.sleep(0.1)
    raise RuntimeError(f"server did not become idle: {last}")


def parse_counts(text: str) -> dict[int,int]:
    out={}
    for part in text.split(","):
        m,r=part.split(":",1)
        out[int(m)]=int(r)
    return out


def read_trace(path: Path, wanted: set[str]) -> dict[str,dict]:
    out={}
    if not path.exists():
        return out
    for line in path.open(encoding="utf-8"):
        obj=json.loads(line)
        if obj.get("kind")=="lane_lease" and obj.get("request_id") in wanted:
            out[obj["request_id"]]=obj
    return out


def jain(values: list[float]) -> float | None:
    if not values:
        return None
    d=len(values)*sum(v*v for v in values)
    return (sum(values)**2/d) if d else None


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--host",default="127.0.0.1")
    ap.add_argument("--port",type=int,default=18087)
    ap.add_argument("--policy",required=True)
    ap.add_argument("--trace",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--counts",default="3:7,4:5,6:4,9:3")
    ap.add_argument("--facts",type=int,default=80)
    ap.add_argument("--max-tokens",type=int,default=256)
    ap.add_argument("--timeout",type=float,default=180.0)
    args=ap.parse_args()

    counts=parse_counts(args.counts)
    status=wait_idle(args.host,args.port)
    if status.get("scheduler_policy") != args.policy:
        raise SystemExit(f"server policy mismatch: expected {args.policy}, got {status.get('scheduler_policy')}")
    lanes=len(status.get("lanes") or [])
    if lanes < 1:
        raise SystemExit("no lanes")

    common=common_messages(args.facts)

    # Equal warmup: promoted balanced placement gives one fresh session to each lane.
    for i in range(lanes):
        rid=f"phase2d-warmup-{int(time.time())}-{i}"
        request(
            host=args.host,port=args.port,session_id=rid,
            payload_messages=messages(common,10000+i),max_tokens=16,
            run_id=rid,request_id=rid,barrier=None,timeout=args.timeout,
        )
    wait_idle(args.host,args.port)

    args.output.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    campaign_stamp=time.strftime("%Y%m%d-%H%M%S")

    for m,reps in counts.items():
        for rep in range(1,reps+1):
            wait_idle(args.host,args.port)
            run_id=f"phase2d-m{m}-r{rep}-{campaign_stamp}"
            barrier=threading.Barrier(m)
            results=[None]*m
            errors=[None]*m

            def worker(i:int) -> None:
                try:
                    results[i]=request(
                        host=args.host,port=args.port,
                        session_id=f"{run_id}-s{i}",
                        payload_messages=messages(common,i),
                        max_tokens=args.max_tokens,
                        run_id=run_id,request_id=f"{run_id}-q{i}",
                        barrier=barrier,timeout=args.timeout,
                    )
                except Exception as e:
                    errors[i]=repr(e)

            threads=[threading.Thread(target=worker,args=(i,),daemon=True) for i in range(m)]
            for t in threads:t.start()
            for t in threads:t.join()
            if any(errors):
                raise RuntimeError(f"{run_id} request failures: {errors}")
            rr=[x for x in results if x is not None]
            wait_idle(args.host,args.port)

            wanted={x["request_id"] for x in rr}
            trace={}
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                trace=read_trace(args.trace,wanted)
                if len(trace)==m:break
                time.sleep(0.1)
            if len(trace)!=m:
                raise RuntimeError(f"{run_id}: trace only has {len(trace)}/{m} requests")

            starts=sorted((x["start_ns"],i) for i,x in enumerate(rr))
            submit_rank={i:rank for rank,(_ns,i) in enumerate(starts)}
            wall_s=(max(x["end_ns"] for x in rr)-min(x["start_ns"] for x in rr))/1e9
            completion=[int((x["usage"] or {}).get("completion_tokens") or 0) for x in rr]
            agg=sum(completion)/wall_s
            lane_service=[0.0]*lanes
            rates=[]
            overtakes=[]
            for i,x in enumerate(rr):
                tr=trace[x["request_id"]]
                lane=int(tr["lane_index"])
                service=float(tr["service_ms"])
                lane_service[lane]+=service/1000.0
                if service>0 and completion[i]:
                    rates.append(completion[i]/(service/1000.0))
                overtakes.append(max(0,submit_rank[i]-int(tr["admission_rank"])))
            util=[v/wall_s for v in lane_service]
            fair=jain(rates)
            max_overtake=max(overtakes) if overtakes else 0

            for i,x in enumerate(rr):
                tr=trace[x["request_id"]]
                timings=x["timings"] or {}
                usage=x["usage"] or {}
                row={k:"" for k in FIELDS}
                row.update({
                    "run_id":run_id,"rep":rep,"request_count":m,"lane_count":lanes,
                    "request_index":i,"submit_rank":submit_rank[i],
                    "admission_rank":int(tr["admission_rank"]),"lane_index":int(tr["lane_index"]),
                    "fork_commit":tr.get("fork_commit") or "",
                    "prompt_id":f"phase2d-shared-facts-{args.facts}",
                    "warm_state":"balanced-prefix-warmup",
                    "submit_offset_ms":(x["start_ns"]-min(y["start_ns"] for y in rr))/1e6,
                    "queue_wait_ms":float(tr["queue_wait_ms"]),
                    "ttft_ms":x["ttft_ms"],"service_ms":float(tr["service_ms"]),"e2e_ms":x["e2e_ms"],
                    "prompt_tokens":usage.get("prompt_tokens") or "",
                    "completion_tokens":usage.get("completion_tokens") or "",
                    "pp_tok_s":timings.get("prompt_per_second") or "",
                    "tg_tok_s":timings.get("predicted_per_second") or "",
                    "reused_tokens":timings.get("cache_n") or 0,
                    "finish_reason":x["finish_reason"] or tr.get("completion_reason") or "",
                    "common_wall_s":wall_s,"aggregate_tg_tok_s":agg,
                    "jain_service_throughput":fair,"max_fifo_overtake":max_overtake,
                    "notes":"phase2d balanced-default overload baseline; exact queue/service from supervisor trace",
                })
                for li in range(min(3,lanes)):
                    row[f"lane{li}_utilization"]=util[li]
                rows.append(row)

            with args.output.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS)
                w.writeheader();w.writerows(rows)
            print(f"{run_id}: wall={wall_s:.3f}s agg={agg:.2f} tok/s max_overtake={max_overtake}",flush=True)

    return 0


if __name__=="__main__":
    raise SystemExit(main())
