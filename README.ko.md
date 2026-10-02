# Qwen3.8-Flash-Next / Strata GPU-per-Lane 병렬 서빙 레시피

[English](README.md) | **한국어** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

이 저장소는 **GPU 한 장당 독립 Strata generation lane 하나**를 두고, lane 프로세스들이 큰 host-RAM expert arena는 **물리적으로 한 벌만 공유**하는 서빙 구조를 정리한다.

**Upstream:** Strata는 [Niko1221](https://github.com/Niko1221)가 만들고 유지하는 inference engine이며, upstream은 [`Niko1221/Strata`](https://github.com/Niko1221/Strata)이다. 이 저장소는 그 엔진 위에 추가한 multi-lane serving과 shared-arena 확장을 정리한다.

## 현재 상태

- 구현 포크: [`rhgo1749/Strata-Lanes`](https://github.com/rhgo1749/Strata-Lanes)
- **현재 운용 Strata pin:** [`475e076`](https://github.com/rhgo1749/Strata-Lanes/commit/475e0766e8b41e17c978a6765ee0587f198790a3)
- 엔진 기준: Strata **0.1.31** (upstream `9259cad`); 승격 기록: [`docs/strata-0.1.31-promotion-20261001.md`](docs/strata-0.1.31-promotion-20261001.md)
- 기준 서버 현재 production quant: **Qwen3.8-Flash-Next GSQ-RCO IQ3_S**
`main`은 현재 운용 레시피를 따라간다. 유지 중인 실측 결과와 버전 경계는 [`RESULTS.md`](RESULTS.md)에 정리한다. 더 오래된 스냅샷은 움직이는 `main`에 중복 보관하지 않고 Git history와 별도 브랜치에서 확인할 수 있다.

## 핵심 구조

**활성 요청 하나는 GPU lane 하나가 처리하고, 여러 요청은 서로 다른 GPU에서 동시에 처리한다. 시스템 RAM의 큰 expert weight는 프로세스마다 복제하지 않고 공유한다.**

```mermaid
flowchart TB
    C[클라이언트 / 에이전트 / OpenAI-compatible API] --> D[세션 인지 디스패처]
    D -->|세션/요청 A| G0[GPU lane A]
    D -->|세션/요청 B| G1[GPU lane B]
    D -->|세션/요청 C| G2[GPU lane C]
    E[공유 host expert arena] --> G0
    E --> G1
    E --> G2
```

CUDA 상태, GPU hot-expert cache, GPU-resident KV, host-KV/session 상태, speculative/MTP 상태, generation loop는 lane별로 독립이다. 정상 production 경로에는 필수 token-by-token cross-GPU 동기화가 없고 NVLink도 필요하지 않다.

## 세션 인지 스케줄러

초기 multi-lane supervisor는 request-level free-lane/round-robin 방식이었다. 독립 요청 throughput 실험에서는 문제가 없지만, KV/prompt cache가 lane-local인 상황에서 긴 대화의 다음 턴이 다른 GPU로 이동하면 전체 또는 대규모 prompt re-prefill을 다시 치를 수 있다.

현재 `main`은 **엄격한 session affinity + balanced-additive 새 세션 배치**를 사용한다. 우선순위는 명시적으로 다음과 같다.

1. 먼저 살아 있고 capability 조건(예: vision)을 만족하는 lane만 후보로 남긴다.
2. 이미 알려진 세션이면 그 세션이 기억하고 있는 lane을 사용한다. 그 lane이 busy면 **다른 GPU로 도망가지 않고 그 lane 뒤에서 기다린다.**
3. 완전히 새로운 세션은 이미 busy인 lane에 끼어들지 않는다. 모든 후보가 busy면 request/stream 하나가 완전히 끝나 lane을 release할 때까지 기다린다.
4. 사용 가능한 idle lane 중에서는 먼저 **기억된 affinity session 수가 가장 적은 lane**을 선호해 장기 cache state가 한 lane을 영구적인 attractor로 만들지 않게 한다.
5. session 수가 같은 후보끼리는 **추정 new-prefill bytes + 마지막 완료 요청의 retained bytes** 합을 최소화한다. 이는 routing-state proxy이지 engine-truth compute cost 주장이 아니다.
6. live-state recency와 rotating candidate order는 동률 해소용으로 남는다. `safe-affinity-live-state-v1`은 명시적인 rollback 정책으로 유지한다.

대기 중인 새 세션은 **compatible FIFO ticket**으로 줄을 선다. 먼저 기다린 compatible 요청이 새로 풀린 lane을 먼저 받고, vision 같은 capability 제약 요청은 자신이 쓸 수 없는 다른 lane까지 막지 않는다. 기존 세션 continuation이 자기 lane을 기다리는 동안에는 그 lane을 예약하므로 `notify_all()` wake-up race 때문에 새 세션이 cache-rich lane을 가로채지 못한다. 실제 빈 live state는 affinity key 유무가 아니라 `live_request_bytes == 0`으로 판정한다.

이 정책에는 **GPU 번호, GPU 모델, PCIe 폭을 하드코딩하지 않는다.** `busy` 수명은 request/stream 단위이고, affinity 수명은 session 단위다. 하나의 engine에 여러 session key가 기억될 수 있어, 중간에 다른 요청이 그 engine을 사용하더라도 예전 세션이 같은 engine으로 돌아와 Strata의 per-engine prompt-cache checkpoint를 다시 활용할 수 있다.

실 production smoke에서는 A → B → C → D → A 순서로 검증했다. A/B/C가 각각 빈 lane을 채운 뒤 D는 live state가 가장 작은 lane을 사용했고, 마지막 A는 다시 원래 lane으로 돌아왔다. 별도의 overload smoke에서는 3개 요청으로 세 lane을 모두 점유한 상태에서 4개 요청을 추가해 `peak_queue_depth=4`를 관측했고, 7개 요청 모두 성공한 뒤 `queue_depth=0`, 모든 lane idle로 정상 복귀했다.

이 스케줄러는 **현재 lane-local KV 구조를 안전하게 운용하기 위한 serving hardening**이며, 최종 최적 스케줄러라고 주장하지 않는다. cache-aware global scheduling, migration/transfer cost, overload queueing, 더 정교한 cost model은 로드맵 과제로 남긴다.

## 기준 시스템

```text
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
GPU lanes           RTX 5070 Ti 16 GB ×3
PCIe                x8 / x4 / x8
contexts            262144 / 262144 / 262144
resident KV         32768 / 32768 / 32768
VRAM reserve MiB    1200 / 1200 / 1200
physical CPU cores  5 / 6 / 5
production vision   선택된 lane 1개
current quant       IQ3_S
```

이 값들은 **다른 PC의 기본값이 아니라 기준 시스템의 실측값**이다.

### mixed vision/text lane의 VRAM reserve 주의

vision 설정이 들어 있는 base config에서 text-only lane을 파생할 때 `--vision`과 encoder 설정은 제거해도 되지만, VRAM 안전 여유까지 함께 사라지게 두면 안 된다. 기준 RTX 5070 Ti 16GB / IQ3_S / 262K context / resident-KV 32768 환경에서 non-vision lane이 700 MiB reserve로 돌아가자 최종 free VRAM이 약 **93 MiB**만 남았고 실제 `verify: instantiate: out of memory`가 발생했다.

현재 production은 `--lane-vram-reserve-mibs 1200,1200,1200`을 명시한다. 재측정에서 GPU0/GPU1/GPU2의 최종 free VRAM은 각각 **593 / 592 / 593 MiB**였고, 새 startup 이후 세 lane 동시 public 요청이 모두 HTTP 200으로 끝났으며 OOM/illegal-memory/engine-stop은 0건이었다. 이 1200 MiB 값도 **기준 호스트의 안전값**이지 모든 GPU의 보편 기본값은 아니다. 이 문제는 vision encoder가 text-only GPU의 VRAM을 사용해서 생긴 것이 아니라, mixed-capability lane을 만들면서 base config의 reserve가 text-only lane에서 빠진 데서 드러났다.

host RAM은 대략 다음처럼 잡는다.

```text
필요 host RAM ≈ shared expert arena 1벌 + 모든 lane의 host-KV + OS/runtime 여유
```

## 버전별 증거 경계

움직이는 `main`에는 현재 **0.1.31 운용 baseline**과 바로 전 **0.1.30 benchmark generation**만 유지한다. 측정값은 원래 엔진 버전을 그대로 유지하며, 더 오래된 세대의 기록을 현재 결과처럼 재라벨링하지 않는다.

참고:

- [`RESULTS.md`](RESULTS.md) — 현재 요약과 유지 중인 benchmark evidence
- [`docs/strata-0.1.31-promotion-20261001.md`](docs/strata-0.1.31-promotion-20261001.md) — 현재 운용 parity 승격 기록
- [`docs/strata-0.1.30-promotion-20261001.md`](docs/strata-0.1.30-promotion-20261001.md) — 유지 중인 전체 benchmark generation
- [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md) — upstream/fork/recipe 역할 경계

## 다른 PC에 적용할 때

1. 사용할 GPU 각각에서 single-GPU Strata를 먼저 정상화한다.
2. VRAM, negotiated PCIe link, RAM 여유, CPU topology를 확인한다.
3. lane worker pool이 겹치지 않도록 physical CPU core를 나눈다.
4. 보수적인 context/resident-KV 값으로 시작해 각 lane을 단독 검증한다.
5. 동시 lane, cold/no-reuse 장문, streaming/cancellation, lane recovery, **multi-turn session affinity**를 검증한다.
6. 기준 서버의 tuning 값은 portable default가 아니라 측정값으로 취급한다.

## 관련 프로젝트

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane 구현 포크: [`rhgo1749/Strata-Lanes`](https://github.com/rhgo1749/Strata-Lanes)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## 라이선스

이 저장소의 recipe 문서와 helper material은 MIT 라이선스다. Strata와 모델 파일은 각각의 원래 라이선스를 따른다.