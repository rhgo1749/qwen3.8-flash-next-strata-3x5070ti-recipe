# Phase 2B online scheduler policy A/B — 2026-10-01

Runtime commit: `0d6f237bc7a2bffd6cf5c795956118e9a92283da`  
Reference host: 3 independent Strata lanes with a shared pinned expert arena, 262144 context per lane.  
Workload: 6 sequential new sessions sharing a long exact leading prefix, then one synchronized continuation per session. Turn 1 = 32 output tokens; turn 2 = 128 output tokens.

## Decision

**Do not promote a Phase-2 scheduler challenger yet. Keep `safe-affinity-live-state-v1` as the production/rollback control while hardening long-lived session-start placement.**

Fresh-restart results identify `additive-new-prefill-retained-state-proxy-v1` as the strongest current challenger, but a second workload wave on the same long-lived supervisor exposed a 6-to-1 lane attractor. The retained trace also records the legacy safe placement key for every candidate lane; replaying that key on the exact second-wave states selects the same lane for all six starts. Therefore this is not evidence that additive alone is unsafe while the current safe policy is immune. It is evidence that **retained-state-only session-start scoring can become self-reinforcing after state accumulates**.

## Fresh-restart repeated comparison

| Policy | TG mean ± sd | TG range | p95 queue mean | p95 token TTFT mean | Placement |
|---|---:|---:|---:|---:|---|
| `safe-affinity-live-state-v1` | 74.5 ± 8.7 tok/s | 64.7–80.8 | 5.57s | 8.61s | 2/2/2 in 3/3 |
| `round-robin-idle-v1` | 70.1 ± 9.5 tok/s | 64.5–81.1 | 5.84s | 9.32s | 2/2/2 in 3/3 |
| `additive-new-prefill-retained-state-proxy-v1` | 80.8 ± 0.9 tok/s | 79.8–81.6 | 5.00s | 7.66s | 2/2/2 in 3/3 |

On fresh state, additive is both the fastest and the least variable of these three runs. That is enough to keep it as the leading challenger, but **not enough to promote it**, because fresh restart is not representative of a long-lived serving process.

## Long-lived-state probe

The additive server was intentionally reused for a second independent 6-session workload after the first wave had left retained state on all three lanes.

- First wave: session starts distributed 2/2/2.
- Second wave: all 6 new sessions selected lane 2.
- Second-wave continuation common-wall throughput: **29.3 tok/s**.
- Second-wave p95 queue wait: **21.84s**.
- Second-wave p95 token TTFT: **24.40s**.

The second-wave trace is retained as `bench/raw/phase2-20261001/additive-long-lived-two-wave-trace.jsonl`.

### Safe-policy counterfactual on the exact same state

Each trace decision records both the active challenger score and the legacy safe `placement_key`. For all six second-wave session starts, the lexicographic minimum safe key is also lane 2. Because the first counterfactual choice equals the actual choice, and that remains true after every recorded state transition, the counterfactual follows the same state path by induction.

The retained audit is `bench/raw/phase2-20261001/safe-counterfactual-on-long-lived-state.json`.

This changes the interpretation materially: **the current safe control is still the rollback policy because it is the deployed, correctness-hardened baseline, but it should not be considered immune to long-lived session-start concentration.** The next 2B change should harden the baseline/challenger family against that attractor before any default switch.

## Single-run challenger screen

| Policy | Session starts | Common-wall TG | p95 queue | p95 token TTFT | Result |
|---|---:|---:|---:|---:|---|
| `cache-aware-idle-v1` | 6/0/0 | 29.4 tok/s | 21.85s | 24.41s | reject current form: prefix reuse dominates balance |
| `session-start-balance-cache-aware-v1` | 2/2/2 | 64.1 tok/s | 6.20s | 10.13s | balanced, but no single-run win |
| `multiplicative-new-prefill-retained-state-proxy-v1` | 6/0/0 | 29.3 tok/s | 21.69s | 24.25s | reject current form: prefix reuse dominates balance |
| `retained-state-smallest-v1` | 2/2/2 | 64.7 tok/s | 6.14s | 10.07s | balanced, but no single-run win |

## Measurement hygiene

One attempted safe repeat at `/tmp/phase2-safe-r3-client.jsonl` is excluded because an earlier timed-out orchestration shell later injected extra requests. It is not retained as evidence.

The file `safe-r2-appended-raw-trace.jsonl` contains two fresh-server runs because the append-only trace pathname was reused. The retained safe-r2 client result is run ID `phase2-online-safe-affinity-live-state-v1-20261001-183701`; analysis must filter that run ID rather than treating the full file as one run.

All retained policy traces used for this campaign report runtime commit `0d6f237bc7a2bffd6cf5c795956118e9a92283da`.

## Additional operational finding

After many rapid benchmark teardown/start cycles, NVIDIA RTD3 entered an error state on PCI devices `02:00.0` and `16:00.0`. Kernel logs show RM lock assertions and power-management unload failures; `nvidia-smi` reports those devices as `Unknown Error`. Host RAM remained plentiful and memlock was unlimited, so the later lane-2 startup failure is not evidence for a scheduler regression. No performance result from that failed startup is retained.

This also means future repeated scheduler campaigns should avoid bypassing the production idle-holder/RTD3 lifecycle for dozens of rapid restarts. Prefer fewer controlled restarts or temporarily pin the benchmark GPUs active during a campaign.

## Gate outcome

- Phase 2A observability/signals: complete.
- Phase 2B simple-policy live comparison: **evidence collected, no policy promotion**.
- Fresh-state leader: `additive-new-prefill-retained-state-proxy-v1`.
- Long-lived-state blocker: session-start concentration after retained state accumulates.
- Production control: keep `safe-affinity-live-state-v1` unchanged until that blocker is fixed and repeated long-lived A/B passes.
- Next 2B experiment: add an explicit session-start balance term (or bounded imbalance fallback) ahead of retained-state/reuse preference, then test **multiple waves on one persistent supervisor**, not only fresh restarts.
- Phase 2C shared-pressure modeling remains separate; Phase 1 interference evidence justifies studying it, but this campaign does not justify promoting a coupling term.
