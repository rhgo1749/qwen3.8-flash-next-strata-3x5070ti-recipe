#!/usr/bin/env python3
"""Phase-2C shared-pressure go/no-go analysis.

Uses retained Phase-1 matched direct-lane interference data to answer two questions:

1. Does a simple observable concurrency signal generalize to held-out workload campaigns?
2. Within the aligned warm-short telemetry campaign, do sampled CPU/PCIe pressure
   signals improve held-out prediction beyond peer count alone?

The second question is intentionally evaluated only on the warm-short campaign because
its target and peer requests have comparable durations. Long-prefill peer campaigns keep
sampling after the target finishes, so their run-average telemetry is not a clean
target-overlap feature.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


def solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("singular design matrix")
        m[col], m[pivot] = m[pivot], m[col]
        d = m[col][col]
        m[col] = [x / d for x in m[col]]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col]
            if f:
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][-1] for i in range(n)]


def fit_ols(rows: list[dict], features: list[str], target: str) -> tuple[list[float], list[float], list[float]]:
    if not features:
        return [statistics.mean(r[target] for r in rows)], [], []

    means = [statistics.mean(r[f] for r in rows) for f in features]
    sds = []
    for f, mu in zip(features, means):
        sd = math.sqrt(sum((r[f] - mu) ** 2 for r in rows) / len(rows))
        sds.append(sd if sd > 1e-12 else 1.0)

    x = [[1.0] + [(r[f] - mu) / sd for f, mu, sd in zip(features, means, sds)] for r in rows]
    y = [r[target] for r in rows]
    p = len(x[0])
    xtx = [[sum(row[i] * row[j] for row in x) for j in range(p)] for i in range(p)]
    xty = [sum(row[i] * yy for row, yy in zip(x, y)) for i in range(p)]
    return solve_linear(xtx, xty), means, sds


def predict(row: dict, features: list[str], fit: tuple[list[float], list[float], list[float]]) -> float:
    beta, means, sds = fit
    if not features:
        return beta[0]
    return beta[0] + sum(
        beta[i + 1] * ((row[f] - means[i]) / sds[i])
        for i, f in enumerate(features)
    )


def error_metrics(actual: list[float], predicted: list[float]) -> dict:
    err = [p - y for y, p in zip(actual, predicted)]
    return {
        "n": len(actual),
        "rmse": math.sqrt(sum(e * e for e in err) / len(err)),
        "mae": sum(abs(e) for e in err) / len(err),
    }


def load_jsonl(path: Path) -> tuple[dict | None, list[dict]]:
    meta = None
    reps = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("kind") == "metadata":
                meta = obj
            elif obj.get("kind") == "rep":
                reps.append(obj)
    return meta, reps


def telemetry_row(rep: dict) -> dict:
    lanes = rep["resource_summary"]["lanes"]
    lane_values = list(lanes.values())
    return {
        "rep": rep["rep"],
        "arm": rep["arm"],
        "decode_ms": float(rep["target"]["timings"]["predicted_ms"]),
        "peer_count": float(len(rep.get("peers", {}))),
        "cpu_mean": statistics.mean(float(v["cpu"]["mean"]) for v in lane_values),
        "agg_pcie_rx_mb_mean": sum(float(v["gpu_pcie_rx_mb"]["mean"]) for v in lane_values),
        "peer_pcie_rx_mb_mean": sum(
            float(v["gpu_pcie_rx_mb"]["mean"])
            for idx, v in lanes.items()
            if int(idx) != 0
        ),
    }


def grouped_rep_cv(rows: list[dict], features: list[str]) -> dict:
    actual, predicted = [], []
    for rep_id in sorted({r["rep"] for r in rows}):
        train = [r for r in rows if r["rep"] != rep_id]
        test = [r for r in rows if r["rep"] == rep_id]
        fit = fit_ols(train, features, "decode_ms")
        actual.extend(r["decode_ms"] for r in test)
        predicted.extend(predict(r, features, fit) for r in test)
    return error_metrics(actual, predicted)


def matched_slowdown_points(reps: list[dict]) -> list[dict]:
    by_rep: dict[int, dict[str, dict]] = {}
    for row in reps:
        by_rep.setdefault(int(row["rep"]), {})[row["arm"]] = row
    out = []
    for rep_id, arms in sorted(by_rep.items()):
        if not all(k in arms for k in ("solo", "plus1", "plus2")):
            continue
        solo = float(arms["solo"]["target"]["timings"]["predicted_ms"])
        for arm in ("plus1", "plus2"):
            row = arms[arm]
            out.append({
                "rep": rep_id,
                "arm": arm,
                "peer_count": float(len(row.get("peers", {}))),
                "slowdown_fraction": float(row["target"]["timings"]["predicted_ms"]) / solo - 1.0,
            })
    return out


def loco_campaign_cv(campaigns: list[tuple[str, list[dict]]]) -> dict:
    folds = []
    all_peer_actual, all_peer_pred = [], []
    all_null_actual, all_null_pred = [], []

    for hold_name, hold_points in campaigns:
        train = [p for name, pts in campaigns if name != hold_name for p in pts]
        peer_fit = fit_ols(train, ["peer_count"], "slowdown_fraction")
        null_fit = ([0.0], [], [])  # explicit no-shared-pressure model
        peer_pred = [predict(p, ["peer_count"], peer_fit) for p in hold_points]
        null_pred = [predict(p, [], null_fit) for p in hold_points]
        actual = [p["slowdown_fraction"] for p in hold_points]
        peer_err = error_metrics(actual, peer_pred)
        null_err = error_metrics(actual, null_pred)
        folds.append({
            "held_out_campaign": hold_name,
            "peer_count_model": peer_err,
            "no_pressure_model": null_err,
            "peer_count_rmse_improvement_fraction": (
                1.0 - peer_err["rmse"] / null_err["rmse"] if null_err["rmse"] else None
            ),
        })
        all_peer_actual.extend(actual)
        all_peer_pred.extend(peer_pred)
        all_null_actual.extend(actual)
        all_null_pred.extend(null_pred)

    peer_all = error_metrics(all_peer_actual, all_peer_pred)
    null_all = error_metrics(all_null_actual, all_null_pred)
    return {
        "folds": folds,
        "aggregate_peer_count_model": peer_all,
        "aggregate_no_pressure_model": null_all,
        "aggregate_rmse_improvement_fraction": 1.0 - peer_all["rmse"] / null_all["rmse"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=Path("bench/raw/phase1-20261001"))
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    files = sorted(args.raw_dir.glob("phase1-direct-*.jsonl"))
    campaigns = []
    warm_telemetry_rows = None
    source_meta = {}

    for path in files:
        meta, reps = load_jsonl(path)
        if not reps:
            continue
        points = matched_slowdown_points(reps)
        if points:
            campaigns.append((path.name, points))
        source_meta[path.name] = {
            "target_state": meta.get("target_state") if meta else None,
            "target_context": meta.get("target_context") if meta else None,
            "peer_profile": meta.get("peer_profile") if meta else None,
            "matched_reps": len(points) // 2,
        }
        if path.name == "phase1-direct-warm-short-warm-short-telemetryfix.jsonl":
            warm_telemetry_rows = [telemetry_row(r) for r in reps]

    if warm_telemetry_rows is None:
        raise SystemExit("missing aligned warm-short telemetry campaign")

    models = {
        "constant": [],
        "peer_count": ["peer_count"],
        "peer_count_plus_cpu": ["peer_count", "cpu_mean"],
        "peer_count_plus_aggregate_pcie_rx": ["peer_count", "agg_pcie_rx_mb_mean"],
        "peer_count_plus_peer_pcie_rx": ["peer_count", "peer_pcie_rx_mb_mean"],
        "peer_count_plus_cpu_plus_aggregate_pcie_rx": [
            "peer_count", "cpu_mean", "agg_pcie_rx_mb_mean"
        ],
    }
    telemetry_cv = {
        name: grouped_rep_cv(warm_telemetry_rows, features)
        for name, features in models.items()
    }

    peer_rmse = telemetry_cv["peer_count"]["rmse"]
    telemetry_candidates = {
        name: metrics for name, metrics in telemetry_cv.items()
        if name not in ("constant", "peer_count")
    }
    best_telemetry_name, best_telemetry_metrics = min(
        telemetry_candidates.items(), key=lambda kv: kv[1]["rmse"]
    )

    loco = loco_campaign_cv(campaigns)
    incremental_telemetry_improves = best_telemetry_metrics["rmse"] < peer_rmse

    result = {
        "kind": "phase2c_shared_pressure_gate",
        "schema": 1,
        "sources": source_meta,
        "aligned_warm_short_grouped_rep_cv": telemetry_cv,
        "aligned_warm_short_best_incremental_telemetry_model": {
            "model": best_telemetry_name,
            **best_telemetry_metrics,
            "rmse_improvement_vs_peer_count_fraction": 1.0 - best_telemetry_metrics["rmse"] / peer_rmse,
        },
        "leave_one_campaign_out_slowdown_cv": loco,
        "limitations": [
            "CPU/PCIe telemetry is sampled during the run, not a pre-routing signal.",
            "Long-prefill peer runs outlive the target request, so their run-average telemetry is not used for incremental pressure-model validation.",
            "The retained plus1 arm uses one specific peer lane; there is no peer-lane-1-only matched arm, so lane-pair-specific coupling is not identifiable from this dataset.",
        ],
        "decision": {
            "shared_interference_material": True,
            "simple_active_peer_count_generalizes_better_than_no_pressure": (
                loco["aggregate_rmse_improvement_fraction"] > 0
                and all(
                    f["peer_count_rmse_improvement_fraction"] > 0
                    for f in loco["folds"]
                )
            ),
            "continuous_cpu_pcie_telemetry_adds_held_out_value_over_peer_count": incremental_telemetry_improves,
            "add_lane_specific_shared_pressure_term_now": False,
            "next_gate": (
                "carry active-concurrency pressure into Phase 2D admission/tail experiments; "
                "do not add a PCIe/CPU coupling coefficient to placement without new lane-pair-specific held-out evidence"
            ),
        },
    }

    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
