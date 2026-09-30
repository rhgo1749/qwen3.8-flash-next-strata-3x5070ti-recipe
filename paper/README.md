# Paper workspace

This directory is the working preprint area for the GPU-per-lane / shared-host expert-arena paper.

## Branch policy

- Work on the paper in `paper/preprint` while the manuscript is changing rapidly.
- Keep benchmark data, promoted measurements, and experiment methodology canonical on `main` under `bench/`, `docs/`, and `RESULTS.md`.
- Do not copy or silently edit benchmark numbers inside the paper without first updating the canonical evidence on `main`.
- Merge `paper/` to `main` only after the first public preprint is stable.
- Add `CITATION.cff` to `main` when the public preprint/arXiv identifier and preferred citation are known.

## Current evidence pin

The initial paper workspace is based on the Strata 0.1.27 validation package:

- implementation fork: `rhgo1749/Strata@6cf101d5b98523cbaefc34a199faa5657c5c2719`
- upstream Strata 0.1.27: `a79080535d1b2a71a3419a0d97d8e7dca194b0f1`
- recipe evidence baseline: main commit `69add1c321e156d591441cf745e937ace89709d9`

Canonical inputs:

- `../RESULTS.md`
- `../docs/systems-ablation-0.1.27-20260930.md`
- `../docs/workload-sensitivity-0.1.27-20260930.md`
- `../bench/systems-ablation-0.1.27-20260930.csv`
- `../bench/workload-sensitivity-0.1.27-20260930.csv`
- `../bench/strata-0.1.27-promotion-20260930.csv`

## Build

A minimal local build is:

```bash
cd paper
latexmk -pdf main.tex
```

The manuscript intentionally starts with a generic article layout. Replace it with the target workshop/conference template only after selecting a venue.

## Layout

- `main.tex` — working manuscript source
- `references.bib` — bibliography source
- `figures/` — generated/exported paper figures
- `tables/` — table-generation notes or exported table fragments

Do not commit generated LaTeX auxiliary files. A final PDF may be attached to a release or added intentionally once a public preprint is ready.
