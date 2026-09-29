# Qwen3.8-Flash-Next / Strata GPU-per-Lane 병렬 서빙 레시피

[English](README.md) | **한국어** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

이 저장소는 **GPU 한 장당 독립 Strata generation lane 하나**를 두고, 큰 host-RAM expert arena는 lane들이 **물리적으로 한 벌만 공유**하는 서빙 패턴을 설명한다.

실측 기준 시스템은 **RTX 5070 Ti 16 GB ×3 + Qwen3.8-Flash-Next IQ3_XXS**다. 구조는 tensor parallel이 아니라 request/session parallelism이다. 요청 하나는 보통 GPU lane 하나가 처리하고, 여러 요청을 서로 다른 GPU lane에서 동시에 처리한다.

구현: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)  
**현재 승격된 구현 pin:** [`9dda206`](https://github.com/rhgo1749/Strata/commit/9dda206874387b20cac20837a1452f115a8f9f93)  
**현재 승격 엔진:** Strata **0.1.22**

## 핵심 개념

**요청 하나는 GPU lane 하나가 처리하고, 여러 요청은 서로 다른 GPU에서 동시에 처리한다. 시스템 RAM의 큰 expert weight는 프로세스마다 복제하지 않고 공유한다.**

```mermaid
flowchart TB
    C[클라이언트 / 에이전트 / OpenAI-compatible API] --> D[요청 디스패처]
    D -->|요청 A| G0[GPU 0 lane]
    D -->|요청 B| G1[GPU 1 lane]
    D -->|요청 C| G2[GPU 2 lane]
    E[공유 host expert arena] --> G0
    E --> G1
    E --> G2
```

### 공유되는 것

- host expert arena의 물리 RAM 페이지 1벌;
- host memory bandwidth와 CPU 자원;
- PCIe/root-complex bandwidth;
- runtime storage.

### lane마다 독립인 것

- CUDA context/stream;
- GPU hot-expert cache;
- GPU-resident KV;
- host-KV/session state;
- speculative/MTP state;
- generation/decode loop.

정상 production 경로에서는 GPU 사이에 token-by-token 동기화를 요구하지 않는다.

## 이 구조를 유지하는 이유

| 특성 | 실제 효과 |
| --- | --- |
| 느린 GPU는 자기 lane에 격리 | 느린 카드가 다른 lane의 매 token 진행을 끌어내리지 않음 |
| 혼합 GPU 사용 가능 | 서로 다른 성능의 GPU도 독립 request slot로 활용 가능 |
| host expert 공유 | 가장 큰 RAM 할당을 lane 수만큼 복제하지 않음 |
| failure isolation | 한 lane 장애가 모든 token step의 공통 장애영역이 되지 않음 |
| lane별 tuning 가능 | context/KV/CPU/PCIe/clock/undervolt를 lane별로 조정 가능 |
| NVLink 불필요 | 정상 decode가 필수 GPU-to-GPU 전송에 의존하지 않음 |

대신 **요청 하나는 보통 GPU 하나만 쓴다.** 따라서 이 구조는 single-request 최대속도보다 **동시 요청 처리량과 격리성**을 우선한다.

## 기준 시스템

```text
CPU                 Ryzen 9 9950X3D, 16C/32T
RAM                 128 GB DDR5
GPUs                RTX 5070 Ti 16 GB ×3
PCIe                Gen5 x8 / x4 / x8
model               Qwen3.8-Flash-Next IQ3_XXS
contexts            262144 / 262144 / 262144
host-KV guard       786432
resident KV         32768 / 32768 / 32768
CPU cores           5 / 6 / 5
pcie-frac           0.55 / 0.25 / 0.55
shared expert arena ~39.97 GiB
GPU V/F plateau     2300 MHz @ >=875 mV
VRAM offset         +2500
```

이 값들은 **다른 PC의 기본값이 아니라 기준 시스템에서 실측해 선택한 값**이다.

RAM은 대략 다음 식으로 잡는다.

```text
필요 host RAM ≈
    shared expert arena 1벌
  + 모든 lane의 host-KV
  + OS / server / filesystem-cache 여유
```

expert arena는 GPU 수만큼 곱하지 않는다. 이 포크가 바로 그 큰 arena를 물리 RAM에서 공유한다.

## 현재 승격 성능 — Strata 0.1.22

현재 레시피 baseline은 fork commit `9dda206`, engine 0.1.22다. 기존 3-lane 실행 명령과 설정 계약은 그대로 호환됐고 별도 migration flag는 필요 없었다.

### clean warm 3동시 wall aggregate

동일한 짧은 요청 3개를 각 lane에 보내고 동일 prefix가 warm된 상태에서 유지한 두 라운드는 다음과 같다.

- **227.9 tok/s** wall aggregate — 384 completion tokens / 1.685 s
- **226.5 tok/s** wall aggregate — 384 completion tokens / 1.695 s

따라서 현재 headline multi-lane 수치는 **226.5–227.9 tok/s clean warm wall aggregate**이며 중간값은 약 **227.2 tok/s**다.

예전 **237.3 tok/s**는 각 lane의 engine-reported TG를 더한 **lane-sum**이었다. 유효한 역사 수치지만 clean wall aggregate가 아니므로 이제 대표 concurrent-serving 수치는 0.1.22의 226.5–227.9 tok/s를 사용한다.

### 15K no-reuse prompt-processing spot check

262K lane 하나에서 **15,064-token no-reuse prompt**를 처리한 결과는 **2,492.2 tok/s**였다.

이 값은 같은 호스트에서 0.1.22 promotion을 검증한 소프트웨어 버전 spot check다. 모든 장문 prompt를 대표하는 보편 PP 수치로 해석하면 안 된다. 기존 45K–65K PP 관측은 prompt 길이와 benchmark generation이 달라 역사 데이터로 남긴다.

### 0.1.21 대비

직전 0.1.21 integration 검증값은:

- warm 3-request wall aggregate: **198.2 tok/s**
- ~15K PP spot check: **1,609.9 tok/s**

이번 0.1.22 promotion run에서는 각각 약:

- **+14.6%** warm wall aggregate
- **+54.8%** retained ~15K PP

를 기록했다. 이 비율은 해당 promotion run끼리의 비교이며 모든 workload에 그대로 적용되는 보편 speedup 주장은 아니다.

자세한 기록: [`docs/strata-0.1.22-promotion-20260929.md`](docs/strata-0.1.22-promotion-20260929.md)

## upstream layer-split challenger

같은 `9dda206` 바이너리에서 upstream 3-GPU layer-split도 262K로 정상 기동했다.

- 짧은 single-request decode: **80.6 tok/s**
- 15,064-token no-reuse PP: **1,142.3 tok/s**

같은 15K PP probe에서 request-per-lane A는 약 **2.18×**의 PP를 보였고, layer-split B는 single-request decode에서 우위를 유지했다.

따라서 architecture promotion 판단은 그대로다. **동시 agent serving의 production baseline은 independent request lanes**, layer-split은 single-request 중심 workload를 위한 challenger로 남긴다.

## 262K ×3 장문 검증

실제 software-review prompt 3개를 모든 lane이 262K context로 설정된 상태에서 동시에 실행했다.

- 141,578 input / 992 output tokens
- 144,875 input / 1,295 output tokens
- 144,777 input / 871 output tokens

세 요청 모두 context overflow, CUDA OOM, API failure, lane death 없이 완료했다. 이 결과는 **262K ×3 capacity/client compatibility 검증**이며 throughput headline과는 분리한다.

## IQ3_S quality-oriented challenger

같은 262K ×3 정책으로 IQ3_S도 검증되어 있다.

| 측정 | IQ3_S 결과 |
| --- | ---: |
| Shared host expert arena | **46.84 GiB** |
| GPU당 hot-expert cache | **4548 slots / 8.67 GiB** |
| Warm short-decode TG | **60.5 / 63.8 / 59.1 tok/s** |
| Engine-reported lane-sum | **183.4 tok/s** |
| Concurrent ~30K no-reuse PP | **1,553.7 / 1,323.9 / 1,545.1 tok/s** |

IQ3_S는 quality-oriented challenger이며 current performance baseline은 계속 IQ3_XXS다.

## 내 PC에 적용하는 순서

1. 사용할 GPU 각각에서 single-GPU Strata를 먼저 정상화한다.
2. 각 GPU의 VRAM, negotiated PCIe link, 상대 성능을 확인한다.
3. 선택한 GPU 각각이 lane 하나의 VRAM 요구량을 감당하는지 확인한다.
4. shared expert arena를 올린 뒤 시스템 RAM 여유를 확인한다.
5. lane worker들이 같은 physical core를 겹쳐 쓰지 않게 나눈다.
6. context / resident-KV / topology 값은 보수적으로 시작하고 lane 단독부터 측정한다.
7. 2개 동시 → 전체 동시 순으로 확장한다.
8. 짧은 warm prompt와 긴 cold/no-reuse prompt를 모두 검증한다.
9. streaming, tool call, cancellation, lane recovery까지 통과시킨 뒤 production으로 승격한다.

기준 실행 예시는 [`recipe/launch-3lane.sh.example`](recipe/launch-3lane.sh.example)에 있다.

## 문서 지도

- [`RESULTS.md`](RESULTS.md) — 현재/역사 기준 시스템 실측 결과와 reporting rule
- [`docs/strata-0.1.22-promotion-20260929.md`](docs/strata-0.1.22-promotion-20260929.md) — 현재 0.1.22 promotion 기록
- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — 과거 2차 언더볼팅 lane-local 데이터
- [`docs/iq3-s-3lane-benchmark-20260929.md`](docs/iq3-s-3lane-benchmark-20260929.md) — IQ3_S challenger benchmark
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — 262K ×3 장문/서빙 검증
- [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md) — 포크와 레시피의 역할 분리
- [`bench/README.md`](bench/README.md) — benchmark/reporting contract

## 관련 프로젝트

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane 구현 포크: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

이 저장소의 recipe 문서와 helper material은 MIT License를 따른다. Strata와 모델 파일은 각각의 원 라이선스를 따른다.
