#!/usr/bin/env python3
"""Aggregate the retained Phase-1 matched interference runs."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any


BASE = Path(__file__).parent / "raw" / "phase1-20261001"
SETS = {
    "public_warm_scheduler": [BASE / "strata-phase1-warm-client-telemetryfix.jsonl"],
    "direct_warm_short": [BASE / "phase1-direct-warm-short-warm-short-telemetryfix.jsonl"],
    "direct_cold_short": [
        BASE / "phase1-direct-cold-short-cold-short-v1.jsonl",
        BASE / "phase1-direct-cold-short-cold-short-v2.jsonl",
    ],
    "direct_cold_long": [BASE / "phase1-direct-cold-long-cold-long-v1.jsonl"],
    "direct_warm_target_cold_long_peers": [
        BASE / "phase1-direct-warm-short-cold-long-v1.jsonl"
    ],
}


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def retained_reps(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        records = load(path)
        if not any(r.get("kind") == "summary" for r in records):
            raise RuntimeError(f"incomplete retained run: {path}")
        rows.extend(r for r in records if r.get("kind") == "rep")
    return rows


def stats(values: list[float]) -> dict[str, float | int]:
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 3),
        "sd": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def summarize_experiment(paths: list[Path]) -> dict[str, Any]:
    rows = retained_reps(paths)
    by_arm = {arm: [r for r in rows if r.get("arm") == arm] for arm in ("solo", "plus1", "plus2")}
    if any(not rows for rows in by_arm.values()):
        raise RuntimeError(f"missing arm in {paths}")

    solo_decode = statistics.fmean(r["target"]["timings"]["predicted_ms"] for r in by_arm["solo"])
    solo_tg = statistics.fmean(r["target"]["timings"]["predicted_per_second"] for r in by_arm["solo"])
    solo_prompt = statistics.fmean(r["target"]["timings"]["prompt_ms"] for r in by_arm["solo"])

    arms: dict[str, Any] = {}
    for arm, arm_rows in by_arm.items():
        decode = [float(r["target"]["timings"]["predicted_ms"]) for r in arm_rows]
        tg = [float(r["target"]["timings"]["predicted_per_second"]) for r in arm_rows]
        prompt = [float(r["target"]["timings"]["prompt_ms"]) for r in arm_rows]
        ttft = [float(r["target"]["client_token_ttft_ms"]) for r in arm_rows]
        cache = [float(r["target"]["timings"].get("cache_n") or 0) for r in arm_rows]
        hit = []
        for r in arm_rows:
            lane = str(r["target"].get("lane_index", 0))
            req = (r.get("lane_requests") or {}).get(lane) or {}
            if isinstance(req.get("hit_rate"), (int, float)):
                hit.append(float(req["hit_rate"]))

        arms[arm] = {
            "decode_ms": stats(decode),
            "decode_vs_solo_pct": round((statistics.fmean(decode) / solo_decode - 1) * 100, 3),
            "decode_tok_s": stats(tg),
            "decode_tg_vs_solo_pct": round((statistics.fmean(tg) / solo_tg - 1) * 100, 3),
            "prompt_ms": stats(prompt),
            "prompt_vs_solo_pct": round((statistics.fmean(prompt) / solo_prompt - 1) * 100, 3),
            "client_token_ttft_ms": {
                **stats(ttft),
                "median": round(statistics.median(ttft), 3),
            },
            "cache_n": stats(cache),
            "expert_hit_rate": stats(hit) if hit else None,
        }
    return {"source_files": [str(p) for p in paths], "arms": arms}


def main() -> int:
    output = {
        "schema": 1,
        "date": "2026-10-01",
        "fork_commit": "e947183a6a819dfe567a6bfbb87e5a2528590a8e",
        "experiments": {name: summarize_experiment(paths) for name, paths in SETS.items()},
    }
    path = BASE / "phase1-summary-20261001.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
