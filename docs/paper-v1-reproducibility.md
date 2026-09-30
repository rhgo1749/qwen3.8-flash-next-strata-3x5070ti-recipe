# Paper v1 reproducibility map

This document is the immutable-reference map for **Independent GPU Lanes with a Shared Pinned Expert Arena — Preprint v1 (September 2026)**.

The paper does **not** use the moving `main` branch as its implementation revision. It explicitly names the paper-validation Strata commit. `main` may continue evolving after submission.

## Frozen revisions

| Component | V1 revision |
| --- | --- |
| Recipe / evidence repository snapshot | [`f54597a071e56bb0412685c46c4d604d50e26e45`](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/commit/f54597a071e56bb0412685c46c4d604d50e26e45) |
| Convenience frozen recipe branch | [`paper-v1`](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/tree/paper-v1) |
| Strata implementation fork | [`6cf101d5b98523cbaefc34a199faa5657c5c2719`](https://github.com/rhgo1749/Strata/commit/6cf101d5b98523cbaefc34a199faa5657c5c2719) |
| Upstream Strata 0.1.27 | `a79080535d1b2a71a3419a0d97d8e7dca194b0f1` |
| Evaluated binary path | `build-production-027/strata` |

The manuscript text states the implementation pin as `6cf101d` and upstream baseline as `a790805`.

## V1 evidence files

Use these files at the frozen recipe commit, not at a future `main` HEAD:

- [RESULTS.md @ f54597a](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/blob/f54597a071e56bb0412685c46c4d604d50e26e45/RESULTS.md)
- [benchmark/reporting contract @ f54597a](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/blob/f54597a071e56bb0412685c46c4d604d50e26e45/bench/README.md)
- [systems methodology @ f54597a](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/blob/f54597a071e56bb0412685c46c4d604d50e26e45/docs/systems-ablation-0.1.27-20260930.md)
- [workload methodology @ f54597a](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/blob/f54597a071e56bb0412685c46c4d604d50e26e45/docs/workload-sensitivity-0.1.27-20260930.md)
- [systems repetitions CSV @ f54597a](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/blob/f54597a071e56bb0412685c46c4d604d50e26e45/bench/systems-ablation-0.1.27-20260930.csv)
- [workload repetitions CSV @ f54597a](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/blob/f54597a071e56bb0412685c46c4d604d50e26e45/bench/workload-sensitivity-0.1.27-20260930.csv)
- [validation/provenance CSV @ f54597a](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/blob/f54597a071e56bb0412685c46c4d604d50e26e45/bench/strata-0.1.27-promotion-20260930.csv)

## Branch semantics after v1

- `paper-v1`: frozen v1 snapshot; do not move or rewrite it.
- `main`: ongoing development and current documentation; it is allowed to advance.
- `paper/preprint`: working manuscript branch for later revisions.
- experimental branches such as vision work are not part of v1 unless a later paper revision explicitly adopts and pins them.

For any later revision, create a new explicit paper snapshot and record new exact commit IDs rather than changing the v1 references above.
