# Strata 0.1.38 upstream-sync promotion — 2026-10-03

## Scope

This is a bounded compatibility promotion of the Strata-Lanes software baseline from upstream Strata 0.1.34 to **0.1.38**.

```text
Strata-Lanes merge      8ea68eaab3ee93f1c820f5103d64ca251cfe52b6
upstream Strata         99f3dbd0b21d1401b3769e0c0d963913607f380b
upstream tag            v0.1.38
reference host          Ryzen 9 9950X3D / 128 GB DDR5 / RTX 5070 Ti 16 GB x3
driver / CUDA           615.71.09 / 13.4
quant                   Qwen3.8-Flash-Next GSQ-RCO IQ3_S
candidate binary sha256 e8740716451ac5b7f5f0155a3dca442e6c3ea2c768e262ed01ed54f2f8195957
```

## Merge compatibility work

The two textual conflicts were resolved deliberately rather than by choosing one side:

- `src/core/expert_source.cpp`: a shared-arena follower still verifies readiness and skips source loading; the population leader uses 0.1.38's buffered/unbuffered expert loader and publishes readiness only after a complete successful load.
- `src/program/generate.cpp`: fork adaptive tracing and upstream `--expert-profile-save` coexist. The fork's expanded `PendingSwap` type is used by the new profile/peer code rather than treating it as the older pair type.

Ordinary lane configuration also strips inherited engine-internal multi-GPU options (`--layer-split`, `--split-device`, `--peer-*`, `--expert-cache-device1..3`, and remote expert placement). A copied parent `--expert-profile-save` path is stripped as well so several lane processes cannot become concurrent writers to one profile file. Static `--expert-profile` input remains allowed.

Conversation parking remains disabled in the production lane contract until parked-state ownership is explicitly modeled by the Lanes scheduler.

## Compatibility gate

- Python serving suite: **256 tests run, 7 skipped, no failures**
- CUDA **13.4.92**, sm_120 Release configure/build: **PASS**
- candidate `strata` binary: **PASS**
- focused CTests: `pinned_shared_test`, `expert_profile_save_test`, `file_expert_source_test`: **3/3 PASS**
- live 3-lane shared-arena startup: **PASS**
- three simultaneous public requests: **PASS**, one routed to each of GPU0/GPU1/GPU2
- observed queue waits in that smoke: **2.7–5.3 ms**
- short-request decode in that smoke: **48.8 / 48.9 / 49.1 tok/s**, with the same MTP acceptance (**23/26**) on all three requests

The short smoke is a correctness/health check, not a replacement for the retained full throughput campaigns.

## Bounded long-prompt A/B

Because 0.1.38 contains prompt-path changes, a matched single-lane A/B was run against the still-installed 0.1.31 production binary.

Conditions were held to the same GPU0, IQ3_S model/pack, 262144 context, INT8 KV, 32768 resident KV, `pcie_frac=0.55`, no reused prefix for the long prompts, and 16 output tokens.

| Fresh prompt | Installed 0.1.31 | Candidate 0.1.38 | Delta |
| ---: | ---: | ---: | ---: |
| ~15K tokens | 2498.4 tok/s | **2735.0 tok/s** | **+9.5%** |
| ~30K tokens | 2594.7 tok/s | **2784.0 tok/s** | **+7.3%** |

This is a **bounded directional compatibility A/B with one retained sample per long-prompt size**, not a new full performance campaign. The 16-token decode tails were acceptance-sensitive, so no decode-speed promotion claim is made from them.

## Evidence boundary

The full architecture-performance matrix remains the Strata 0.1.30 campaign. The latest full live scheduler/lifecycle campaign remains the Strata 0.1.31 evidence. Neither is relabeled as 0.1.38.

The 0.1.38 record establishes software compatibility, live three-lane correctness, and a bounded indication that long-prompt prefill improved on the reference host.
