# Documentation index

This directory keeps human-readable experiment and implementation records for the GPU-per-lane Strata recipe.

Machine-readable benchmark repetitions live under [`../bench/`](../bench/). The current promoted summary is [`../RESULTS.md`](../RESULTS.md). Generic runtime contracts and source code belong in [`rhgo1749/Strata-Lanes`](https://github.com/rhgo1749/Strata-Lanes).

## Current paper-validation evidence — Strata 0.1.27

- [`systems-ablation-0.1.27-20260930.md`](systems-ablation-0.1.27-20260930.md) — 1→2→3 GPU scaling, private-vs-shared PSS, heterogeneous isolation, methodology, and caveats.
- [`workload-sensitivity-0.1.27-20260930.md`](workload-sensitivity-0.1.27-20260930.md) — fiction/coding/reasoning/long-context PP/TG, cache-hit, speculative-acceptance, and mixed-serving measurements.
- [`fork-and-implementation.md`](fork-and-implementation.md) — ownership boundary between the Strata implementation fork and this reproducibility repository.

Corresponding machine-readable files:

- [`../bench/systems-ablation-0.1.27-20260930.csv`](../bench/systems-ablation-0.1.27-20260930.csv)
- [`../bench/workload-sensitivity-0.1.27-20260930.csv`](../bench/workload-sensitivity-0.1.27-20260930.csv)
- [`../bench/strata-0.1.27-promotion-20260930.csv`](../bench/strata-0.1.27-promotion-20260930.csv)

## Historical evidence

Historical records are intentionally kept at their original paths so existing links remain stable.

### Strata 0.1.24

- [`strata-0.1.24-promotion-20260930.md`](strata-0.1.24-promotion-20260930.md) — prior promoted baseline and adaptive-replacement measurements.
- [`../bench/adaptive-swap-20260930.csv`](../bench/adaptive-swap-20260930.csv) — machine-readable adaptive trace summary.

### Strata 0.1.22 generation and earlier measurements

- [`strata-0.1.22-promotion-20260929.md`](strata-0.1.22-promotion-20260929.md) — historical 0.1.22 promotion.
- [`systems-ablation-20260929.md`](systems-ablation-20260929.md) — earlier architecture scaling/RAM/heterogeneous experiment.
- [`iq3-s-3lane-benchmark-20260929.md`](iq3-s-3lane-benchmark-20260929.md) — historical IQ3_S three-lane benchmark detail.
- [`reference-host-validation-20260929.md`](reference-host-validation-20260929.md) — historical long-context reference-host validation.
- [`undervolt-v2-20260929.md`](undervolt-v2-20260929.md) — separately documented reference tuning experiment; do not treat it as verified provenance for the final 0.1.27 paper-validation run.

## Reporting rule

Use the 0.1.27 files above for current paper claims. Historical files are retained for provenance and qualitative comparison, not as strict software-version A/B measurements unless the underlying prompts, model, quantization, runtime settings, and measurement contract match.
