# Laya 연동

[English](laya-integration.md) | [한국어](laya-integration.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

## 요청 구성

DeciFlow는 로그 청크를 `state`로 담아 `/v1/systemone`에 보내고 분류(`choice`),
긴급도(`score`), 작업 티켓 필요성(`noul`) 세 질문을 평가합니다. Laya·Jev는
[`classifier.py`](../classifier.py)의 요청 생성·결과 검증·UI 동작을 공유합니다.
[요청·결과 JSON](results.ko.md)을 참고하세요.

| 설정 | DeciFlow 동작 |
| --- | --- |
| `LAYA_MODEL` | 내장 모델 또는 서버에 등록한 이름을 명시. 자동 모델 선택 없음 |
| `LAYA_MAX_TOKENS` | max_len으로 전달. 빈 값이면 English 512, Multilingual·Typed-decisions 8192. 사용자 모델은 명시적 값 필요 |
| `LAYA_HEAD_TOKENS` | head_max_len으로 전달. 기본 256이며 양수·전체 윈도 미만 |
| `LAYA_CONCURRENCY` | 실행별 최대 동시 요청 수. 기본 4. 파일 Batch는 개별 요청이며 추론 배치가 아님 |

Jev에는 Jev 모델 이름을 보내고 Laya 전용 토큰 예산 필드는 전달하지 않습니다.
엔진은 명시적으로 선택하며 유료 Jev로 자동 전환하지 않습니다.

## 입력·응답 검증

예산은 고정 예약량이 아닌 상한입니다. 실제 로그 공간은 렌더링된 질문과 시퀀스
오버헤드에 따라 달라지며 `max_len - head_max_len`은 정확한 토큰 계산식이 아닙니다.
질문 예산을 늘리면 로그에 남는 공간이 줄 수 있습니다.

Laya 응답에는 Boolean `usage.truncated`가 필요합니다. 값이 true이거나 필드가
없거나 유효하지 않으면 판정을 거절하고 원본 로그를 보존합니다.
`state_tokens_dropped`·`truncated_questions`가 제공되면 로그 본문(state)의 잘림을
나타내며 지시문 축약 정보는 아닙니다. false만으로 지시문·선택지 설명 전체가
보존되었다고 판단할 수 없습니다.

세 답변이 모두 유효해야 합니다. 분류 확률은 5개 범주 전체를 포함하고 합이 약 1이어야
합니다. 긴급도는 정해진 범례·4개 유효 확률·확률 가중합과 일치하는 점수가 필요합니다.
티켓 필요성은 0~1 확률입니다. 답변 누락·오류는 전체 판정을 실패시킵니다.

성공 판정은 선택 범주 확률 70% 미만, 상위 두 확률 차이 10%p 미만, Laya가 보고한
분류 선택지 구별 손실 중 하나라도 해당하면 Uncertain으로 표시합니다.
원래 판정·확률은 보존합니다. 등록한 사용자 모델은 `routing.model` 일치 확인도
필요합니다. [검토 규칙](usage.ko.md#불확실성과-사람의-검토)을 참고하세요.

## Laya 호스트에서 관리할 서버 설정

| 설정 | 효과·운영 지침 |
| --- | --- |
| `LAYA_MAX_TOKEN_BUDGET` | 기본 8192; 두 요청 예산의 상한. 초과하면 422. 인코더 용량을 늘리지는 않음 |
| `LAYA_MAX_CONCURRENT` | 기본 16개 요청 수용; 초과하면 503. v0.4.1 추론 워커는 1개 |
| `LAYA_THREADS` | CPU 연산 스레드 수; 물리 코어 수 이하 권장. CUDA 병렬도 설정이 아님 |
| `LAYA_PRELOAD`, `LAYA_MODELS`, `LAYA_MAX_LOADED` | 시작 시 적재·상주 모델 관리. preload는 적재 모델 수에 맞춰 상주 상한을 늘리므로 3개 모델 preload에 `LAYA_MAX_LOADED=3` 추가 불필요 |
| `LAYA_IDLE_UNLOAD_SECONDS` | 기본 0은 상주 유지; 활성화하면 상주 자원을 줄이지만 다음 요청의 재적재 비용 발생 |
| `LAYA_DEVICE` | 장치 선호 설정. 인증한 `/health`의 실제 장치·모델별 fallback 확인 필요; CUDA 지정만으로 실행 장치를 확정할 수 없음 |
| `LAYA_JEV_STRICT` | DeciFlow는 0 유지: strict 모드는 필수 잘림 정보와 라우팅 정보를 제거 |
| `LAYA_EXTRA_MODELS` | 사용자 체크포인트 등록. DeciFlow는 명시적 전체 예산과 함께 등록 이름 허용 |

이 서버 설정을 DeciFlow의 `.env`에 추가해도 원격 컨테이너가 바뀌지는 않습니다.
DeciFlow의 `LAYA_CONCURRENCY`는 실행별 설정이며 여러 실행·노드의 요청은
서버의 요청 수용 제한을 함께 사용합니다.

Compose 배포에서는 `docker-compose.yml`의 선택한 Laya 서비스 `environment`에
서버 변수를 설정한 뒤 해당 서비스를 재생성하세요. Laya가 `.env`에서 읽는 값은
`LAYA_API_KEY`처럼 명시적으로 변수 치환한 설정뿐입니다.

## 평가와 한계

[평가 안내](laya-validation.ko.md)에 따라 모델 예측을 정답 로그와 비교하세요.
평가 스크립트는 세 질문을 모두 전송하며 분류 범주 일치·요청 실패·불확실성 수·
오분류 행렬을 기록합니다.

DeciFlow는 모델 학습·확률 보정·네이티브 추론 배치·실제 서비스 토크나이저 기준
지시문 전체 보존 검사를 수행하지 않습니다. 범주 확률과 검토 임계값은 정확도
보장이 아닙니다. Docker Hub 이미지의 설치 Laya 버전·모델 리비전은 실행 중인
서버에서 확인해야 하며 저장소 설정만으로 확정할 수 없습니다.
아래 공식 참고 자료는 Laya v0.4.1 동작을 설명합니다.

## 근거

- [공식 README: 예산·한계](https://github.com/NandhaKishorM/laya#honest-limits)
- [HTTP API: 요청 옵션·제한·장치·동시 요청](https://nandhakishorm.github.io/laya/http-api/)
- [v0.4.1 HTTP 구현](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/serve.py)
- [v0.4.1 Agent: 렌더링·usage](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/agent.py)
- [v0.4.1 Router: 라우팅·preload·배치](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/router.py)
- [토큰 예산 조정 가이드](https://nandhakishorm.github.io/laya/langchain/#7-widening-the-token-budget-for-many-options)
