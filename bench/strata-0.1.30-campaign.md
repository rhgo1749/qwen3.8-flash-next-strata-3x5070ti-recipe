# Strata 0.1.30 measurement campaign

This campaign regenerated the paper-facing systems evidence on one software generation and promoted Strata 0.1.30 as the current recipe baseline on 2026-10-01.

## Frozen promoted pins

```text
implementation  rhgo1749/Strata-Lanes
candidate       dcdd46ff37b1baf5172a96389fbdc0c7b51a7dbc
upstream        Niko1221/Strata
upstream head   30ec18ec7094550fcc594fd948220d511d80464e
engine          0.1.30
CUDA            13.4
reference driver 615.71.09
```

The measured generation passed the required matrix and is promoted. All retained headline rows identify the same fork/upstream generation. `recipe/launch-3lane-0.1.30-candidate.sh.example` is retained as the frozen campaign launcher, while `recipe/launch-3lane.sh.example` is the promoted operational example. `recipe/capture-0.1.30-provenance.sh.example` captures the read-only host/software snapshot used beside retained runs.

## Gate 0 — implementation and provenance

Before performance runs, record:

- exact fork and upstream commits;
- upstream-native shared-arena contract (`STRATA-ARENA-V1` header, /dev/shm backing, pack-hash validation) and the exact backing inode/size for shared-PSS runs;
- SHA-256 of the tested `strata` binary;
- compiler/CUDA and NVIDIA driver versions;
- GPU model, PCI bus ID, negotiated width, and maximum link generation;
- CPU and RAM;
- model and quantization artifact hashes or stable artifact identifiers;
- prompt bytes/hash and token count;
- context, resident KV, MTP/speculation, expert-cache and PCIe settings;
- CPU affinity partition;
- GPU clock/power/undervolt/memory tuning snapshot;
- whether the run is cold, clean-warm, reused-prefix, or steady-state warm.

The implementation gate is tracked separately in `strata-0.1.30-candidate-20261001.csv`. Missing optional model fixtures are recorded as unavailable, not silently converted to passes.

## Gate 1 — regenerate the headline systems table

All retained headline rows use the same 0.1.30 candidate generation.

### 1 → 2 → 3 independent-lane scaling

Use one fixed IQ3_S prompt, fixed completion length, `temperature=0`, fixed seed, and the same warm/reuse contract across lane counts. Synchronize client release and compute:

```text
common-wall aggregate TG = sum(completion tokens) / (last completion - common release)
```

Retain lane-local TG/PP/TTFT as diagnostics, but never substitute lane-sum TG for common-wall aggregate throughput.

### Private arena ↔ shared arena PSS

Use the same two fully ready engines and the same model/runtime configuration. Snapshot `/proc/<pid>/smaps_rollup` after readiness stabilizes. Report summed PSS and, for shared mode, the shared file mapping identity/size and its shared-vs-private accounting. Host-global swap may be recorded but is not attributed to an individual process.

### Heterogeneous isolation

Compare an RTX 5070 Ti lane alone against the same RTX 5070 Ti lane while an RTX 5060 Ti lane runs concurrently. Interleave solo/concurrent conditions rather than running all of one condition first. Report the fast lane's lane-local TG, slow-lane TG, common-wall aggregate throughput, PP/TTFT, cache-hit rate and speculative acceptance where available.

### Workload sensitivity

Repeat the existing fiction/coding/reasoning short/medium and long-review matrix. Keep no-reuse PP/TTFT separate from warm decode TG. Cache-hit rate and speculative acceptance remain observational unless a controlled intervention isolates them.

### Mixed three-lane serving

Rotate fiction/coding/reasoning assignments across the three primary lanes. Report common-wall aggregate throughput plus lane-local PP/TTFT/TG. Rotation is part of the contract so GPU position and workload class are not permanently confounded.

## Gate 2 — oversubscription serving curve

Hold the server at exactly three independent lanes and submit synchronized batches of:

```text
M = 3, 4, 6, 9 requests
N = 3 lanes
```

Use identical fixed-length requests for the primary serving curve. Run a separate mixed-workload overload arm only after the equal-work primary curve is complete.

### Per-request fields

Each request row records:

- synchronized submit timestamp/offset;
- exact lane-admission timestamp;
- lane index;
- queue wait;
- service time;
- end-to-end latency;
- TTFT to the first generated token, excluding SSE keep-alive comments;
- prompt/output tokens;
- PP and decode TG when reported by the engine;
- prompt reuse/cache state;
- finish reason and errors/cancellations.

Exact queue wait is a server-side quantity. Launch the supervisor with `--bench-trace-jsonl FILE` and send `X-Strata-Benchmark-Run-Id`, `X-Strata-Benchmark-Request-Id`, and `X-Strata-Benchmark-Submit-Rank` on each request. The supervisor records queue-entry, lane-admission and release timestamps, lane index, 0-based admission rank, exact scheduler queue wait and service time; it also returns `X-Strata-Lane-Index`, `X-Strata-Admission-Rank` and `X-Strata-Queue-Wait-Ms` response headers. The JSONL lease record is the source of truth for queue timing; client time-to-response-headers remains only a cross-check.

### Per-run fields

For every synchronized batch report:

- common-wall aggregate throughput;
- p50/p95 queue wait;
- p50/p95 end-to-end latency;
- p99 only when enough retained request samples make it meaningful;
- per-lane utilization = admitted busy time / common wall interval;
- submit rank and admission rank, including maximum FIFO overtake among compatible requests;
- Jain's fairness index over per-request service throughput for the equal-work arm;
- queue depth trajectory if captured.

Streaming cancellation is a separate failure-path experiment. A disconnected request may retain its lane until a later child heartbeat detects the closed downstream connection; do not mix that cleanup interval into ordinary overload percentiles unless cancellation is explicitly the workload under test.

### Cache-persistence extension

After the equal-work curve, add a stateful mix that revisits known session IDs among new sessions. Report whether preserved lane affinity changes queue wait, TTFT or prompt reuse. Keep the scheduler policy unchanged; this arm measures the trade-off between affinity/cache persistence and immediate first-free placement rather than retuning the policy mid-run.

## Gate 3 — matched 0.1.30 layer-split A/B

Use IQ3_S and identical prompt/context/completion/sampling/warm-state inputs for both structures. Keep upstream 0.1.30 conversation parking disabled (`--conversation-cache-mib 0`) in the primary matched A/B unless a separate parking experiment is explicitly declared.

### Independent lanes

Measure:

1. one request on one lane: latency, PP, TTFT, TG;
2. three simultaneous requests on three lanes: per-request latency/PP/TTFT/TG and common-wall aggregate throughput.

### Three-GPU upstream layer-split

Measure:

1. one request spanning three GPUs: latency, PP, TTFT, TG;
2. three requests under the serving behavior the layer-split server actually supports, reporting total workload completion time and per-request latency.

Do not combine these into a single score. The result should show which workload region favors request-level independent lanes and which favors a coupled multi-GPU request.

## One-GPU batching baseline

The current upstream Strata server serializes model generation through a FIFO lock. It does not expose an equivalent one-GPU continuous-batching execution contract. Therefore:

- a one-GPU serial queue can be measured as a queueing baseline;
- it must be labeled serial FIFO serving;
- it must not be presented as continuous batching;
- if upstream later adds a real multi-request batching path, add it as a new matched arm instead of retroactively relabeling the serial data.

## Statistical and run hygiene

- Keep a predetermined repetition count; do not drop slow completed runs without an external failure criterion.
- Record contamination events such as other GPU processes, thermal/power limit changes, OOM, engine restart, or client cancellation.
- Require the supervisor's fixed private/public ports to be free before model load; the 0.1.30 candidate preflights these ports so a stale wrapper cannot satisfy readiness for a new lane.
- Use common synchronized release for concurrency trials.
- Report `n`, mean, SD, min/max, and percentile definitions.
- State when warm repetitions are stateful/non-IID.
- Preserve raw per-request rows; summaries are derived artifacts. `bench/summarize_oversub.py` regenerates the overload percentiles, common-wall throughput, utilization/fairness summaries and FIFO-overtake diagnostic from the request-level CSV.
- Never merge historical 0.1.27 values into a 0.1.30 headline table.

## Promotion outcome

Gate 0 and the complete Gate 1 headline matrix passed on `dcdd46ff37b1baf5172a96389fbdc0c7b51a7dbc`, so 0.1.30 is the promoted recipe/paper-facing generation. Gates 2 and 3 also completed: the exact-queue 3/4/6/9 oversubscription curve and the matched independent-lanes ↔ three-GPU layer-split A/B are both retained. See `docs/strata-0.1.30-promotion-20261001.md` for the results.
