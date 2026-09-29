# Results

This repository owns the reference-host measurements for the GPU-per-lane Strata recipe. The implementation fork intentionally keeps only generic runtime and roadmap contracts.

## Reference implementation

- CPU: AMD Ryzen 9 9950X3D, 16C/32T
- RAM: 128 GB DDR5
- GPU: 3 × RTX 5070 Ti 16 GB
- PCIe: Gen5 x8 / x4 / x8
- model: Qwen3.8-Flash-Next, Strata IQ3_XXS
- sanitized implementation pin: [`rhgo1749/Strata@844d6206`](https://github.com/rhgo1749/Strata/commit/844d62064b4327f80eae0f2980ccbd83b04fbe9a)

## Promoted three-lane policy

```text
lane contexts       262144 / 262144 / 262144
host-KV guard       786432 tokens
resident KV         32768 / 32768 / 32768
physical CPU cores  5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
```

## Headline measurements

- long-context prompt processing: roughly **1.5–1.6k tok/s per lane**;
- long-context aggregate prompt processing: roughly **4.5–4.8k tok/s**;
- long-context decode: roughly **54–64 tok/s per lane**;
- long-context aggregate decode: roughly **175–190 tok/s**;
- short warm pre-second-undervolt aggregate: **216.1 tok/s**, best observed round **221.1 tok/s**;
- second-undervolt warm lane-local result: **78.8 / 78.4 / 80.1 tok/s**, or **237.3 tok/s lane-sum**.

The 237.3 tok/s value is a lane-sum rather than a clean wall-timed aggregate and should not be presented as proof that undervolting caused a speedup.

## Long-context validation

Three independent real software-review prompts were launched concurrently. Their source repositories and local session identifiers are intentionally omitted from this public record.

| Client | Input tokens | Output tokens | API latency | Finish |
| --- | ---: | ---: | ---: | --- |
| A | 141,578 | 992 | 298.7 s | `stop` |
| B | 144,875 | 1,295 | 229.3 s | `stop` |
| C | 144,777 | 871 | 211.4 s | `stop` |

All three inputs exceeded the former 131,072-token per-lane limit. No context-overflow error, CUDA OOM, API failure, or lane death occurred.

These latencies are not a raw throughput benchmark because a small amount of earlier work was still draining near the start of the run.

## CPU affinity progression

Representative warm measurements:

| CPU cores | per-lane `pcie-frac` | warm aggregate |
| --- | --- | ---: |
| overlap-prone baseline | default | ~50 tok/s |
| disjoint automatic partition | default | ~136–138 tok/s |
| 5/6/5 | 0.55 / 0.55 / 0.55 | 174.5 tok/s |
| 5/6/5 | 0.55 / 0.35 / 0.55 | 202.9 tok/s |
| **5/6/5** | **0.55 / 0.25 / 0.55** | **216.1 tok/s** |
| 5/6/5 | 0.55 / 0.15 / 0.55 | 213.1 tok/s |
| 5/6/5 | 0.65 / 0.25 / 0.65 | 206.9 tok/s |
| 5/7/4 | 0.55 / 0.25 / 0.55 | 215.1 tok/s |

These values are specific to the reference host and should not be copied blindly to another topology.

## Resident-KV boundary

Increasing one lane from 32K to 64K GPU-resident KV reduced hot-expert cache capacity, pushed the measured expert-cache hit rate down to 54.2%, and reduced cold long-context decode from 60.1 tok/s to 45.0 tok/s. The promoted reference host therefore keeps 32K resident KV on each lane.

## More detail

- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — full sanitized reference-host validation
- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — second-undervolt dataset
- [`bench/README.md`](bench/README.md) — measurement/reporting rules
- [`docs/multigpu-shared-runtime.md`](https://github.com/rhgo1749/Strata/blob/844d62064b4327f80eae0f2980ccbd83b04fbe9a/docs/multigpu-shared-runtime.md) — generic implementation contract
- [`docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/844d62064b4327f80eae0f2980ccbd83b04fbe9a/docs/multigpu-roadmap.md) — generic implementation roadmap
