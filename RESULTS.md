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

The repository keeps **different measurement classes separate** instead of promoting whichever number is largest.

## Performance summary

### Clean wall-timed warm aggregate

The controlled short-warm benchmark remains the clean aggregate reference:

- **216.1 tok/s** controlled warm aggregate;
- **221.1 tok/s** best observed clean warm round.

These are wall-timed concurrent three-lane results from the pre-second-undervolt controlled dataset. They remain the appropriate public aggregate numbers because the wall interval was clean and the three requests were measured as one controlled concurrent run.

### Long-context real-workload aggregate

On overlapping long-context real workloads, aggregate decode was approximately:

- **175–190 tok/s aggregate TG**;
- prompt processing was roughly **1.5–1.6k tok/s per lane** on representative long-context observations.

These values describe real serving behavior rather than the fixed short-warm microbenchmark, so they should not be compared as if they were the same workload.

### Second-undervolt lane-local observation

After the second undervolt pass, fixed short lane-local probes used `temperature=0` and `max_tokens=256` and recorded:

| Lane | Prompt reuse | TG | MTP/spec accepted |
| --- | --- | ---: | ---: |
| GPU0 | 72 reused + 5 read | **78.8 tok/s** | 126 / 166 (**75.9%**) |
| GPU1 | 69 reused + 5 read | **78.4 tok/s** | 129 / 157 (**82.2%**) |
| GPU2 | 73 reused + 5 read | **80.1 tok/s** | 141 / 177 (**79.7%**) |

Lane-sum:

```text
78.8 + 78.4 + 80.1 = 237.3 tok/s
```

**237.3 tok/s is a lane-sum of engine-reported TG, not a clean wall-clock aggregate.** It demonstrates that the 2300 MHz / 875 mV plateau did not show an obvious decode regression, but it is not promoted as proof that aggregate throughput increased from 221.1 to 237.3 tok/s.

A concise public wording is:

> **237.3 tok/s lane-sum was observed after the second undervolt pass, while 221.1 tok/s remains the best clean wall-timed warm aggregate.**

## No-reuse prompt-processing spot checks after the second undervolt

These are independent lane observations with zero reused prompt tokens. They were not one synchronized three-lane prefill and therefore must not be summed into an aggregate PP number.

| Lane | Prompt tokens | Read time | PP | Following TG |
| --- | ---: | ---: | ---: | ---: |
| GPU0 | 45,519 | 29,756 ms | **1,529.7 tok/s** | 56.4 tok/s |
| GPU1 | 45,812 | 32,226 ms | **1,421.6 tok/s** | 50.1 tok/s |
| GPU2 | 64,972 | 42,275 ms | **1,536.9 tok/s** | 57.2 tok/s |

Mean PP across the three independent spot checks is about **1,496 tok/s/lane**.

## Full-window concurrency validation

Three independent real software-review prompts were also run concurrently to validate the full 262K window on every lane:

| Client | Input tokens | Output tokens | Finish |
| --- | ---: | ---: | --- |
| A | 141,578 | 992 | `stop` |
| B | 144,875 | 1,295 | `stop` |
| C | 144,777 | 871 | `stop` |

All three inputs exceeded the former 131,072-token per-lane limit. No context-overflow error, CUDA OOM, API failure, or lane death occurred.

This run is retained as **262K ×3 capacity and client-compatibility evidence**. Its real-workload throughput belongs to the long-context measurement class above, not the controlled short-warm class.

## Resident-KV boundary

Testing a larger GPU-resident KV window showed that giving KV more VRAM can displace the hot-expert tier. The reference host therefore keeps **32K resident KV on each lane** rather than maximizing resident KV in isolation.

## Reporting rule

For this repository:

- **216.1 tok/s** is the controlled clean warm aggregate reference;
- **221.1 tok/s** is the best observed clean wall-timed warm aggregate;
- **175–190 tok/s** describes long-context real-workload aggregate TG;
- **237.3 tok/s** must be described as the post-second-undervolt **lane-sum**, not wall aggregate;
- independent PP spot checks must not be summed unless their prefill intervals are known to overlap;
- do not infer a causal undervolt speedup without a clean same-workload stock-vs-undervolt wall-timed A/B.

## More detail

- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — second-undervolt GPU tuning and PP/TG dataset
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — sanitized full-window and serving validation
- [`bench/README.md`](bench/README.md) — measurement/reporting rules
- [`docs/multigpu-shared-runtime.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-shared-runtime.md) — generic implementation contract
- [`docs/multigpu-roadmap.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-roadmap.md) — generic implementation roadmap
