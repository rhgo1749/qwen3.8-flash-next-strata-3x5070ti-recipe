#!/usr/bin/env python3
"""Run repeated Phase-2 policy waves on one persistent Strata supervisor.

This wrapper deliberately does *not* restart the server between waves. Each
wave invokes phase2_online_policy_ab.py with fresh session IDs while preserving
all lane-local retained state and supervisor affinity history from earlier
waves. That makes long-lived session-start concentration visible instead of
resetting it away between measurements.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


def load_summary(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = next((row for row in rows if row.get("kind") == "summary"), None)
    if not isinstance(summary, dict):
        raise RuntimeError(f"{path} has no summary record")
    return summary


def numeric_stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def assignment_shape(summary: dict[str, Any]) -> dict[str, Any]:
    counts = {
        str(k): int(v)
        for k, v in (summary.get("session_assignment_counts") or {}).items()
    }
    values = list(counts.values())
    total = sum(values)
    maximum = max(values, default=0)
    minimum = min(values, default=0)
    return {
        "counts": dict(sorted(counts.items())),
        "total": total,
        "max_lane_share": (maximum / total) if total else None,
        "spread": (maximum - minimum) if values else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18087)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--waves", type=int, default=3)
    ap.add_argument("--sessions", type=int, default=6)
    ap.add_argument("--facts", type=int, default=300)
    ap.add_argument("--turn1-tokens", type=int, default=32)
    ap.add_argument("--turn2-tokens", type=int, default=128)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if args.waves < 1:
        ap.error("--waves must be >= 1")
    if args.sessions < 1:
        ap.error("--sessions must be >= 1")

    client = Path(__file__).with_name("phase2_online_policy_ab.py")
    if not client.is_file():
        raise SystemExit(f"missing single-wave client: {client}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "multiwave-summary.json"
    wave_paths = [args.output_dir / f"wave-{wave:02d}.jsonl" for wave in range(1, args.waves + 1)]
    existing = [path for path in [*wave_paths, summary_path] if path.exists()]
    if existing and not args.overwrite:
        raise SystemExit(
            "refusing to overwrite retained evidence: "
            + ", ".join(str(path) for path in existing)
        )
    if args.overwrite:
        for path in existing:
            path.unlink()

    wave_summaries: list[dict[str, Any]] = []
    for wave, output in enumerate(wave_paths, start=1):
        command = [
            sys.executable,
            str(client),
            "--host", args.host,
            "--port", str(args.port),
            "--policy", args.policy,
            "--sessions", str(args.sessions),
            "--facts", str(args.facts),
            "--turn1-tokens", str(args.turn1_tokens),
            "--turn2-tokens", str(args.turn2_tokens),
            "--output", str(output),
        ]
        print(f"=== persistent supervisor wave {wave}/{args.waves} ===", flush=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            raise SystemExit(
                f"wave {wave} failed with exit code {completed.returncode}; "
                f"retained earlier waves under {args.output_dir}"
            )
        summary = load_summary(output)
        summary["wave"] = wave
        summary["assignment_shape"] = assignment_shape(summary)
        wave_summaries.append(summary)

    tg = [float(row["continuation_common_wall_tg"]) for row in wave_summaries]
    queue_p95 = [float(row["continuation_queue_wait_ms"]["p95"]) for row in wave_summaries]
    ttft_p95 = [float(row["continuation_token_ttft_ms"]["p95"]) for row in wave_summaries]
    e2e_p95 = [float(row["continuation_e2e_ms"]["p95"]) for row in wave_summaries]
    max_lane_share = [
        float(row["assignment_shape"]["max_lane_share"])
        for row in wave_summaries
        if row["assignment_shape"]["max_lane_share"] is not None
    ]

    summary = {
        "kind": "multiwave_summary",
        "policy": args.policy,
        "waves_requested": args.waves,
        "waves_completed": len(wave_summaries),
        "sessions_per_wave": args.sessions,
        "facts": args.facts,
        "turn1_tokens": args.turn1_tokens,
        "turn2_tokens": args.turn2_tokens,
        "persistent_supervisor": True,
        "wave_files": [path.name for path in wave_paths],
        "waves": [
            {
                "wave": row["wave"],
                "run_id": row.get("run_id"),
                "pass": row.get("pass"),
                "assignment_shape": row["assignment_shape"],
                "continuation_common_wall_tg": row["continuation_common_wall_tg"],
                "continuation_queue_p95_ms": row["continuation_queue_wait_ms"]["p95"],
                "continuation_token_ttft_p95_ms": row["continuation_token_ttft_ms"]["p95"],
                "continuation_e2e_p95_ms": row["continuation_e2e_ms"]["p95"],
            }
            for row in wave_summaries
        ],
        "aggregate": {
            "continuation_common_wall_tg": numeric_stats(tg),
            "continuation_queue_p95_ms": numeric_stats(queue_p95),
            "continuation_token_ttft_p95_ms": numeric_stats(ttft_p95),
            "continuation_e2e_p95_ms": numeric_stats(e2e_p95),
            "max_lane_share": numeric_stats(max_lane_share),
        },
        "all_waves_pass": all(row.get("pass") is True for row in wave_summaries),
        "max_observed_lane_share": max(max_lane_share, default=None),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_waves_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
