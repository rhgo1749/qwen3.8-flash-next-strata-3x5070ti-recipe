# Lane-local conversation parking — production and Hermes validation (2026-10-03)

## Scope

This record documents the current reference-host operating contract for upstream Strata conversation parking under the Strata-Lanes independent-lane supervisor.

Current implementation pin:

```text
Strata-Lanes      3ccb7f9c6316ab51a696d621feb0502d083509fa
upstream Strata   99f3dbd0b21d1401b3769e0c0d963913607f380b (0.1.38)
text binary       a1793a6e3f65dc271f8fa1af6148b374aac7398e431b3f94e40010846049a3bd
```

Reference production serving pool:

```text
GPU0  RTX 5070 Ti 16 GB   PCIe 5.0 x8
GPU1  RTX 5070 Ti 16 GB   PCIe 5.0 x4   vision-capable lane
GPU2  RTX 5070 Ti 16 GB   PCIe 5.0 x8
GPU3  RTX 5060 Ti 16 GB   excluded from the production serving pool
```

## Upstream-native engine contract

Conversation snapshots are an upstream Strata feature. Ordinary lane engines use the upstream options directly:

```text
--conversation-cache-mib 4096
--conversation-cache-slots 4
--conversation-cache-min-free-mib 8192
```

The Lanes supervisor exposes bounded per-lane forwarding controls:

```text
--experimental-conversation-cache-mib 4096
--experimental-conversation-cache-slots 4
--experimental-conversation-cache-min-free-mib 8192
```

The supervisor does **not** own a second snapshot format. It owns session/lane affinity and request admission; each ordinary Strata engine owns its lane-local parked snapshots.

`conversation-cache-slots` is the maximum number of parked conversations per lane. It is not the number of GPUs and not request queue depth. The effective working set is jointly limited by slot count and MiB budget.

## Exact matched production-path A/B

The public production path was used:

```text
client -> 127.0.0.1:8087 idle/wake proxy
       -> 127.0.0.1:18087 three-lane supervisor
       -> ordinary lane engine
```

Both A/B arms used the same patched text-engine binary. The only intended retained-state difference was parking OFF versus ON.

Workload: six stable mixed sessions, three turns, deterministic sampling.

| Turn | Parking OFF wall | Parking ON wall | Wall delta | OFF mean E2E | ON mean E2E | E2E delta | Aggregate completion TPS delta |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 cold/wake | 36.185 s | 36.223 s | +0.1% | 33.185 s | 33.228 s | +0.1% | -0.1% |
| 2 returning | 9.686 s | **6.232 s** | **-35.7%** | 6.063 s | **4.333 s** | **-28.5%** | **+55.4%** |
| 3 returning | 9.688 s | **6.571 s** | **-32.2%** | 5.508 s | **4.091 s** | **-25.7%** | **+59.1%** |

Parking ON restored approximately 964–1064 prompt tokens on turn 2 and 1305–1315 on turn 3 for all six sessions. The ON arm ended with exactly two affinity sessions per lane, one parked conversation per lane, about 1.60 GiB total engine-reported parked state, zero evictions and zero queue depth.

Cold/wake behavior did not materially move.

## Hermes eval live-use validation

A follow-up used Hermes itself rather than a direct HTTP harness.

The Hermes `eval` profile was invoked with:

- its normal profile/session machinery;
- provider overridden to its configured local `strata` provider;
- model `qwen3.8-flash-next-strata-iq3-s`;
- named persistent sessions;
- `--pass-session-id`;
- six independent conversations repeatedly alternated and resumed.

Because the Hermes system/tool context is large, returning prompts were roughly **25K tokens**.

Representative healthy revisits:

| Lane | Prompt tokens | Reused | Freshly read | Prompt time |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 25,840 | 25,592 | 248 | 1.253 s |
| 0 | 25,863 | 25,613 | 250 | 1.278 s |
| 1 | 25,882 | 25,618 | 264 | 2.149 s |
| 2 | 25,875 | 25,617 | 258 | 1.275 s |

Initial/no-parking reads of approximately 25.1K tokens were roughly 11.5–11.7 s on the x8 text lanes in the same live-use window.

### Real byte-budget eviction

Large Hermes snapshots made the **4 GiB byte budget** the binding limit before the nominal four-slot count on lane1.

Final observed state:

| Lane | Affinity sessions | Parked conversations | Parked bytes | Evictions |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 3 | 2 | ~1.73 GiB | 0 |
| 1 | 3 | 2 | ~2.86 GiB | **1** |
| 2 | 1 | 1 | ~1.10 GiB | 0 |

The affected revisit after eviction still completed successfully:

```text
prompt tokens   25,865
reused          16,384
freshly read     9,481
prompt time      ~8.00 s
```

Conversation continuity remained intact. This is the intended contract: snapshot residency is an optimization, while the Hermes conversation and Lanes affinity remain the durable routing state. A miss or eviction falls back to partial/full prompt recomputation on the remembered lane.

## Recovery behavior

The robustness gate also validated:

- client disconnect/cancellation cleanup;
- post-eviction recompute;
- live parked-count / parked-bytes / eviction telemetry;
- child-engine death with the Python lane wrapper surviving;
- same-lane affinity retention across child restart;
- returning request triggering synchronous child reload and then recomputing with `cached_tokens=0`.

New sessions continue to require a loaded engine. Wrapper health is not used as a general new-session scheduling signal.

## Host memory

During the Hermes validation window, host `MemAvailable` moved from roughly 52.4 GiB to a minimum around 43.7 GiB, ending around 44.8 GiB. This includes normal runtime/model/cache movement and is **not** parking-only allocation.

Use engine-reported parked bytes as the cleaner parking-state accounting signal. The 8192 MiB physical-RAM floor remains part of admission.

## Operational conclusion

For the reference host, lane-local parking is now enabled in production at:

```text
4096 MiB / 4 slots / 8192 MiB floor per lane
```

The production pool remains three RTX 5070 Ti lanes. The RTX 5060 Ti is intentionally excluded.

The main practical finding from Hermes is that **byte budget can bind before slot count**. Raising `conversation-cache-slots` alone may not increase the effective number of parked large-agent sessions.

Immediate rollback remains:

```text
--conversation-cache-mib 0
```

Cross-lane snapshot migration remains deferred.
