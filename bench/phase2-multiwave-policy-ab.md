# Phase 2B persistent-supervisor multi-wave gate

The single-wave client in `phase2_online_policy_ab.py` is useful for fresh-state A/B, but the 2026-10-01 campaign exposed a failure mode that only appeared **after retained state accumulated across waves on one supervisor**. Restarting the server between every run hides that failure.

Use `phase2_multiwave_policy_ab.py` for the promotion gate.

Example:

```bash
python3 bench/phase2_multiwave_policy_ab.py \
  --policy balanced-additive-new-prefill-retained-state-proxy-v1 \
  --waves 3 \
  --sessions 6 \
  --facts 300 \
  --turn1-tokens 32 \
  --turn2-tokens 128 \
  --output-dir bench/raw/phase2-<date>/balanced-additive-multiwave
```

The wrapper launches the existing single-wave client repeatedly **without restarting Strata**. Each wave uses fresh session IDs, while lane-local retained state and the supervisor's affinity history remain in place. This directly exercises the long-lived session-start attractor that fresh-restart-only campaigns miss.

Each wave retains its own JSONL file plus one `multiwave-summary.json` containing:

- per-wave session assignment counts and maximum single-lane share;
- continuation common-wall throughput;
- p95 queue wait, token TTFT and E2E;
- aggregate distribution across waves;
- whether every underlying single-wave correctness gate passed.

The wrapper refuses to overwrite retained evidence unless `--overwrite` is explicitly supplied.

## Promotion use

For Phase 2B, a policy should not be promoted from a fresh-state win alone. At minimum, compare the safe control and candidate on the same persistent-supervisor wave count, and require:

1. no correctness/affinity failures;
2. no progressive session-start concentration;
3. no material p95 queue/TTFT regression;
4. repeatable throughput benefit or a clearly declared latency/locality objective;
5. the same result after the supervisor has accumulated realistic retained state.

Multi-wave testing is intentionally designed to gather long-lived-state evidence without resetting the scheduler state between waves.
