# Laya 연동 검토

2026-10-10 공식 문서와 v0.4.1 소스를 대조했습니다.
설정·코드 검토이며 새로운 성능·정확도 벤치마크는 수행하지 않았습니다.
Docker Hub 이미지의 설치 버전과 적재한 체크포인트 리비전은 별도 확인해야 합니다.
저장소 문서만으로 이미지 내부 구성을 확정할 수 없습니다.

## 현재 요청 구성

DeciFlow는 `/v1/systemone`에 청크 하나와 `choice` 분류·`score` 긴급도·
`noul` 작업 티켓 필요성 질문 세 개를 보내며
모델과 토큰 예산을 명시합니다. 파일 Batch는 개별 요청을 동시에 전송하며
`/v1/systemone/batch`를 사용하지 않습니다. Jev는 동일한 분류·검증·UI 경로를
사용하되 Laya 전용 옵션은 전송하지 않습니다.

| 옵션 | 공식 동작 | DeciFlow 현황·권고 |
| --- | --- | --- |
| `model` | 체크포인트 지정; 자동 라우팅보다 우선 | `LAYA_MODEL`로 내장 모델 명시; 자동 유형·모델 선택 없음 |
| `max_len` | 요청별 전체 토큰 윈도; 생략하면 기존 설정 사용 | English 512, 나머지 내장 모델 8192 명시; 단순 상향보다 실제 청크 검증 필요 |
| `head_max_len` | 요청별 질문·선택지 렌더링 예산 | `.env`의 `LAYA_HEAD_TOKENS`를 이 JSON 필드로 그대로 전달; 기본 256 |
| `lang`, `lang_guess`, `task` | 언어·워크플로 라우팅 및 해당되는 언어별 추론 동작 | 미전송; 명시적 모델 선택 유지. 범용 정확도 개선 옵션이 아님 |
| `min_confidence` | 답변을 유지하면서 판단 보류 표시; `answer_confidence` 우선, 없으면 `confidence` | 미전송. DeciFlow는 선택 확률 70% 미만 또는 상위 두 확률 차이 10%p 미만을 Uncertain으로 표시; 설명 없는 이중 임계값을 피할 것 |
| `batch_size`, `sort_by_length` | 배치의 추론 크기·패딩 최적화 | 현재 개별 요청에는 미사용; `/v1/systemone` 요청에 추가할 옵션이 아님 |

예산은 **상한**이며 고정 예약량이 아닙니다. 실제 로그 공간은 렌더링된 질문 길이와
시퀀스 부가 토큰에 따라 결정됩니다. 선택지가 많으면 최소 할당량 때문에 실제
질문 길이가 예산을 초과할 수도 있습니다. `max_len - head_max_len`은 정확한
토큰 계산식이 아닙니다. 현재 5개 범주는 다수 선택지 문제를 피하지만 긴 설명이
짧아질 가능성은 남아 있습니다.

`usage.truncated`, `state_tokens_dropped`, `truncated_questions`는 로그 본문의
잘림 정보입니다. 마지막 필드는 지시문이 짧아진 질문이 아니라 **로그가 잘린
질문의 ID**입니다. DeciFlow는 잘린 로그의 판정을 거절하고 원문을 보존합니다.
서버가 선택지 구별 손실을 `usage.options`로 보고하면 `providerResponse`에
보존하며 이제 Uncertain·검토 사유로 표시합니다. `usage.truncated=false`만으로
질문 전체가 보존되었다고 판단할 수 없습니다.

## Laya 호스트에서 관리할 서버 설정

| 설정 | 효과·운영 지침 |
| --- | --- |
| `LAYA_MAX_TOKEN_BUDGET` | 기본 8192; 두 요청 예산의 상한. 초과하면 422. 인코더 용량을 늘리지는 않음 |
| `LAYA_MAX_CONCURRENT` | 기본 16개 요청 수용; 초과하면 503. v0.4.1 추론 워커는 여전히 1개 |
| `LAYA_THREADS` | CPU 연산 스레드 수; 물리 코어 수 이하 권장. CUDA 병렬도 설정이 아님 |
| `LAYA_PRELOAD`, `LAYA_MODELS`, `LAYA_MAX_LOADED` | 시작 시 적재·상주 모델 관리. preload는 적재 모델 수에 맞춰 상주 상한을 늘리므로 기존 3개 모델 preload에 `LAYA_MAX_LOADED=3` 추가 불필요 |
| `LAYA_IDLE_UNLOAD_SECONDS` | 기본 0은 상주 유지; 활성화하면 상주 자원을 줄이지만 다음 요청의 재적재 비용 발생 |
| `LAYA_DEVICE` | 장치 선호 설정. 인증한 `/health`의 실제 장치·모델별 fallback 확인 필요; CUDA 지정만으로 실행 장치를 확정할 수 없음 |
| `LAYA_JEV_STRICT` | DeciFlow는 0 유지: strict 모드는 필수 잘림 정보와 라우팅 정보를 제거 |
| `LAYA_EXTRA_MODELS` | 사용자 체크포인트 등록. 공식 서버는 지원하지만 DeciFlow는 이제 명시적 전체 예산과 함께 등록 이름도 허용 |

이 서버 설정을 DeciFlow의 `.env`에 추가해도 원격 컨테이너가 바뀌지는 않습니다.
DeciFlow의 `LAYA_CONCURRENCY`는 실행별 설정이며 여러 실행·노드의 요청은
서버의 요청 수용 제한을 함께 사용합니다.

## 반영 상태

검토 후 다음을 구현했습니다:

- `usage.options.category` 구별 손실을 `collapsed_options`·Uncertain·Needs review로
  표시하고 UI에 이유를 보여줍니다. 판정 범주와 확률은 그대로 유지합니다.
- `LAYA_MAX_TOKENS`로 실제 `max_len`을 제어합니다. 내장 모델 기본값은 유지하며
  등록한 사용자 모델 이름은 명시적 윈도 설정을 요구합니다.
- 합성 사례 36개로 5개 프로필을 평가하며 오분류 행렬·요청 실패·Uncertain·Certain
  중 정답 수를 집계합니다. 도메인 데이터는 `--cases`로 지정합니다.
  운영 정확도를 입증한 것은 아닙니다.

여전히 보류한 항목: 실제 서비스 토크나이저 리비전으로 지시문·설명 보존을 검증하는
기능, 실제 추론 배치, 학습, 확률 보정. 선택지 구별 손실 정보는 한 종류의 문제만
탐지하며 모든 지시문 잘림을 탐지하지는 않습니다. 이번 변경의 속도·정확도 향상은
실측하지 않았습니다.

## 개선 우선순위

1. **정확도 우선:** 정답 라벨을 붙인 로그 사례를 확장하고 실제 프로필 문구로
   각 체크포인트를 평가합니다. 정상·성능 저하·실패·보안 사례와 시간·PID 변경
   사례를 포함합니다. 공식 문서도 Laya를 범용 zero-shot 판정기보다 특화할
   기반으로 설명합니다. 긴 프롬프트, 질문 유형 변경, 불확실성 임계값 하향만으로
   정확도를 입증할 수 없습니다. [기존 평가](laya-validation.ko.md)를 참고하세요.
2. **질문 보존 검증:** 각 프로필의 지시문·선택지가 실제 체크포인트 토크나이저와
   예산에서 어떻게 렌더링되는지 확인합니다. 선택지 구별 손실 메타데이터가 있으면
   표시하되 모든 설명 잘림을 검출하는 정보는 아니라는 점을 유지합니다.
   로그 본문 잘림과 별도로 검증해야 합니다.
3. **처리량:** 모델·프로필·예산이 같은 대기 청크를 `/v1/systemone/batch`로 묶는
   방식을 실측합니다. 청크별 원본 정보, 중단 동작, Realtime의 최대 대기시간을
   보존해야 합니다. 개별 동시 요청 증가와 GPU 배치는 다릅니다.
   이번 검토에서 배치 구현은 변경하지 않았습니다.
4. **로그 특화 모델:** 검증한 모델이 준비되면 등록한 사용자 체크포인트 이름과
   명시적 예산 지원을 검토합니다. 확률 보정은 별도의 도메인 검증 데이터로
   수행해야 하며 높은 범주 확률이 실측 정확도를 뜻하지는 않습니다.
   사용자 모델 이름 지원은 반영했으며 모델 학습·확률 보정은 수행하지 않았습니다.

## 근거

- [공식 README: 예산·한계](https://github.com/NandhaKishorM/laya#honest-limits)
- [HTTP API: 요청 옵션·제한·장치·동시 요청](https://nandhakishorm.github.io/laya/http-api/)
- [v0.4.1 HTTP 구현](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/serve.py)
- [v0.4.1 Agent: 렌더링·usage](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/agent.py)
- [v0.4.1 Router: 라우팅·preload·배치](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/router.py)
- [토큰 예산 조정 가이드](https://nandhakishorm.github.io/laya/langchain/#7-widening-the-token-budget-for-many-options)
