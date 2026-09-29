# Results

This repository owns the reference-host measurements for the GPU-per-lane Strata recipe. The implementation fork intentionally keeps only generic runtime and roadmap contracts.

## Reference implementation

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU: 3 × RTX 5070 Ti 16 GB
- PCIe: Gen5 x8 / x4 / x8
- model: Qwen3.8-Flash-Next, Strata IQ3_XXS
- sanitized implementation pin: [`rhgo1749/Strata@844d6206`](https://github.com/rhgo1749/Strata/commit/844d62064b4327f80eae0f2980ccbd83b04fbe9a)

## Reference three-lane policy

```text
lane contexts       262144 / 262144 / 262144
host-KV guard       786432 tokens
resident KV         32768 / 32768 / 32768
physical CPU cores  5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
```

The repository keeps **different measurement classes separate** instead of promoting whichever number is largest. The second-undervolt state is the canonical public IQ3_XXS state; older pre-second-undervolt throughput numbers are intentionally omitted.

## Canonical IQ3_XXS performance

### Second-undervolt lane-local observation

Fixed short lane-local probes used `temperature=0` and `max_tokens=256` and recorded:

| Lane | Prompt reuse | TG | MTP/spec accepted |
| --- | --- | ---: | ---: |
| GPU0 | 72 reused + 5 read | **78.8 tok/s** | 126 / 166 (**75.9%**) |
| GPU1 | 69 reused + 5 read | **78.4 tok/s** | 129 / 157 (**82.2%**) |
| GPU2 | 73 reused + 5 read | **80.1 tok/s** | 141 / 177 (**79.7%**) |

Lane-sum:

```text
78.8 + 78.4 + 80.1 = 237.3 tok/s
```

**237.3 tok/s is a lane-sum of engine-reported TG, not a clean wall-clock aggregate.** It is the canonical public decode observation for this recipe, but it must not be described as an aggregate speedup.

## No-reuse prompt-processing spot checks after the second undervolt

These are independent lane observations with zero reused prompt tokens. They were not one synchronized three-lane prefill and therefore must not be summed into an aggregate PP number.

| Lane | Prompt tokens | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: |
| GPU0 | 45,519 | 29,756 ms | **1,529.7 tok/s** | 56.4 tok/s |
| GPU1 | 45,812 | 32,226 ms | **1,421.6 tok/s** | 50.1 tok/s |
| GPU2 | 64,972 | 42,275 ms | **1,536.9 tok/s** | 57.2 tok/s |

Mean PP across the three independent spot checks is about **1,496 tok/s/lane**.

## Full-window concurrency validation

Three independent real software-review prompts were run concurrently with every lane configured for a 262K context window:

| Client | Input tokens | Output tokens | Finish |
| --- | ---: | ---: | --- |
| A | 141,578 | 992 | `stop` |
| B | 144,875 | 1,295 | `stop` |
| C | 144,777 | 871 | `stop` |

All three inputs exceeded the former 131,072-token per-lane limit. No context-overflow error, CUDA OOM, API failure, or lane death occurred.

This run is retained as **262K ×3 capacity and client-compatibility evidence**, not as a 262K-token-per-prompt benchmark and not as the canonical throughput benchmark.

## IQ3_S challenger profile — 2026-09-29

A clean three-lane IQ3_S run was also completed on the same reference host with the same `262144 / 262144 / 262144` context policy, `32768` resident KV per lane, `5 / 6 / 5` physical-core split, and `0.55 / 0.25 / 0.55` PCIe fractions.

Key clean observations:

- shared expert arena: **46.84 GiB**;
- hot-expert cache: **4548 slots / 8.67 GiB per lane**;
- controlled concurrent short TG: **60.5 / 63.8 / 59.1 tok/s**;
- short TG lane-sum: **183.4 tok/s**;
- concurrent ~30K no-reuse PP: **1,553.7 / 1,323.9 / 1,545.1 tok/s**;
- the x4 middle lane was about **14.6% slower** in PP than the mean of the two x8 lanes;
- no lane death or CUDA OOM occurred during the run.

The IQ3_S short lane-sum is about 23% below the canonical IQ3_XXS lane-sum, but those two figures come from different short-probe workloads and generation lengths. Treat that percentage as an **indicative cross-run comparison**, not a controlled quantization A/B.

The first IQ3_S bring-up was excluded because two idle-holder containers were still occupying roughly 0.5 GiB of GPU1 VRAM and reduced that lane's hot-expert cache. The retained dataset was collected only after removing those holders and restarting all three lanes cleanly; the holders were restored after the benchmark.

Full IQ3_S configuration, per-lane logs, power samples, and reporting caveats are recorded in [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md).

## Resident-KV boundary

Testing a larger GPU-resident KV window showed that giving KV more VRAM can displace the hot-expert tier. The reference host therefore keeps **32K resident KV on each lane** rather than maximizing resident KV in isolation.

## Reporting rule

For this repository:

- **237.3 tok/s** is the canonical IQ3_XXS post-second-undervolt **lane-sum**, not wall-clock aggregate throughput;
- independent IQ3_XXS PP spot checks must not be summed because their prefill intervals were not one synchronized benchmark;
- the 141K–145K ×3 run is capacity/stability/client-compatibility evidence for three lanes configured to 262K each;
- **183.4 tok/s** is the clean IQ3_S controlled short **lane-sum**, not wall-clock aggregate throughput;
- the IQ3_S ~30K PP figures are concurrent per-lane engine rates and must not be promoted as a summed wall-clock PP number;
- do not infer a causal undervolt or quantization speedup/slowdown without a clean same-workload wall-timed A/B.

## More detail

- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — canonical second-undervolt GPU tuning and IQ3_XXS PP/TG dataset
- [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md) — IQ3_S three-lane challenger benchmark
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — sanitized full-window and serving validation
- [`bench/README.md`](bench/README.md) — measurement/reporting rules
- [`docs/multigpu-shared-runtime.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-shared-runtime.md) — generic implementation contract
- [`docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md) — generic implementation roadmap
