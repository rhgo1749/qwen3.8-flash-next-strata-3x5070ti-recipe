#!/usr/bin/env python3
"""Phase-1 live correctness smoke for the promoted Strata multi-GPU service.

Checks text routing, vision-capability routing, multi-turn affinity/cache reuse,
malformed-input handling, client-disconnect cleanup, and immediate recovery.
The output contains only statuses/metrics, never prompt or image contents.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import struct
import time
from pathlib import Path
from typing import Any


def request(host: str, port: int, body: dict[str, Any], session_id: str, timeout: float = 300.0):
    raw = json.dumps(body, separators=(",", ":")).encode()
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    conn.request(
        "POST",
        "/v1/chat/completions",
        body=raw,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
            "X-Strata-Session-Id": session_id,
        },
    )
    resp = conn.getresponse()
    data = resp.read()
    headers = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    parsed = None
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        pass
    return resp.status, headers, parsed, data


def get_json(host: str, port: int, path: str, timeout: float = 5.0) -> dict[str, Any]:
    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    conn.request("GET", path)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"GET {path} returned {resp.status}: {raw[:200]!r}")
    return json.loads(raw)


def valid_bmp_data_uri(width: int = 64, height: int = 64) -> str:
    row = ((width * 3 + 3) // 4) * 4
    pixels = bytearray()
    for _y in range(height):
        for _x in range(width):
            pixels += bytes((0, 0, 255))
        pixels += b"\0" * (row - width * 3)
    size = 54 + len(pixels)
    header = b"BM" + struct.pack("<IHHI", size, 0, 0, 54)
    dib = struct.pack("<IIIHHIIIIII", 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    return "data:image/bmp;base64," + base64.b64encode(header + dib + pixels).decode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--public-port", type=int, default=8087)
    ap.add_argument("--backend-port", type=int, default=18087)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    result: dict[str, Any] = {
        "schema": 1,
        "kind": "phase1_correctness_smoke",
        "created_unix_ns": time.time_ns(),
    }

    status = get_json(args.host, args.backend_port, "/__multigpu/status")
    vision_lanes = [int(x["index"]) for x in status.get("lanes", []) if x.get("vision")]
    result["vision_lanes"] = vision_lanes

    code, headers, body, _ = request(
        args.host,
        args.public_port,
        {"messages": [{"role": "user", "content": "Reply OK."}], "max_tokens": 1, "temperature": 0, "stream": False},
        "phase1-smoke-text",
    )
    text_lane = int(headers["x-strata-lane-index"])
    result["text"] = {"status": code, "lane": text_lane}
    if code != 200:
        raise RuntimeError(f"text smoke failed: {code} {body!r}")

    image_uri = valid_bmp_data_uri()
    code, headers, body, _ = request(
        args.host,
        args.public_port,
        {
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_uri}},
                    {"type": "text", "text": "What color dominates this image? Answer one word."},
                ],
            }],
            "max_tokens": 4,
            "temperature": 0,
            "stream": False,
        },
        "phase1-smoke-vision",
    )
    vision_lane = int(headers["x-strata-lane-index"])
    result["vision"] = {"status": code, "lane": vision_lane}
    if code != 200 or vision_lane not in vision_lanes:
        raise RuntimeError(f"vision smoke failed: status={code} lane={vision_lane} eligible={vision_lanes}")

    sid = "phase1-smoke-multiturn"
    first_messages = [{"role": "user", "content": "Remember the word cobalt. Reply OK."}]
    code1, h1, b1, _ = request(
        args.host,
        args.public_port,
        {"messages": first_messages, "max_tokens": 8, "temperature": 0, "stream": False},
        sid,
    )
    second_messages = first_messages + [
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": "What word did I ask you to remember? Reply with only that word."},
    ]
    code2, h2, b2, _ = request(
        args.host,
        args.public_port,
        {"messages": second_messages, "max_tokens": 8, "temperature": 0, "stream": False},
        sid,
    )
    lane1 = int(h1["x-strata-lane-index"])
    lane2 = int(h2["x-strata-lane-index"])
    cache_n = int(((b2 or {}).get("timings") or {}).get("cache_n") or 0)
    result["multiturn"] = {
        "turn1_status": code1,
        "turn2_status": code2,
        "turn1_lane": lane1,
        "turn2_lane": lane2,
        "turn2_cache_n": cache_n,
    }
    if code1 != 200 or code2 != 200 or lane1 != lane2 or cache_n <= 0:
        raise RuntimeError(f"multi-turn smoke failed: {result['multiturn']}")

    malformed = b'{"messages":['
    conn = http.client.HTTPConnection(args.host, args.public_port, timeout=60)
    conn.request(
        "POST",
        "/v1/chat/completions",
        body=malformed,
        headers={"Content-Type": "application/json", "Content-Length": str(len(malformed))},
    )
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    result["malformed"] = {"status": resp.status}
    if resp.status != 400:
        raise RuntimeError(f"malformed-input smoke failed: {resp.status} {raw[:200]!r}")

    stream_body = json.dumps({
        "messages": [{"role": "user", "content": "Count upward slowly and keep going."}],
        "max_tokens": 512,
        "temperature": 0,
        "stream": True,
    }).encode()
    conn = http.client.HTTPConnection(args.host, args.public_port, timeout=120)
    conn.request(
        "POST",
        "/v1/chat/completions",
        body=stream_body,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(stream_body)),
            "X-Strata-Session-Id": "phase1-smoke-disconnect",
        },
    )
    resp = conn.getresponse()
    disconnect_lane = int(resp.getheader("X-Strata-Lane-Index"))
    first_line = resp.readline()
    conn.close()
    if resp.status != 200 or not first_line.startswith(b"data:"):
        raise RuntimeError(f"disconnect setup failed: status={resp.status} first={first_line[:100]!r}")

    cleanup_polls = None
    for poll in range(1, 81):
        state = get_json(args.host, args.backend_port, "/__multigpu/status")
        if all(not lane.get("busy") for lane in state.get("lanes", [])):
            cleanup_polls = poll
            break
        time.sleep(0.25)
    result["disconnect"] = {
        "start_status": resp.status,
        "lane": disconnect_lane,
        "cleanup_polls_250ms": cleanup_polls,
    }
    if cleanup_polls is None:
        raise RuntimeError("client disconnect did not release all lane leases")

    code, headers, body, _ = request(
        args.host,
        args.public_port,
        {"messages": [{"role": "user", "content": "Reply OK."}], "max_tokens": 1, "temperature": 0, "stream": False},
        "phase1-smoke-recovery",
    )
    result["recovery"] = {"status": code, "lane": int(headers["x-strata-lane-index"])}
    if code != 200:
        raise RuntimeError(f"post-disconnect recovery failed: {code} {body!r}")

    result["status"] = "pass"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
