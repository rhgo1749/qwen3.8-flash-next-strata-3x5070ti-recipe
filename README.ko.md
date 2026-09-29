# Qwen3.8-Flash-Next / Strata GPU-per-Lane 병렬 서빙 레시피

[English](README.md) | **한국어** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

이 저장소는 **GPU 한 장당 독립 Strata generation lane 하나**를 두고, 큰 host-RAM expert arena는 lane들이 **물리적으로 한 벌만 공유**하는 서빙 패턴을 설명한다.

실측 기준 시스템은 **RTX 5070 Ti 16 GB ×3 + Qwen3.8-Flash-Next IQ3_XXS**지만, 설계 자체는 3장이나 특정 GPU에 종속되지 않는다. 각 GPU가 lane-local runtime을 담을 수 있고 CPU/RAM/PCIe 여유가 있다면 2장·3장·4장 이상, 혼합 GPU에도 적용할 수 있다.

구현: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)  
정리된 기준 구현 커밋: [`844d6206`](https://github.com/rhgo1749/Strata/commit/844d62064b4327f80eae0f2980ccbd83b04fbe9a)

## 핵심 개념

**요청 하나는 GPU lane 하나가 처리하고, 여러 요청은 서로 다른 GPU에서 동시에 처리한다. 시스템 RAM의 큰 expert weight는 프로세스마다 복제하지 않고 공유한다.**

Tensor parallel이 아니라 request/session parallelism이다.

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

- 큰 host expert arena의 물리 RAM 페이지;
- host memory bandwidth와 CPU 자원;
- PCIe/root-complex bandwidth;
- runtime storage.

### lane마다 독립인 것

- CUDA context/stream;
- GPU hot-expert cache;
- GPU-resident KV;
- host-KV/session state;
- generation/decode loop.

정상 production 경로에서는 GPU 사이에 token-by-token 동기화를 요구하지 않는다.

## 이 구조의 장점과 대가

- 느린 GPU가 다른 GPU의 매 token 진행을 끌어내리지 않는다.
- 서로 다른 성능의 GPU도 독립 request slot으로 쓰기 쉽다.
- 큰 RAM expert weight를 lane 수만큼 물리 복제하지 않는다.
- lane별 context/KV/CPU/PCIe/clock/undervolt tuning이 가능하다.
- NVLink가 없어도 정상 decode 경로가 성립한다.

대신 **요청 하나는 보통 GPU 하나만 쓴다.** 요청이 하나뿐이면 다른 GPU lane은 놀 수 있다. 따라서 이 구조는 single-request 최대 속도보다 **동시 요청 처리량과 격리성**을 우선한다.

## 권장 사양 가이드

이 포크는 특정 GPU 3장 구성에 하드코딩되어 있지 않다. 가장 중요한 기준은 다음과 같다.

> **선택한 GPU 각각이 먼저 single-GPU Strata lane 하나를 정상 구동할 수 있어야 하고, 호스트는 그 lane들을 동시에 돌릴 CPU / RAM / PCIe 여유가 있어야 한다.**

| 항목 | 실용적인 출발점 | multi-lane 권장 | 검증된 기준 시스템 |
| --- | --- | --- | --- |
| OS | Linux | 최신 64-bit Linux | Ubuntu Linux |
| GPU 수 | NVIDIA GPU 2장 | 2–4장 | 3장 |
| GPU별 VRAM | 선택한 single-GPU Strata 설정을 수용할 것. Upstream Strata의 지원 모델은 12 GB부터 시작 | hot-expert cache / resident KV 여유를 위해 **GPU당 16 GB+** 권장 | RTX 5070 Ti 16 GB ×3 |
| 시스템 RAM | shared expert arena 1벌 + **모든 lane의 host-KV** + OS/runtime 여유 | 실제 quant/context 계획으로 계산. **이 3-lane IQ3_XXS 262K ×3 레시피는 128 GB를 검증된 권장값으로 사용** | 128 GB |
| CPU | 현재 auto partition 기준 lane당 최소 2 physical cores | 가능하면 **활성 lane당 4–6 physical cores**부터 시작 | Ryzen 9 9950X3D 16C/32T, 5 / 6 / 5 |
| PCIe | 각 GPU에 안정적인 실사용 링크 | 넓은 링크를 우선하되 비대칭 topology는 실측으로 조정 | Gen5 x8 / x4 / x8 |
| Storage | SSD | NVMe SSD | NVMe |
| NVLink | 불필요 | 불필요 | 없음 |
| PSU / 냉각 | CPU와 모든 GPU의 동시 부하를 감당할 것 | 일반적인 전력/온도 여유를 두고 구성 | 호스트별 상이 |

이 값들은 **범용 최소사양이 아니라 가이드**다. 더 작은 quant, 적은 lane, 짧은 context는 RAM 요구량을 낮출 수 있고, 반대로 lane/context/model이 커지면 더 필요할 수 있다.

RAM은 대략 다음 식으로 생각하면 된다.

```text
필요 host RAM ≈
    shared expert arena 1벌
  + lane 0 host-KV
  + lane 1 host-KV
  + ...
  + OS / server / filesystem-cache 여유
```

**GPU 수만큼 expert arena를 곱하면 안 된다.** 이 포크가 바로 그 큰 expert arena를 물리 RAM에서 공유하기 때문이다.

범용 하드웨어 sizing과 bring-up 체크리스트는 구현 포크의 [`docs/multigpu-hardware-guide.md`](https://github.com/rhgo1749/Strata/blob/main/docs/multigpu-hardware-guide.md)에 정리했다.

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

이 값들은 **다른 PC의 기본값이 아니다.** 기준 시스템에서 실측 후 선택한 값이다.

## 정본 성능 수치

이 레시피의 공개 성능 정본은 **2차 언더볼팅 상태**다. 2차 이전 throughput 수치는 더 이상 대표 성능으로 사용하지 않는다.

- warm lane-local TG: **78.8 / 78.4 / 80.1 tok/s**;
- lane-sum TG: **237.3 tok/s**;
- no-reuse PP spot check: **1,529.7 / 1,421.6 / 1,536.9 tok/s**;
- 위 독립 PP 관측 3개의 평균: 약 **1,496 tok/s/lane**;
- 약 **141K–145K token**짜리 full-window 요청 3개를 동시에 넣어 context overflow / CUDA OOM / lane death 없이 완료했다.

> **237.3 tok/s는 각 lane의 engine-reported TG를 더한 lane-sum이며 clean wall-clock aggregate가 아니다.**

PP 3개 역시 한 번의 동기화된 prefill 구간이 아니라 각 lane의 독립 spot check이므로 합산 aggregate PP로 홍보하지 않는다.

141K–145K ×3 장문 테스트는 **262K ×3 capacity와 client compatibility 검증**으로 남기고, 정본 throughput benchmark와는 구분한다.

자세한 데이터와 보고 규칙은 [`RESULTS.md`](RESULTS.md), [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md)를 보면 된다.

## 내 PC에 적용하는 순서

1. 사용할 GPU 각각에서 먼저 single-GPU Strata 설정을 정상 동작시킨다.
2. 각 GPU의 VRAM, 실제 negotiated PCIe link, 상대 성능을 확인한다.
3. 선택한 GPU 각각이 lane 하나의 VRAM 요구량을 감당하는지 확인한다.
4. shared expert arena를 올린 뒤 시스템 RAM 여유를 확인한다.
5. lane들의 CPU worker가 같은 physical core를 겹쳐 쓰지 않게 나눈다.
6. context / resident-KV / topology 값은 보수적으로 시작하고 각 lane 단독부터 측정한다.
7. 2개 동시 → 전체 동시 순으로 확장한다.
8. 짧은 warm prompt뿐 아니라 긴 cold prompt도 검증한다.
9. streaming, tool call, cancellation, lane recovery까지 통과시킨 뒤 production 값으로 승격한다.

기준 3-lane 실행 예시는 [`recipe/launch-3lane.sh.example`](recipe/launch-3lane.sh.example)에 있다.

## 구현 저장소와 레시피 저장소의 역할

`rhgo1749/Strata` 포크에는 공유 arena, multi-lane supervisor, request router, 테스트, 범용 architecture/roadmap만 둔다.

**특정 PC의 GPU 구성, CPU split, PCIe tuning, KV 값, 벤치마크 결과는 이 레시피 저장소가 담당한다.**

관계와 구현 위치는 [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md)에 정리돼 있다.

## 현재 production 경로에서 하지 않는 것

- tensor parallel;
- pipeline parallel;
- 필수 cross-GPU expert ownership;
- GPU 간 KV migration;
- dynamic shared KV allocator;
- single-process multi-GPU decode.

이들은 자동 업그레이드 경로가 아니라, 실제 end-to-end 측정으로 현재 lane 구조를 이길 때만 승격할 challenger다.

## 문서 지도

- [`RESULTS.md`](RESULTS.md) — 기준 시스템 실측 결과와 보고 규칙
- [`docs/undervolt-v2-20260929.md`](docs/undervolt-v2-20260929.md) — 정본 2차 언더볼팅 GPU 튜닝 및 PP/TG 데이터
- [`docs/reference-host-validation-20260929.md`](docs/reference-host-validation-20260929.md) — 262K ×3 장문/서빙 검증 기록
- [`docs/fork-and-implementation.md`](docs/fork-and-implementation.md) — 포크와 레시피의 역할 분리
- [`bench/README.md`](bench/README.md) — 측정 규칙

## 관련 프로젝트

- Upstream Strata: [`Niko1221/Strata`](https://github.com/Niko1221/Strata)
- Multi-lane 구현 포크: [`rhgo1749/Strata`](https://github.com/rhgo1749/Strata)
- ExLlamaV3 companion recipe: [`rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe`](https://github.com/rhgo1749/qwen3.8-flash-next-exllamav3-3x5070ti-recipe)

## License

이 저장소의 recipe 문서와 helper material은 MIT License를 따른다. Strata와 모델 파일은 각각의 원 라이선스를 따른다.
