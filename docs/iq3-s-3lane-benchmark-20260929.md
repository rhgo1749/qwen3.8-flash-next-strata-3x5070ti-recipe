# IQ3_S three-lane benchmark — 2026-09-29

This note records the current reference-host IQ3_S measurements for the GPU-per-lane Strata architecture. IQ3_S is the model currently deployed on the reference host, while IQ3_XXS remains the repository's canonical performance-oriented comparison profile.

## Current promoted implementation

```text
repository  rhgo1749/Strata
commit      9dda206874387b20cac20837a1452f115a8f9f93
engine      Strata 0.1.22
architecture independent request-per-GPU lanes + one shared host expert arena
```

The existing recipe command surface remained compatible with 0.1.22; no migration flag was required.

## Host and runtime

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU: 3 × RTX 5070 Ti 16 GB
- PCIe: Gen5 x8 / x4 / x8
- model: Qwen3.8-Flash-Next GSQ-RCO IQ3_S
- shared host expert arena: **46.84 GiB** (`50,294,988,800` bytes)
- lane contexts: `262144 / 262144 / 262144`
- aggregate host-KV guard: `786432`
- resident KV: `32768 / 32768 / 32768`
- physical CPU-core allocation: `5 / 6 / 5`
- `pcie-frac`: `0.55 / 0.25 / 0.55`
- KV mode: `int8`
- MTP/speculation: `--spec 4 --spec-min-p 0.5`
- hot-expert cache on 0.1.22: **4524 slots / 8.63 GiB per lane**
- reported fully-loaded VRAM free: about **225 MiB per lane**

The canonical IQ3_XXS recipe uses an approximately **39.97 GiB** shared expert arena, so IQ3_S still requires about **17%** more shared expert RAM on this host.

## Measurement hygiene

All promoted measurements below were taken on the 0.1.22 production binary with GPU0–2 dedicated to Strata. Requests were sent directly to the three private lane endpoints so each lane's prompt reuse and engine-reported PP/TG could be inspected independently.

One intermediate rerun was discarded because the public idle proxy parked the backend between private benchmark requests; private-lane traffic does not reset that public idle timer. The backend was then woken through the public endpoint and the retained 15K, 30K, and warm-repeat measurements completed in one active backend interval.

No promoted long-prompt request reported prompt reuse, CUDA OOM, API failure, or lane death.

## Current clean warm three-request wall aggregate

Identical short requests used `temperature=0` and `max_tokens=128`. Each measurement session used one cold round followed by warm rounds with the same prefix. Four retained warm rounds across two backend sessions measured:

| Retained warm round | Completion tokens | Wall aggregate |
| --- | ---: | ---: |
| Session A / round 2 | 384 | **183.9 tok/s** |
| Session A / round 3 | 384 | **190.8 tok/s** |
| Session B / round 2 | 384 | **196.8 tok/s** |
| Session B / round 3 | 384 | **209.7 tok/s** |

The current reproducible warm range is therefore **183.9–209.7 tok/s wall aggregate**, with a four-round mean of **195.3 tok/s**.

This wall-derived aggregate is the preferred IQ3_S concurrent-serving headline metric. It should not be replaced by a lane-sum of engine-reported TG.

For the final retained round, engine-reported per-lane TG was:

```text
GPU0 74.8 tok/s
GPU1 77.1 tok/s
GPU2 72.9 tok/s
lane-sum 224.8 tok/s
wall aggregate 209.7 tok/s
```

The difference illustrates why lane-sum and wall aggregate must remain separate metric classes.

## Concurrent 15K no-reuse prompt processing

Three independent prompts were launched concurrently. Each lane received **15,048 prompt tokens** and reported **0 reused**.

| Lane | Prompt tokens | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: |
| GPU0 / x8 | 15,048 | 6,471 ms | **2,325.6 tok/s** | 42.9 tok/s |
| GPU1 / x4 | 15,048 | 8,330 ms | **1,806.5 tok/s** | 48.8 tok/s |
| GPU2 / x8 | 15,048 | 6,563 ms | **2,293.0 tok/s** | 45.5 tok/s |

The two x8 lanes averaged **2,309.3 tok/s**. The x4 middle lane was about **21.8% slower** than that x8 mean.

The common client wall interval for the three requests was 8.691 s. The table above reports per-lane engine PP; those PP values are not summed into an aggregate PP claim.

## Concurrent 30K no-reuse prompt processing

Three independent prompts were launched concurrently. Each lane received **30,024 prompt tokens** and again reported **0 reused**.

| Lane | Prompt tokens | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: |
| GPU0 / x8 | 30,024 | 12,765 ms | **2,352.1 tok/s** | 44.5 tok/s |
| GPU1 / x4 | 30,024 | 16,561 ms | **1,812.9 tok/s** | 50.0 tok/s |
| GPU2 / x8 | 30,024 | 12,785 ms | **2,348.3 tok/s** | 46.2 tok/s |

Mean PP across all three lanes was **2,171.1 tok/s/lane**. The two x8 lanes averaged **2,350.2 tok/s**, while the x4 middle lane was about **22.9% slower**.

The common client wall interval was 16.939 s. As with the 15K run, the per-lane PP rates are overlapping engine measurements and are not added together as an aggregate PP number.

## Historical IQ3_S dataset before the 0.1.22 promotion

The older IQ3_S benchmark generation used an earlier multi-lane engine and measured:

- short engine-reported TG: **60.5 / 63.8 / 59.1 tok/s**;
- TG lane-sum: **183.4 tok/s**;
- ~30K no-reuse PP: **1,553.7 / 1,323.9 / 1,545.1 tok/s**;
- hot-expert cache: **4548 slots / 8.67 GiB per lane**.

Compared with those historical ~30K PP rates, the 0.1.22 measurements are higher by approximately:

- GPU0: **+51.4%**;
- GPU1: **+36.9%**;
- GPU2: **+52.0%**;
- three-lane mean: **+47.3%**.

These percentages are **indicative software-generation comparisons**, not a strict same-prompt A/B: the prompt length was nearly identical (~30K) but the prompt content and runtime generation were not identical.

The old **183.4 tok/s** number remains valid historical lane-sum evidence, but it is no longer the preferred headline IQ3_S concurrent-serving metric now that clean wall-clock aggregate runs exist.

## Historical power samples

The earlier concurrent ~30K run recorded these `nvidia-smi` board-power samples:

| GPU | Mean sampled board power | Max sampled board power | Mean sampled SM clock |
| --- | ---: | ---: | ---: |
| GPU0 | 97.8 W | 128.9 W | 2222 MHz |
| GPU1 | 107.8 W | 129.2 W | 2221 MHz |
| GPU2 | 114.7 W | 145.5 W | 2218 MHz |

These remain historical board-power samples; the current 0.1.22 benchmark did not rerun a synchronized power capture, so they must not be treated as current efficiency measurements.

## Interpretation

IQ3_S is fully viable on the same 3 × 16 GB GPU / 128 GB host with a 262K context configured on every lane. Strata 0.1.22 materially improved the long-prompt path on this profile while preserving the existing lane architecture and launch contract.

The Gen5 x4 middle lane is now about **22% slower** than the x8-lane mean in both the retained 15K and 30K concurrent no-reuse PP runs, so asymmetric PCIe topology is a clearer prompt-processing constraint than in the older benchmark generation.

The current deployment can therefore keep IQ3_S as the quality-oriented production model while IQ3_XXS remains the faster performance reference. A controlled same-prompt quality/performance A/B is still required before making a universal quantization trade-off claim.
