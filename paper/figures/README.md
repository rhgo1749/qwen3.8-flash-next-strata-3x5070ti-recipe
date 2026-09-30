# Figures

Planned paper figures:

1. `architecture` — clients/router → independent GPU lanes → one shared host expert arena; shared vs lane-local state.
2. `scaling` — 1/2/3-GPU common-wall aggregate TG with error bars.
3. `memory-ablation` — private vs shared two-engine PSS.
4. `hetero-isolation` — fast-lane solo/concurrent TG plus concurrent 5060 Ti contribution.
5. `workload-sensitivity` — workload TG together with cache-hit and speculative-acceptance context.

Generate figures from the canonical CSV files under `../../bench/`. Do not hand-edit plotted values independently of those datasets.

Prefer vector PDF/SVG sources for the final manuscript where the venue permits them. Keep plotting scripts or generation notes alongside the evidence if a figure depends on nontrivial transformations.
