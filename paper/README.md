# Paper workspace

This directory is the working preprint area for the GPU-per-lane / shared-host expert-arena paper.

## Paper v1 freeze

The submitted v1 is reproducibly anchored independently of the moving `main` branch.

- immutable recipe snapshot by exact commit: [`f54597a071e56bb0412685c46c4d604d50e26e45`](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/commit/f54597a071e56bb0412685c46c4d604d50e26e45)
- convenience branch for that snapshot: [`paper-v1`](https://github.com/rhgo1749/qwen3.8-flash-next-strata-gpu-per-lane-recipe/tree/paper-v1)
- implementation fork used by the paper: [`rhgo1749/Strata@6cf101d5b98523cbaefc34a199faa5657c5c2719`](https://github.com/rhgo1749/Strata/commit/6cf101d5b98523cbaefc34a199faa5657c5c2719)
- upstream Strata 0.1.27 baseline: `a79080535d1b2a71a3419a0d97d8e7dca194b0f1`

For v1 reproduction, use the exact commit links above. `main` is allowed to continue evolving after submission and must not be interpreted as the paper's immutable code/evidence revision.

## Branch policy

- `paper-v1` is the frozen v1 snapshot and should not be moved or rewritten.
- `paper/preprint` remains a working manuscript branch for later revisions.
- `main` may continue to receive runtime, recipe, benchmark, and documentation work after v1.
- New paper revisions should receive a new explicit snapshot/pin rather than reusing the v1 pin.
- Do not copy or silently edit benchmark numbers inside a paper revision without reconciling them with the evidence snapshot used by that revision.
- Add `CITATION.cff` to `main` when the public preprint/arXiv identifier and preferred citation are known.

## V1 evidence pin

The v1 preprint uses the Strata 0.1.27 validation package at the frozen recipe snapshot above.

Canonical v1 inputs at `f54597a` are:

- `RESULTS.md`
- `docs/systems-ablation-0.1.27-20260930.md`
- `docs/workload-sensitivity-0.1.27-20260930.md`
- `bench/systems-ablation-0.1.27-20260930.csv`
- `bench/workload-sensitivity-0.1.27-20260930.csv`
- `bench/strata-0.1.27-promotion-20260930.csv`

These paths should be interpreted at `paper-v1` / `f54597a`, not at whatever commit `main` points to later.

## Build

Build from this directory so the relative `parts/` inputs resolve consistently:

```bash
cd paper
latexmk -pdf main.tex
```

`main.tex` is a small wrapper that inputs `parts/*.tex`. Concatenating those parts in wrapper order reproduces the reviewed single-file v1 source; the split only avoids large-file API limitations while keeping the manuscript easy to update.

## Layout

- `main.tex` — wrapper for the reviewed v1 manuscript
- `parts/` — manuscript source fragments in document order
- `references.bib` — bibliography workspace/reference metadata
- `figures/` — generated/exported paper figures
- `tables/` — table-generation notes or exported table fragments

Do not commit generated LaTeX auxiliary files. A final PDF may be attached to a release or added intentionally once a public preprint is ready.
