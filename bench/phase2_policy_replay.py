#!/usr/bin/env python3
"""One-step Phase-2 placement replay over Strata trace-schema-2 decisions.

This is intentionally not a full counterfactual simulator. Each policy sees
the exact lane snapshot recorded at one real scheduler decision. Choosing a
different lane would alter later state, so this tool reports policy disagreement
and signal coverage only; it does not claim alternate-policy end-to-end gains.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

Policy = Callable[[dict[str, Any], list[dict[str, Any]]], int | None]


def eligible_idle_components(record: dict[str, Any]) -> list[dict[str, Any]]:
    scheduler = record.get("scheduler") or {}
    rows = []
    for lane in scheduler.get("lane_components") or []:
        if not lane.get("alive") or not lane.get("eligible") or lane.get("busy"):
            continue
        if int(lane.get("affinity_waiters") or 0) > 0:
            continue
        rows.append(lane)
    return rows


def current(record: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    lane = record.get("lane_index")
    return int(lane) if isinstance(lane, int) else None


def round_robin_first_free(record: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    if not candidates:
        return None
    return int(min(candidates, key=lambda lane: (
        int(lane.get("rotation_offset") or 0),
        int(lane["lane_index"]),
    ))["lane_index"])


def least_live_state(record: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    if not candidates:
        return None
    return int(min(candidates, key=lambda lane: (
        int(lane.get("live_request_bytes") or 0),
        int(lane.get("live_sequence") or 0),
        int(lane.get("rotation_offset") or 0),
        int(lane["lane_index"]),
    ))["lane_index"])


def cache_aware(record: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    if not candidates:
        return None
    return int(min(candidates, key=lambda lane: (
        -int(lane.get("estimated_reusable_prefix_bytes") or 0),
        int(lane.get("live_request_bytes") or 0),
        int(lane.get("live_sequence") or 0),
        int(lane.get("rotation_offset") or 0),
        int(lane["lane_index"]),
    ))["lane_index"])


def additive_proxy(record: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    """Minimize new-prefill bytes plus retained live-state bytes.

    live_request_bytes is a routing-history/state-size proxy, not active decode
    work. The report labels this limitation explicitly.
    """
    if not candidates:
        return None
    return int(min(candidates, key=lambda lane: (
        int(lane.get("estimated_new_prefill_bytes") or 0)
        + int(lane.get("live_request_bytes") or 0),
        int(lane.get("rotation_offset") or 0),
        int(lane["lane_index"]),
    ))["lane_index"])


def multiplicative_proxy(record: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    """Minimize new-prefill times one plus normalized retained-state proxy."""
    if not candidates:
        return None
    request_bytes = max(1, int((record.get("scheduler") or {}).get("request_bytes") or 1))

    def key(lane: dict[str, Any]) -> tuple[float, int, int]:
        new_prefill = float(lane.get("estimated_new_prefill_bytes") or 0)
        state = float(lane.get("live_request_bytes") or 0) / request_bytes
        return (
            new_prefill * (1.0 + state),
            int(lane.get("rotation_offset") or 0),
            int(lane["lane_index"]),
        )

    return int(min(candidates, key=key)["lane_index"])


def session_affinity_then_cache(record: dict[str, Any], candidates: list[dict[str, Any]]) -> int | None:
    scheduler = record.get("scheduler") or {}
    if scheduler.get("selected_reason") == "session_affinity":
        selected = current(record, candidates)
        if selected is not None and any(int(x["lane_index"]) == selected for x in candidates):
            return selected
    return cache_aware(record, candidates)


POLICIES: dict[str, Policy] = {
    "current_safe": current,
    "round_robin_first_free": round_robin_first_free,
    "least_live_state": least_live_state,
    "cache_aware": cache_aware,
    "additive_new_prefill_plus_state_proxy": additive_proxy,
    "multiplicative_new_prefill_x_state_proxy": multiplicative_proxy,
    "session_affinity_then_cache": session_affinity_then_cache,
}


def load_records(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    manifest = None
    decisions = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "benchmark_manifest":
                manifest = row
            elif row.get("kind") == "lane_lease" and row.get("trace_schema") == 2 and row.get("scheduler"):
                decisions.append(row)
    return manifest, decisions


def missing_signals(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    lane_fields = set()
    scheduler_fields = set()
    for row in records:
        scheduler = row.get("scheduler") or {}
        scheduler_fields.update(scheduler)
        for lane in scheduler.get("lane_components") or []:
            lane_fields.update(lane)

    requirements = [
        (
            "per_lane_affinity_session_count",
            "affinity_session_count" in lane_fields,
            "needed to replay session-start balancing rather than only continuation affinity",
        ),
        (
            "per_lane_active_decode_progress_or_remaining_work",
            any(x in lane_fields for x in ("active_decode_tokens", "active_remaining_tokens", "active_load")),
            "busy is observable, but wait-vs-recompute cost needs remaining-work or service-rate evidence",
        ),
        (
            "per_lane_queue_age_and_queued_work",
            any(x in lane_fields for x in ("queued_work", "queued_request_bytes", "queue_age_ms")),
            "global queued counts exist, but counterfactual lane-specific queue cost is not retained",
        ),
        (
            "instant_shared_pressure_at_decision",
            any(x in scheduler_fields for x in ("shared_pressure", "pcie_pressure", "host_pressure")),
            "Phase 1 resource telemetry is retained separately; Phase 2C needs time-aligned decision input",
        ),
        (
            "engine_truth_prefix_overlap",
            any(x in lane_fields for x in ("reusable_prefix_tokens", "reusable_prefix_blocks")),
            "current per-lane overlap is routing-history bytes and is explicitly approximate",
        ),
    ]
    return [
        {"signal": name, "available": "yes" if ok else "no", "why": why}
        for name, ok, why in requirements
    ]


def analyze(path: Path) -> dict[str, Any]:
    manifest, records = load_records(path)
    choices: dict[str, list[int | None]] = {name: [] for name in POLICIES}
    actual_reasons = Counter()
    candidate_counts = Counter()
    replayable = 0

    for row in records:
        candidates = eligible_idle_components(row)
        candidate_counts[str(len(candidates))] += 1
        actual_reasons[str((row.get("scheduler") or {}).get("selected_reason"))] += 1
        if not candidates:
            for name in POLICIES:
                choices[name].append(None)
            continue
        replayable += 1
        for name, policy in POLICIES.items():
            choices[name].append(policy(row, candidates))

    policy_summary = {}
    actual = choices["current_safe"]
    for name, selected in choices.items():
        comparable = [(a, b) for a, b in zip(actual, selected) if a is not None and b is not None]
        agree = sum(1 for a, b in comparable if a == b)
        policy_summary[name] = {
            "decisions": len(selected),
            "comparable": len(comparable),
            "agrees_with_current": agree,
            "disagrees_with_current": len(comparable) - agree,
            "agreement_rate": (agree / len(comparable)) if comparable else None,
            "lane_choice_counts": dict(sorted(Counter(str(x) for x in selected if x is not None).items())),
        }

    pairwise = {}
    names = list(POLICIES)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            pairs = [
                (a, b)
                for a, b in zip(choices[left], choices[right])
                if a is not None and b is not None
            ]
            disagree = sum(1 for a, b in pairs if a != b)
            pairwise[f"{left}__vs__{right}"] = {
                "comparable": len(pairs),
                "disagreements": disagree,
                "disagreement_rate": (disagree / len(pairs)) if pairs else None,
            }

    unique_vectors = Counter()
    for idx in range(len(records)):
        vector = tuple(choices[name][idx] for name in names)
        unique_vectors[str(vector)] += 1

    return {
        "input": str(path),
        "manifest_fork_commit": (manifest or {}).get("fork_commit"),
        "trace_schema": 2,
        "scope": (
            "one-step snapshot replay only; later state is not counterfactually simulated, "
            "so disagreement is evidence about policy distinctness, not performance"
        ),
        "records": len(records),
        "replayable_records": replayable,
        "selected_reason_counts": dict(sorted(actual_reasons.items())),
        "eligible_idle_candidate_counts": dict(sorted(candidate_counts.items())),
        "policy_summary": policy_summary,
        "pairwise": pairwise,
        "unique_choice_vectors": dict(unique_vectors.most_common()),
        "signal_gaps": missing_signals(records),
        "proxy_warning": (
            "additive and multiplicative policies use live_request_bytes as a retained-state/load proxy; "
            "trace schema 2 does not contain lane-local active remaining work"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    result = analyze(args.trace)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
