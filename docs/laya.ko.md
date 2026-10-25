# Laya 연동과 검증

[English](laya.md) | [한국어](laya.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

## 요청 구성

DeciFlow는 TEXT 청크 또는 JSONL에서 추출한 텍스트를 `state`로 보내며 Criteria의
가변 질문 맵을 `questions`에 담습니다. 질문 수·이름·`choice`·`score`·`noul` 조합은
프로필마다 다릅니다. 기본 시스템 프로필의 category·urgency·ticket은 한 예시입니다.
Laya·Jev는 [`classifier.py`](../deciflow/classifier.py)의 요청 생성·결과 검증·UI 동작을
공유합니다. [요청·결과 JSON](results.ko.md)과 [Criteria](criteria.ko.md)를 참고하세요.

| 설정 | DeciFlow 동작 |
| --- | --- |
| `LAYA_MODEL` | 내장 모델 또는 서버에 등록한 이름을 명시. 자동 모델 선택 없음 |
| `LAYA_MAX_TOKENS` | max_len으로 전달. 빈 값이면 English 512, Multilingual·Typed-decisions 8192. 사용자 모델은 명시적 값 필요 |
| `LAYA_HEAD_TOKENS` | head_max_len으로 전달. 기본 256이며 양수·전체 윈도 미만 |
| `LAYA_CONCURRENCY` | 실행별 최대 동시 요청 수. 기본 4. 파일 Batch는 개별 요청이며 추론 배치가 아님 |

Jev에는 Jev 모델 이름을 보내고 Laya 전용 토큰 예산 필드는 전달하지 않습니다.
엔진은 명시적으로 선택하며 유료 Jev로 자동 전환하지 않습니다.

다중 호스트 Task도 같은 요청을 사용하며 호스트 정보는 결과 메타데이터에만 남기고
`state`에 추가하지 않습니다. 동시 요청 제한은 실행 전체가 공유하며 호스트 수집에는
순환 기회를 부여합니다. [Tasks](tasks.ko.md#여러-source-hosts)를 참고하세요.

## 입력·응답 검증

예산은 고정 예약량이 아닌 상한입니다. 실제 로그 공간은 렌더링된 질문과 시퀀스
오버헤드에 따라 달라지며 `max_len - head_max_len`은 정확한 토큰 계산식이 아닙니다.
질문 예산을 늘리면 로그에 남는 공간이 줄 수 있습니다.

Laya 응답에는 Boolean `usage.truncated`가 필요합니다. 값이 true이거나 필드가
없거나 유효하지 않으면 판정을 거절하고 원본 로그를 보존합니다.
`state_tokens_dropped`·`truncated_questions`가 제공되면 로그 본문(state)의 잘림을
나타내며 지시문 축약 정보는 아닙니다. false만으로 지시문·선택지 설명 전체가
보존되었다고 판단할 수 없습니다.

로컬 `laya_server.py` 어댑터는 지시문·선택지가 축약되면
`usage.criteria_tokens_dropped`를 보고하며 DeciFlow는 해당 결과에 검토 표시를 합니다.
기본 Compose 서버는 이 메타데이터를 제공하지 않을 수 있습니다.

프로필에서 요청한 모든 답변이 유효해야 합니다. Choice 확률은 해당 프로필의 선택지와
일치하고 합이 약 1이어야 합니다. Score는 프로필의 범례·확률·확률 가중합과 일치해야
하며 Noul은 0~1 확률입니다. 답변 누락·오류는 전체 요청을 실패시킵니다.

Choice는 선택 확률 70% 미만, 상위 두 확률 차이 10%p 미만, Laya가 보고한 선택지 구별
손실을 검사합니다. Score·Noul에는 별도 타입별 검토 규칙을 적용하며 하나의 분류 확률로
전체 프로필을 판단하지 않습니다. 원래 판정·확률은 보존하고 사용자 모델은 `routing.model`
일치도 확인합니다. [검토 규칙](usage.ko.md#불확실성과-사람의-검토)을 참고하세요.

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

## 한계

DeciFlow는 모델 학습·확률 보정·네이티브 추론 배치·실제 서비스 토크나이저 기준
지시문 전체 보존 검사를 수행하지 않습니다. 범주 확률과 검토 임계값은 정확도
보장이 아닙니다. Docker Hub 이미지의 설치 Laya 버전·모델 리비전은 실행 중인
서버에서 확인해야 하며 저장소 설정만으로 확정할 수 없습니다.
아래 공식 참고 자료는 Laya v0.4.1 동작을 설명합니다.

<a id="evaluation"></a>

## 모델 평가

`scripts/evaluate_laya.py`로 설정한 Laya 모델을 정답 로그와 비교합니다.
각 요청은 로그를 `state`로 보내고 분류(`choice`), 긴급도(`score`), 작업 티켓
필요성(`noul`)을 함께 묻습니다. 분류 코드는 세 답변을 모두 검증하지만,
정답 라벨과의 비교는 **분류 범주만** 평가합니다.
긴급도·티켓 확률의 정확도는 측정하지 않으며 Jev 호출은 거부합니다.

### 평가 실행

`.env`에서 `DECISION_ENGINE=laya`와 `LAYA_MODEL`을 설정하세요.
선택한 모델이 Laya 서버에 준비되어 있어야 합니다. 실행 방식은 하나를 선택합니다:

- **Docker Compose:** UI 컨테이너 안에서 실행합니다.
  `http://laya:8000/v1/systemone`으로 선택한 CPU·CUDA 서비스에 연결합니다.
- **로컬 Python:** uv와 프로젝트 의존성이 설치된 복제 저장소에서 실행합니다.
  `LAYA_API_URL`은 접근 가능한 Laya 주소로 설정하세요. 같은 호스트의 Laya는
  `http://127.0.0.1:8000/v1/systemone`을 사용합니다.

Docker Compose:

```bash
docker compose exec ui uv run --no-sync python -m scripts.evaluate_laya \
  --output /tmp/laya-validation.json
docker compose cp ui:/tmp/laya-validation.json /tmp/laya-validation.json
```

로컬 Python:

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

기본값은 [5개 프로필의 합성 사례 36개](../tests/fixtures/log_evaluation.json)이며,
동시 요청은 최대 두 개로 제한합니다. 평가에는 [`deciflow/profiles/`](../deciflow/profiles/)의 번들
기준을 사용하며 UI에서 수정·저장한 기준은 읽지 않습니다.
UI에서 편집한 기준은 정답 로그를 UTF-8 파일로 만들고 Local File Source로 등록한 뒤,
해당 프로필을 선택한 Batch Task를 실행해 Main에서 결과를 검증하세요.

준비된 모델을 비교하려면 선택한 명령에 `--model` 옵션을 반복해서 추가합니다:

```text
--model english --model multilingual --model typed-decisions
```

자체 사례는 UTF-8 JSON 목록으로 작성하고 `--cases PATH`로 지정하세요:

```json
[
  {
    "log": "application: database connection failed",
    "expected": "error",
    "profile": "617706a3-c4ee-426f-81cf-7f5d80ecf67a"
  }
]
```

각 사례에는 로그 문자열과 기대 범주(`normal`·`warning`·`error`·`security`·`other` 중 하나)가
필요합니다. `profile`은 번들 Criteria UUID이며 기본값은 Sample General System입니다.
사례 파일 경로는 평가 스크립트를 실행하는 환경에서 읽을 수 있어야 합니다.

### 보고서 확인

생성한 JSON은 UTC `evaluatedAt`과 모델별 항목을 담은 `reports` 목록을 포함합니다:

| 필드 | 의미 |
| --- | --- |
| `model` | 요청한 체크포인트 이름 |
| `total` / `correct` | 전체 사례 수 / 기대 범주와 일치한 예측 수 |
| `failed` | 거절된 요청·유효하지 않은 답변·연결 및 API 오류 |
| `uncertain` | Uncertain으로 표시한 성공 판정 수 |
| `certain` / `certainCorrect` | Uncertain이 아닌 성공 판정 수 / 그중 기대 범주와 일치한 수 |
| `confusionMatrix` | 행은 기대 범주, 열은 예측 범주이며 실패 열도 포함 |
| `rows` | 입력 사례·일치 여부·분류 결과. 성공 시 세 질문과 답변 포함 |

Certain은 DeciFlow의 확률·선택지 구별 검사를 통과했다는 뜻이며 정답 보장이 아닙니다.
대표 정답 로그로 오분류와 검토량을 평가하세요. 합성 사례는 회귀 검증용이며 운영
정확도 추정 자료가 아닙니다. 모델·판정 기준·입력 예산이 결과에 영향을 주므로
실행 결과를 비교할 때 같은 조건을 유지하세요.

응답 스키마는 [요청·결과 JSON](results.ko.md), 검토 임계값은
[불확실성 규칙](usage.ko.md#불확실성과-사람의-검토)을 참고하세요.


## 근거

- [공식 README: 예산·한계](https://github.com/NandhaKishorM/laya#honest-limits)
- [HTTP API: 요청 옵션·제한·장치·동시 요청](https://nandhakishorm.github.io/laya/http-api/)
- [v0.4.1 HTTP 구현](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/serve.py)
- [v0.4.1 Agent: 렌더링·usage](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/agent.py)
- [v0.4.1 Router: 라우팅·preload·배치](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/router.py)
- [토큰 예산 조정 가이드](https://nandhakishorm.github.io/laya/langchain/#7-widening-the-token-budget-for-many-options)

## Docker Laya 상세

<a id="laya-docker"></a>

#### Laya 엔진 사용

기존 공용 Laya 서버에 연결하거나 아래 절차로 원격 노드에 서버를 구성하세요.
이미 서버가 있다면 구성 절차를 건너뛰고 DeciFlow 연결 설정만 적용합니다.

Laya 호스트의 복제한 저장소에서 [docker-compose.yml](../docker-compose.yml)을 사용합니다.
`.env.example`의 기본값은 CPU이며, 호환 NVIDIA GPU가 있으면 추론 성능을 높일 수 있습니다.
실제 성능은 하드웨어와 작업량에 따라 달라집니다.
Laya 서비스만 선택해도 Compose는 OAuth 값을 포함한 전체 `.env`를 검증합니다.
먼저 [배포 설정](authentication.ko.md)을 완료하세요.

##### CPU 실행

`.env`에서 `COMPOSE_PROFILES=cpu`를 설정한 뒤 실행하세요:

```bash
docker compose up -d laya-cpu
```

Laya와 DeciFlow를 함께 실행하려면 대신 `docker compose up -d`를 사용합니다.
두 Laya 방식 모두 호스트 포트 **8000**, `deciflow-laya-model-cache` 공유 볼륨,
`english`·`multilingual`·`typed-decisions` 사전 적재를 사용합니다.
프로필은 하나만 선택하세요. 이 구성에서 CPU·CUDA를 동시에 실행할 수 없습니다.
`.env`의 `LAYA_API_KEY`를 Laya와 DeciFlow가 함께 사용하며, 빈 키는 인증을 비활성화합니다.

<a id="laya-gpu"></a>

##### 선택 사항: GPU 가속(CUDA)

CUDA 실행에는 호환 NVIDIA GPU·드라이버와
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)이 필요합니다.
`nvidia-smi`로 GPU·드라이버를 확인하세요. `CUDA Version`은 드라이버의 지원 버전이며
설치된 Toolkit 버전이 아닙니다. 이 컨테이너에는 로컬 CUDA Toolkit이 필요하지 않습니다.
CUDA 13.0 이미지에는 [580 이상 드라이버](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)가 필요합니다.
CUDA 서비스는 모든 GPU를 사용하도록 요청하며 CPU 서비스는 GPU를 요청하지 않습니다.

기존 배포를 전환하려면 필요한 결과를 내보낸 뒤 **프로필을 수정하기 전에** 현재 구성을 종료하세요:

```bash
docker compose down
```

`.env`에서 `COMPOSE_PROFILES=cuda`로 변경하고 실행하세요:

```bash
docker compose up -d
docker compose logs --follow laya-cuda
```

CPU로 돌아가려면 같은 절차에서 `COMPOSE_PROFILES=cpu`를 사용합니다.
내부 URL `http://laya:8000/v1/systemone`은 그대로 유지합니다.

<a id="laya-health"></a>

##### 상태 확인과 관리

아래 명령은 선택한 컨테이너 안에서 서버 키를 출력 없이 읽어 상태를 확인합니다.
CUDA를 사용하면 `laya-cpu`를 `laya-cuda`로 바꾸세요:

```bash
docker compose exec laya-cpu python -c 'import os, urllib.request; r = urllib.request.Request("http://127.0.0.1:8000/health", headers={"Authorization": "Bearer " + os.environ["LAYA_API_KEY"]}); print(urllib.request.urlopen(r).read().decode())'
```

CUDA 사용 시 `checkpoint_devices`·`device`와 `cpu_fallbacks`로 실제 GPU 사용을 확인합니다.
신뢰할 수 있는 DeciFlow 노드만 Laya에 접근하도록 제한하고 외부 네트워크에는 TLS를 사용하세요.
잘림 메타데이터를 위해 `LAYA_JEV_STRICT=0`을 유지합니다. 최초 모델 적재에는 수 분이
걸릴 수 있으며 시작 오류는 컨테이너 로그에서 확인하세요.

| 작업 | 명령 |
| --- | --- |
| 상태 | `docker compose ps` |
| 로그 | `docker compose logs --tail=100` |
| 중지 | `docker compose stop` |
| 재개 | `docker compose start` |
| 컨테이너 제거 | `docker compose down` |

`down`은 이름 있는 볼륨을 유지합니다. 데이터를 보존하려면 `--volumes`를 추가하지 마세요.
네이티브 실행과 Docker 중 하나를 선택하세요.

##### DeciFlow 연결 설정

같은 Compose 구성에서는 `LAYA_API_URL=http://laya:8000/v1/systemone`을 사용합니다.
외부 Laya 서버에 연결하려면 `.env`에 접근 가능한 URL과 서버와 동일한 API 키를 설정하세요:

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

`COMPOSE_PROFILES=`로 두고 `docker compose up -d`를 실행하면 로컬 Laya 없이 UI가 시작되며 OAuth2-Proxy는 OAUTH2_PROXY_ENABLED에 따릅니다.
Docker 없이 실행하려면 [네이티브 안내](../INSTALL.ko.md#direct-processes)를 따르세요.
