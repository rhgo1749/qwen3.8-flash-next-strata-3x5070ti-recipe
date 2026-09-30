# Experimental x4 vision lane — Strata 0.1.27

> **Scope:** post-v1 experimental recipe now carried on `main`. These measurements are **not part of paper/preprint v1** and do not modify the frozen `paper-v1` evidence snapshot.

## Provenance

- Frozen paper-v1 recipe snapshot: `f54597a071e56bb0412685c46c4d604d50e26e45`
- Strata benchmarked commit: `eaea3c176d8445186a15e607c3d04404d6334ec9`
- Strata vision promotion tip / current `main`: `cbb1331f1e05e71b8c1092f48c92f2ca6fdbce0d`
- Base/paper Strata commit: `6cf101d5b98523cbaefc34a199faa5657c5c2719`
- Upstream baseline represented by that base: Strata `0.1.27` (`a79080535d1b2a71a3419a0d97d8e7dca194b0f1`)
- Engine / vision helper: local Strata `0.1.27` build

The upstream-PR-only branch `upstream/shared-arena-backing` remains a separate `0.1.26`-based branch. Paper v1 remains pinned independently; the moving Strata `main` now includes the vision-lane routing work.

## Hardware and lane layout

```text
lane 0 / physical GPU0 / RTX 5070 Ti / PCIe x8 -> text
lane 1 / physical GPU1 / RTX 5070 Ti / PCIe x4 -> text + GPU strata-vision
lane 2 / physical GPU2 / RTX 5070 Ti / PCIe x8 -> text
```

Common settings:

- 262,144-token context per lane
- 32,768 resident KV tokens per lane, INT8 KV
- shared pinned expert arena unchanged
- CPU physical-core partition: 5 / 6 / 5
- per-lane PCIe fraction: 0.55 / 0.25 / 0.55
- MTP speculation enabled (`--spec 4 --spec-min-p 0.5`)
- only lane 1 keeps the vision config and `--vram-reserve-mib`; lanes 0 and 2 strip both
- GPU vision encoder process: about **1,374 MiB** in the measured runs

The two tested expert quants were `IQ3_S` and `IQ3_XXS`.

## Stability finding: 700 MiB reserve was too small for IQ3_S

The initial production configuration used `--vram-reserve-mib 700` on the x4 vision lane. A three-lane request using the fixed 1,827-token text prompt and a 512-token completion target caused the lane-1 engine to terminate with a CUDA allocation failure:

```text
ggml-cuda (strata mmq): out of memory: cudaMalloc(&p, size)
```

Immediately before the failure, the engine reported only about **94 MiB** of free VRAM and recommended at least **1,118 MiB** of reserve. The experiment therefore promoted **1,200 MiB** as the local production value.

With 1,200 MiB reserve, both IQ3_S and IQ3_XXS completed all retained measurements below without a lane failure.

## Text throughput with vision enabled

Measurement contract for this campaign:

- three simultaneous requests through the multi-GPU supervisor
- fixed prompt ID `91c3b2cd291047ff`
- 1,827 prompt tokens per request
- 512 completion tokens per request
- `temperature=0`, `seed=1234`
- one unretained warm-up round
- reported throughput is **common-wall aggregate TG**: 1,536 completion tokens divided by one common client wall interval
- benchmark traffic went directly to the backend supervisor (`127.0.0.1:18087`) so idle-proxy wake/park behavior is excluded

| Quant | 3-lane common-wall aggregate TG | Range | Repetitions |
|---|---:|---:|---:|
| IQ3_S | **163.12 ± 5.08 tok/s** | 158.88–171.65 | 5 |
| IQ3_XXS | **203.52 ± 5.86 tok/s** | 196.37–212.40 | 5 |

Under this vision-enabled campaign and prompt, IQ3_XXS delivered **1.248×** the common-wall aggregate throughput of IQ3_S. This is a within-campaign comparison only. Do **not** compare the absolute numbers directly with the paper scaling table: that table uses a different fixed prompt/evidence campaign and remains frozen in `paper-v1`.

## Vision request results

Test image: 640×480, red background, blue center square. The request asked for the two colors in one short sentence. Both quants answered correctly in every retained request.

| Quant | First no-cache E2E request | First prompt processing | Warm repeated-image E2E | Correct |
|---|---:|---:|---:|---:|
| IQ3_S | **2.581 s** | 327 tokens @ 146.7 tok/s | **0.331 ± 0.020 s** | 5/5 |
| IQ3_XXS | **2.126 s** | 327 tokens @ 175.3 tok/s | **0.295 ± 0.016 s** | 5/5 |

The first request for each quant reported `cached_tokens=0`. Repetitions 2–5 used PNGs with different metadata but identical decoded pixels, and the server reported 320 cached prompt tokens. Therefore the ~0.3 s values are **warm repeated-image/prompt-cache results**, not fresh-image encoder latency. The first no-cache row is the relevant E2E number for this particular fresh image; it still includes prompt processing and the short decode, so it should not be labeled as pure encoder time.

## VRAM snapshot

Process VRAM after the retained runs:

| Quant | GPU0 x8 text engine | GPU1 x4 text engine | GPU1 vision encoder | GPU2 x8 text engine |
|---|---:|---:|---:|---:|
| IQ3_S | 15,818 MiB | 13,942 MiB | 1,374 MiB | 15,820 MiB |
| IQ3_XXS | 15,686 MiB | 13,804 MiB | 1,374 MiB | 15,686 MiB |

This is the intended shape: the two x8 lanes keep their text-only cache budget, while only the middle x4 lane pays the vision encoder and reserve cost.

## Local production state after the experiment

The host was restored to:

```text
IQ3_S
Strata 0.1.27
lane 1 / physical GPU1 x4 = vision-capable
--vram-reserve-mib 1200 on the vision lane only
262144 context per lane
32768 resident KV per lane
```

After the final `cbb1331` restart, all three lanes were alive, `/props` reported `modalities.vision=true`, and the public `8087 /health` endpoint reported `images=true`. A final image smoke test through port 8087 correctly identified the red background and blue center square.

## Raw data

See:

- `bench/vision-x4-lane-0.1.27-20260930.csv`

The raw file also retains the failed 700 MiB reserve trial rather than silently dropping it.
