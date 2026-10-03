# Usage — Strata-Lanes 3×GPU recipe

This recipe documents **direct Strata-Lanes serving**.

The public runtime entry point is:

```text
serve/multigpu_server.py
```

The host-specific launch example is:

```text
recipe/launch-3lane.sh.example
```

## 1. Prepare a normal Strata config

First make the chosen model/config work as a normal single-GPU Strata server on each GPU you plan to use.

The current reference host uses:

```text
GPU0  RTX 5070 Ti 16 GB   PCIe 5.0 x8
GPU1  RTX 5070 Ti 16 GB   PCIe 5.0 x4
GPU2  RTX 5070 Ti 16 GB   PCIe 5.0 x8
GPU3  RTX 5060 Ti 16 GB   excluded
```

The recipe assumes one ordinary Strata engine per selected GPU.

## 2. Launch the three-lane supervisor

Copy the example and set at least:

```bash
STRATA_DIR=/path/to/Strata-Lanes
CONFIG=/path/to/working-strata.json
PUBLIC_PORT=18086
BASE_PORT=19086
ARENA_FILE=/dev/shm/strata-lanes.shared

bash recipe/launch-3lane.sh.example
```

Equivalent direct shape:

```bash
python3 serve/multigpu_server.py \
  --config /path/to/working-strata.json \
  --gpus 0,1,2 \
  --host 127.0.0.1 \
  --port 18086 \
  --base-port 19086 \
  --lane-contexts 262144,262144,262144 \
  --kv-budget 786432 \
  --lane-cpu-cores 5,6,5 \
  --lane-pcie-fracs 0.55,0.25,0.55 \
  --lane-kv-residents 32768,32768,32768 \
  --lane-vram-reserve-mibs 1200,1200,1200 \
  --vision-lanes 1 \
  --experimental-conversation-cache-mib 4096 \
  --experimental-conversation-cache-slots 4 \
  --experimental-conversation-cache-min-free-mib 8192 \
  --arena-file /dev/shm/strata-lanes.shared
```

The numeric CPU/PCIe/KV/VRAM values above are **measurements for this host**, not universal defaults.

## 3. Point clients at the supervisor

Use the public supervisor port as the OpenAI-compatible base URL:

```text
http://127.0.0.1:18086/v1
```

For long-lived sessions, pass a stable session identifier every turn. Recommended:

```http
X-Strata-Session-Id: my-chat-123
```

Lanes also accepts `X-Conversation-Id`, `X-Session-Id`, `X-Thread-Id`, or body/metadata fields `conversation_id`, `session_id`, `thread_id`.

Without an explicit identifier, the first user message is used as a best-effort affinity seed. Explicit IDs are preferred for agents and multi-turn chats.

## 4. Conversation parking

The current reference setting is:

```text
4096 MiB / 4 parked slots / 8192 MiB MemAvailable floor per lane
```

Recipe variables:

```bash
CONVERSATION_CACHE_MIB=4096
CONVERSATION_CACHE_SLOTS=4
CONVERSATION_CACHE_MIN_FREE_MIB=8192
```

These become Lanes supervisor options:

```text
--experimental-conversation-cache-mib
--experimental-conversation-cache-slots
--experimental-conversation-cache-min-free-mib
```

and are forwarded to each ordinary upstream Strata engine as:

```text
--conversation-cache-mib
--conversation-cache-slots
--conversation-cache-min-free-mib
```

`slots` means parked conversations **per lane**. It is not GPU count and not queue depth. Large Hermes/agent prompts may hit the MiB budget before all slots fit.

Rollback:

```bash
CONVERSATION_CACHE_MIB=0
```

or directly:

```text
--experimental-conversation-cache-mib 0
```

## 5. Observe the running server

Status:

```bash
curl http://127.0.0.1:18086/__multigpu/status
```

Useful per-lane fields:

```text
alive
routable
busy
affinity_sessions
parked_conversations
parked_bytes
park_evictions
```

Useful response headers:

```text
X-Strata-Lane-Index
X-Strata-Queue-Wait-Ms
X-Strata-Admission-Rank
```

For experiment-grade lease/queue traces, add:

```bash
--bench-trace-jsonl /path/to/trace.jsonl
```

## 6. Vision lane

The reference recipe uses:

```text
--vision-lanes 1
```

The base config must already contain a valid vision configuration. Image requests are restricted to eligible vision lanes; text requests may also use that lane.

## 7. Full implementation contract

For implementation-level semantics and all accepted affinity fields, recovery behavior and observability controls, see the fork documentation:

https://github.com/rhgo1749/Strata-Lanes/blob/main/docs/LANES_USAGE.md
