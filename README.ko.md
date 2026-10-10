# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**쌓이는 로그를 AI로 분류하고, 오류·보안 이벤트를 한눈에 확인하세요.**

DeciFlow는 로그 줄을 청크로 묶어 Laya 또는 Jev로
**Normal, Warning, Error, Security, Other**로
분류합니다. 기존 파일은 배치로 분석하고 새 로그는 실시간으로 받아보세요.
각 줄을 직접 읽는 대신 분류별 확률과 신뢰도를 참고해 검토할 결과를 추릴 수 있습니다.
소스별 프로필·청크 크기를 지정하고, 실시간 차트로 분포를 보거나 목록 갱신을
일시정지해 개별 결과를 살펴보세요.

**DeciFlow**는 로그가 있는 노드에서 실행해 이벤트를 읽고 브라우저에 결과를 표시합니다.
**Laya 서버**는 별도 호스트에서 판정 모델을 실행하며, **Jev 서비스**는 대신 선택할 수
있는 외부 판정 API입니다. DeciFlow는 선택한 엔진에 이벤트를 보내고 판정 결과를 받습니다.

- **로그가 있는 곳에서 바로 시작합니다.** 붙여 넣기부터 여러 디렉터리의 파일·
  와일드카드 입력까지 지원하므로 파일을 수동으로 합칠 필요가 없습니다.
- **일회성 분석과 실시간 감시를 함께 제공합니다.** Batch로 기존 로그를 읽거나
  Realtime으로 새 줄과 파일 회전을 감시합니다. 최근 판정 완료 결과부터 표시합니다.
- **최종 검토는 사람이 합니다.** 불확실한 판정을 필터링하고 검토자 수정값을 기록해
  JSON으로 내보내세요. 거절된 이벤트도 원문을 검토 대상으로 보존합니다.
- **여러 노드가 추론 서버를 공유합니다.** 각 로그 노드에서 DeciFlow를 실행하고
  공유 Laya 서버에 연결합니다. DeciFlow 실행 노드에는 GPU·PyTorch가 필요하지 않습니다.
- **엔진을 선택합니다.** 기본 Laya를 자체 운영하면 Jev API 호출료가 없습니다.
  `.env`에서 Jev로 전환해도 사용 흐름은 같으며 유료 엔진으로 자동 전환하지 않습니다.

access 로그, 애플리케이션 오류, 운영 이벤트에 활용하세요.
기존 로그 파일 하나로 시작해 브라우저에서 판정 결과를 검토할 수 있습니다.

## 빠른 시작

아래 **Laya 또는 Jev 중 하나만 선택**해 설정하세요.

DeciFlow 실행 노드에는 **Python 3.11 이상**과 **uv**가 필요합니다. 추론은 별도
Laya 서버 또는 Jev API가 처리하므로 이 노드에는 Docker·CUDA가 필요하지 않습니다.
DeciFlow 디렉터리에서 가상환경을 생성·활성화한 뒤 의존성을 설치합니다
(Linux·macOS·WSL의 Bash 기준):

```bash
uv venv
source .venv/bin/activate
uv sync
```

`.env`가 없으면 [.env.example](.env.example)을 `.env`로 복사하세요.
선택한 엔진의 설정을 적용합니다:

### Laya 엔진 사용

기존 공용 Laya 서버에 연결하거나 아래 절차로 원격 노드에 서버를 구성하세요.
이미 서버가 있다면 구성 절차를 건너뛰고 DeciFlow 연결 설정만 적용합니다.

아래는 Laya 호스트에서 Docker run으로 실행하는 절차입니다. Docker Compose를
사용하려면 아래 공식 문서 링크를 참고하고 **둘 중 하나만 선택**하세요.

이 문서는 CPU·CUDA 모두 Docker로 Laya 서버를 간편하게 실행하는 절차를 안내합니다.
CUDA 실행에는 NVIDIA 드라이버와
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)도
필요합니다. `nvidia-smi`로 GPU·드라이버를 확인하세요. `CUDA Version`은 드라이버의
지원 버전이며 설치된 Toolkit 버전이 아닙니다. 로컬 Toolkit은 `nvcc --version`으로
확인하며 이 컨테이너에는 설치가 필요하지 않습니다. CUDA 13.0 이미지에는 호환 GPU와
[580 이상 드라이버](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)가 필요합니다.

#### Docker run

**`call518/deciflow-laya:cpu`** 또는 **`call518/deciflow-laya:cuda`**를 사용합니다.
복제·빌드는 필요하지 않습니다. 사용할 스크립트를 Laya 호스트로 복사하고
아래 CPU·CUDA 명령 중 **하나만** 실행하세요.

CPU: [run-deciflow-laya-cpu.sh](scripts/run-deciflow-laya-cpu.sh)

```bash
bash scripts/run-deciflow-laya-cpu.sh
```

CUDA: [run-deciflow-laya-cuda.sh](scripts/run-deciflow-laya-cuda.sh)

```bash
bash scripts/run-deciflow-laya-cuda.sh
```

스크립트는 `--env LAYA_API_KEY=changeme`를 직접 지정하므로 다른 키를 export해도
덮어쓰지 않습니다. 실제 배포에는 이 인자를 강한 키로 변경하고 DeciFlow의 `.env`에도
같은 값을 설정하세요.

스크립트는 **8000** 포트, `multilingual` 사전 적재,
`deciflow-laya-model-cache` 공유 볼륨을 사용합니다. CUDA는 컨테이너에 모든 GPU를
노출합니다. 호스트 인터페이스·포트는 `--publish 호스트_IP:호스트_포트:8000`을
수정하고 `LAYA_API_URL`에도 반영하세요. 두 스크립트 모두 `DeciFlow-Laya`를 사용하므로
CPU·CUDA 전환 또는 설정 변경 전에 기존 컨테이너를 중지·제거합니다.

> **NOTE:** Docker Compose로 구성하려면 공식
> [Laya Docker 문서의 HTTP serving 항목](https://nandhakishorm.github.io/laya/docker/#http-serving)을 참고하세요.

#### 상태 확인과 관리

상태 확인 시 `LAYA_API_KEY`에 서버와 동일한 키를 사용하세요(기본값: `changeme`).

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${LAYA_API_KEY:-changeme}" \
  http://127.0.0.1:8000/health
```

DeciFlow 노드에서는 `127.0.0.1`을 서버 주소로 바꾸세요.
`checkpoint_devices`·`device`와 `cpu_fallbacks`로 실제 GPU 사용을 확인합니다.
신뢰할 수 있는 DeciFlow 노드만 Laya에 접근하도록 제한하고 외부 네트워크에는 TLS를 사용하세요.
잘림 메타데이터를 위해 `LAYA_JEV_STRICT=0`을 유지합니다. 최초 모델 적재에는 수 분이
걸릴 수 있으며 시작 오류는 컨테이너 로그에서 확인하세요.

| 작업 | Docker run |
| --- | --- |
| 상태 | `docker ps --filter name=DeciFlow-Laya` |
| 로그 | `docker logs --tail=100 DeciFlow-Laya` |
| 중지 | `docker stop DeciFlow-Laya` |
| 재시작 | `docker start DeciFlow-Laya` |
| 제거 | 중지 후 `docker rm DeciFlow-Laya` |

제거 시 모델 캐시는 유지됩니다. 배포 방법은 한 번에 하나만 사용하세요.

#### Docker run 커스텀 이미지(선택)

직접 만든 이미지가 필요한 경우에만 Laya **v0.4.1**에서 대상에 맞는
CPU **또는** CUDA 빌드 명령을 실행합니다:

```bash
git clone --branch v0.4.1 --depth 1 https://github.com/NandhaKishorM/laya.git
cd laya

docker build \
  --build-arg TORCH_INDEX=cpu \
  --tag my-laya:cpu .

docker build \
  --build-arg TORCH_INDEX=cu130 \
  --tag my-laya:cuda .
```

선택한 Docker run 스크립트의 이미지를 커스텀 태그로 바꾸세요.
`cpu`는 CPU 전용 PyTorch, `cu130`은 CUDA **13.0**을 뜻합니다. GPU·드라이버와
Dockerfile의 `TORCH_VERSION`에 맞는 CUDA 빌드를
[PyTorch 설치 목록](https://pytorch.org/get-started/previous-versions/)에서 선택하세요.
Laya 업그레이드 시 API 호환성을 검증합니다.

#### DeciFlow 연결 설정

DeciFlow 실행 노드의 `.env`에 공용 Laya 서버 URL과 서버와 동일한 API 키를 설정하세요:

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

### Jev 엔진 사용

[Jev 설정 안내](https://docs.typesafe.ai/introduction/quickstart)에서 TypeSafe API 키를
발급받아 `.env`에 설정하세요. Jev는 유료이며 Laya 서버는 필요하지 않습니다.

```dotenv
DECISION_ENGINE=jev
JEV_MODEL=jev-1.13.0
JEV_API_KEY=your-typesafe-api-key
PORT=4000
```

### DeciFlow 실행

```bash
uv run python server.py
```

**http://127.0.0.1:4000**에 접속하세요. 설정 변경 후 DeciFlow를 재시작합니다.

## 설정

DeciFlow 설정은 `.env`에서 관리하며 프로세스 환경변수가 우선합니다.
Laya 서버 설정은 Laya 호스트에서 별도로 관리합니다.

| 환경변수 | 기본값 | 역할 |
| --- | --- | --- |
| `DECISION_ENGINE` | `laya` | `laya` 또는 `jev` |
| `PORT` | `4000` | DeciFlow 웹 포트 |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | 프록시 접두사를 포함한 전체 Laya URL |
| `LAYA_API_KEY` | `changeme` | Laya 서버와 동일한 키 |
| `LAYA_MODEL` | `multilingual` | 내장 모델 또는 등록한 사용자 체크포인트 이름; 서버에 모델 필요 |
| `LAYA_MAX_TOKENS` | 빈 값 | `max_len`으로 전달; 빈 값은 내장 모델 기본값 유지, 사용자 모델은 필수 |
| `LAYA_HEAD_TOKENS` | `256` | `head_max_len`으로 전달; 질문·선택지 예산이며 전체 윈도 미만 |
| `LAYA_CONCURRENCY` | `4` | 실행별 최대 Laya 동시 요청 수; 양의 정수 |
| `JEV_API_KEY` | 미설정 | Jev API 키 |
| `JEV_MODEL` | `jev-1.13.0` | TypeSafe 지원 버전 ID 또는 `jev-latest` 등의 별칭 |
| `JEV_MAX_INPUT_BYTES` | `30000` | Jev 요청 JSON의 UTF-8 바이트 예산; 1~30000 허용 |
| `JEV_CONCURRENCY` | `4` | 실행별 최대 Jev 동시 요청 수; 양의 정수 |

`LAYA_HEAD_TOKENS=384`이면 매 Laya 요청에 `"head_max_len": 384`를 전송합니다.
`LAYA_MAX_TOKENS=1024`는 `"max_len": 1024`를 전송합니다. 해당 요청에서
체크포인트 기본값을 덮어씁니다. `.env` 변경 후 DeciFlow를 재시작하세요.
DeciFlow 설정이므로 이 값을 전송하기 위해 원격 Docker를 변경할 필요는 없습니다.

`LAYA_MAX_TOKENS`가 비어 있으면 DeciFlow 기본 윈도를 유지합니다:
English 512, Multilingual·Typed-decisions 8192. English는 최대 512,
다른 모델은 최대 8192를 허용합니다. 질문 예산은 양의 정수이며 전체 윈도 미만이어야
합니다. 256은 기본값이며 Laya API 최대값이 아닙니다. 이는 **DeciFlow 검증 범위**입니다.
공식 체크포인트 기본값은 English 512/192, 나머지 1024/256 토큰입니다.
서버는 별도로 `LAYA_MAX_TOKEN_BUDGET`(기본 8192)을 두 예산에 적용하며 초과하면
422를 반환합니다. 요청 예산은 결과 JSON의 `inputBudget`에 기록됩니다.

예산은 고정 예약량이 아닙니다. 실제 로그 공간은 렌더링된 질문에 따라 달라지므로
단순히 `max_len - head_max_len`으로 계산하면 안 됩니다. `usage.truncated`는 로그
잘림 정보이며 지시문 전체 보존을 뜻하지 않습니다. Laya가 범주 선택지의 구별 손실을
보고하면 DeciFlow는 Uncertain·Needs review로 표시하고 이유를 보여줍니다.
원래 판정 범주·확률·응답은 그대로 보존합니다.

사용자 체크포인트는 원격 서버의 `LAYA_EXTRA_MODELS`에 이름을 등록한 뒤
`LAYA_MODEL`에 그 이름을 넣고, 검증한 입력 용량 내에서 `LAYA_MAX_TOKENS`를
명시하세요. 이름은 영문자로 시작하며 영문자·숫자·`_`·`-`를 허용합니다.
URL·경로는 받지 않습니다. 응답의 `routing.model`이 지정한 사용자 모델을
확인해 주지 않으면 거절하여 다른 모델로 조용히 전환되는 것을 막습니다.
DeciFlow가 모델을 설치하거나 학습하지는 않습니다.

동시 요청 수는 Paste·Batch·Realtime 모두에 적용됩니다. Laya v0.4.1 추론 워커는
1개입니다. `LAYA_CONCURRENCY`는 클라이언트 요청 수, 서버 `LAYA_MAX_CONCURRENT`는
수용 제한입니다(기본 16, 초과하면 503). GPU 추론 병렬도 설정은 아닙니다.
잘림·라우팅 정보를 위해 서버 `LAYA_JEV_STRICT=0`을 유지하고 CPU `LAYA_THREADS`는
물리 코어 수 이하로 설정하세요. 파일 Batch는 여전히 개별 요청을 전송하며
실제 추론 배치 API를 사용하지 않습니다.

Jev는 Laya 예산을 무시합니다. Jev API는 `head_max_len`에 해당하는 옵션이 없으며
Jev 1.13은 state + 가장 긴 질문 32k, 전체 요청 64k 토큰 제한을 적용합니다.
`JEV_MAX_INPUT_BYTES`는 보수적 바이트 검사이며 토큰 할당량이 아닙니다.
Jev 모델 가용성은 계정·API에 따르며 별칭의 제한은 바뀔 수 있습니다.

파라미터 동작과 반영·보류 사항은 [연동 검토](docs/laya-integration-review.ko.md)를
참고하세요. 5개 프로필의 정답 라벨을 붙인 합성 사례 36개(헤더 변경 사례 포함)를
평가하려면 다음을 실행합니다:

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

보고서는 오분류 행렬, 요청 실패, Uncertain 수와 Certain 중 정답 수를 포함합니다.
사례는 회귀 검증용이며 운영 정확도 추정 자료는 아닙니다.
`--cases PATH`로 자체 정답 JSON(`log`, `expected`, 선택 사항 `profile`)을,
`--model NAME`으로 비교할 체크포인트를 지정합니다. Laya만 사용하며 유료 Jev는
호출하지 않습니다.

## 사용법

넓은 화면에서는 왼쪽 **40%**에 **Classification overview → Log input**, 오른쪽
**60%**에 **Classification results**를 배치합니다. 좁은 화면은 세로로 표시합니다.
사이드바에는 DeciFlow 로그 소스 노드의 hostname, 확인된 IP, OS·버전을 표시합니다.
WSL·컨테이너에서는 해당 환경의 정보이며 호스트 OS 정보가 아닙니다. IP는 전체
인터페이스 목록이 아닙니다. **Ready to connect**는 설정 상태이며 실제 엔진 연결
성공을 확인한 표시가 아닙니다.

### 입력과 판정 기준

기본 모드는 **Realtime**이며, 각 모드에 수정 가능한 예시가 입력되어 있습니다.

| 모드 | DeciFlow가 읽는 데이터 |
| --- | --- |
| Realtime | 기존 파일 끝 이후의 새 줄; 새 파일·교체 파일은 처음부터 |
| Batch | 매칭 파일의 처음부터 EOF까지 |
| Paste | 붙여 넣은 텍스트를 청크로 묶어 처리 |

파일은 **Laya 호스트가 아닌 DeciFlow 실행 노드**에 있어야 합니다. 파일 입력에는
로컬 브라우저 접속(`localhost`·`127.0.0.1`)과 읽기 가능한 UTF-8 일반 파일이
필요합니다. 경로·패턴을 한 줄씩 입력하며 절대 경로, 여러 디렉터리, `*`, `?`,
`[abc]`, 재귀 `**`를 지원합니다. 상대 경로는 DeciFlow 실행 디렉터리 기준입니다.
Batch는 매칭 파일이 필요하고 Realtime은 새 매칭 파일을 기다릴 수 있습니다.

각 경로·패턴 또는 Paste에 **Criteria**와 **Lines/chunk**를 지정하세요.
기본값은 **General system**, **비어 있지 않은 1라인**입니다. 모든 프로필은
`choice`로 **Normal, Warning, Error, Security, Other** 중 하나를 선택하며 설명과
지시문만 다릅니다. Laya·Jev에 동일한 선택 기준을 적용합니다. 유형은 사용자가
선택하며 `score`·`noul`은 사용하지 않습니다.

| Criteria 프로필 | 판정 대상 |
| --- | --- |
| General system | 시스템·서비스 동작과 장애 |
| Authentication | 인증·세션 결과, 서비스 장애, 악용 증거 |
| HTTP access | 응답, 요청 실패, 의심 접근 |
| Application | 애플리케이션 작업, 예외, 의존 서비스 |
| Network / tcpdump text | 텍스트의 연결·패킷 증거; 바이너리 PCAP 미지원 |

[`profiles/`](profiles/)의 JSON을 수정·추가하고 재시작하면 선택 항목에 반영됩니다.
`label`, `instructions`, `criteria`와 기존 5개 분류 키를 유지하세요. 기준에는 사건의
결과와 증거를 설명하고, 특정 로그 문자열은 검증 샘플에서 다룹니다. 운영 기준에
메시지별 예외를 계속 추가하는 방식은 피합니다.

서로 다른 파일의 줄은 섞지 않습니다. Batch는 EOF 잔여분을, Realtime은 설정한
줄 수가 차거나 새 줄이 1초 동안 없으면 제출하며 파일 회전 경계도 분리합니다.
빈 줄은 제외하고 이벤트 경계를 자동 인식하지는 않습니다. 겹치는 경로는 설정이
같으면 실제 경로 기준으로 중복 제거하고, 다르면 오류로 알립니다. 청크로 묶어도
모델 입력 예산은 그대로 적용됩니다.

General system은 정상 동작(Normal), 복구 가능한 문제(Warning), 명시적 실패(Error),
악용·정책 위반의 증거(Security)를 구분합니다. 서비스명·IP·보안 관련 주제만으로
보안 사건을 판정하지 않습니다. 기준은 모델의 판단 지침이므로 실제 활용 전
대표 로그로 배포 모델의 판정 정확도를 검증하세요.

Authentication은 개별 시도 실패·중단(Warning), 서비스·지원 기능 장애(Error),
악용 증거(Security)를 구분합니다. Other는 관련 없는 사건이나 결과를 식별할 수
없는 경우이며, 원인을 모른다는 이유만으로 선택하지 않습니다. 인식 가능한
**단일 라인의 전통적 syslog**는 모델 입력에서 시간·호스트명·PID만 제외하고
서비스명·메시지의 사용자·IP·포트는 유지합니다. 원본은 보존하며 변경된
`decisionInput`을 JSON에서 확인할 수 있습니다. 여러 줄 청크와 미지원 형식은
그대로 전달합니다. 정규화는 동일 판정이나 정확도를 보장하지 않습니다.

### 결과와 조작

최근 **판정 완료** 청크부터 페이지당 100건을 표시합니다. 로그 타임스탬프 순서가
아닌 완료 순서입니다. Batch의 **File line(s)**는 실제 파일 라인 번호이고,
Realtime의 **Observed line(s)**는 감시 시작 또는 파일 회전 이후 읽은 라인 순번입니다.
`1 line (max 5)`는 최대 5라인 설정에서 실제 1라인을 제출했다는 뜻입니다.

선택 범주의 확률(`answerProbability`)이 70% 미만이거나 상위 두 범주의 확률 차이가 10%p 미만이면
**Uncertain**으로 표시합니다. 모델의 원래 범주·확률은 유지하며 화면에 잠정 후보를,
JSON에 후보·확률 차이·검토 사유를 남깁니다. Other·요청 실패도 검토 대상입니다.
이 임계값은 검토 기준이며 정확도 보장이 아닙니다. 엔진 고유 `confidence`는 척도가 달라 별도로 보존하며
Uncertain 판단에는 사용하지 않습니다. **All results / Needs review / No review needed**로 필터링합니다.
범주 필터와 원본 로그의 대소문자 구분 없는 문자열 검색을 함께 적용할 수 있습니다.
목록에만 적용하며 지표·차트·JSON 내보내기는 전체 결과 기준입니다.

| 조작 | 동작 |
| --- | --- |
| Pause updates / Resume updates | 첫 결과 전부터 목록을 고정·재개합니다. 분석·지표·차트는 계속 갱신합니다. 필터·페이지 이동은 고정된 목록에 적용하고 버튼에 새 결과 수를 표시합니다. |
| Stop processing | 파일 읽기·진행 중 요청을 취소하고 완료 결과는 보존합니다. 미제출 청크는 버리며 원격지의 추론은 완료될 수 있습니다. |
| View JSON | 실패 정보, 프로필·청크 정보, 수동 리뷰 값을 포함한 개별 JSON을 펼칩니다. 목록 갱신에도 펼친 상태를 유지합니다. JSON 영역 안의 Copy는 수동 리뷰 값을 포함한 현재 항목을 클립보드에 복사합니다. |
| Reviewer category | `reviewerCategory`를 기록합니다. AI 범주·검토 상태·차트를 바꾸거나 모델을 학습시키지 않습니다. |
| Export JSON | 처리 완료 또는 중단 후 수신한 모든 결과를 내보냅니다. Pause 중 화면에 반영되지 않은 결과도 포함합니다. |

**Classification overview**는 불확실한 선택을 포함해 전체 소스의 AI 분류 개수를
합산합니다. 개수는 원본 라인이 아닌 **청크** 기준이며, 비율은 판정에 성공한 청크
기준입니다. 요청 실패는 별도 표시하고 필터·수동 정정은 집계에 영향을 주지 않습니다.
**All / Uncertain / Certain**으로 차트의 집계 그룹을 선택하며 비율은 선택 그룹
기준입니다. Certain은 Uncertain 표시가 없다는 뜻이며 정확도 보장이 아닙니다.
실패 개수는 항상 전체 요청 실패를 표시하며 어느 확실성 그룹에도 포함하지 않습니다.
**Truncated**는 전체 그룹의 `usage.truncated=true` 응답 수입니다. 거절한 판정이므로
실패에 포함하고 범주 막대에서는 제외합니다. 메타데이터 누락·로컬 바이트 예산
초과는 이 수에 포함하지 않습니다. 로그 본문 잘림이며 질문 지시문 잘림 수는 아닙니다.

결과 JSON에 `requestedModel`, UTC `requestedAt`, 요청 크기, 입력 예산과
질문·판정 기준을 남깁니다. `providerResponse`에는 응답 모델, 실제 체크포인트
`routing`, 토큰·잘림 정보 `usage`, 엔진별 confidence와 action·abstention 등
전체 응답을 보존합니다. 최상위 `answerProbability`는 선택 범주의 확률이며,
`confidence`는 엔진 원래 값입니다. `uncertaintyBasis`로 70% 임계값에 적용한
선택 범주 확률 척도를 명시합니다. HTTP 상태와 제공된 요청 ID·추론 시간 헤더도 남기며
인증 키·Authorization 헤더는 제외합니다. API 실패·판정 거절 시에도 확보한
진단 정보를 보존합니다. Laya의 `model`은 공통 이름일 수 있으므로 실제 모델은
`providerResponse.routing`에서 확인하세요.

결과·수동 정정은 **브라우저 메모리에만** 남습니다. 새로고침·페이지 종료 시 사라지고
새 처리를 시작하면 이전 결과를 교체합니다. 화면을 떠나거나 새로 실행하기 전에
내보내세요. 이력 저장과 JSON 가져오기는 제공하지 않습니다.

### 시간 지표

| 지표 | 의미 |
| --- | --- |
| Processed chunks | 요청 실패를 포함한 완료 결과 수 |
| Needs review | 선택 범주 확률 70% 미만, 근접한 범주 확률, Other, 요청 실패; 오류 개수가 아님 |
| Total elapsed time | 실행 시작 이후 전체 경과시간; 유휴시간 포함 |
| Active processing time | 요청이 하나 이상 진행 중인 구간을 중복 없이 합산; 전체 경과시간 대비 비율 |
| Average processing time | 실패를 포함한 완료 요청의 평균 소요시간; 청크 기준 |

Active·Average에는 네트워크·서버 대기가 포함됩니다. Active는 유휴시간을 제외하며
전체 경과시간 대비 0~100%입니다. CPU·GPU 가동률이나 순수 추론시간이 아닙니다.
대기 중 시간 정보는 1초마다 갱신합니다. 중단·연결 종료 시 마지막 값을 보존하므로
약 1초의 차이가 있을 수 있습니다.

## 제약

- 앱의 파일 크기·줄 수 제한은 없지만 RAM과 브라우저 용량에 영향을 받습니다.
  파일은 점진적으로 읽습니다. 청크는 비어 있지 않은 줄 수로 묶으며
  이벤트 경계를 자동 인식하지 않습니다.
- **Laya:** 선택한 체크포인트를 사용하며 요청 윈도·질문 예산은 위 설정 설명을 따릅니다.
  [공식 HTTP 서버](https://nandhakishorm.github.io/laya/http-api/#limits)는 state
  50,000자, 요청 2 MiB 제한도 적용합니다. 배포한 버전의 제한을 확인하세요.
  잘린 응답이나 잘림 메타데이터가 없는 응답은 거절합니다.
- **Jev:** `jev-1.13.0`, [state + 가장 긴 질문 32k, 전체 요청 64k 토큰](https://docs.typesafe.ai/models).
  바이트 예산은 보수적 검사이며 정확한 토큰 수나 수용 보장이 아닙니다.
- 거절 이벤트는 원문을 검토 대상으로 남기고 다른 이벤트는 계속 처리합니다.
  소스 읽기·UTF-8 오류는 처리를 중단하고 완료 결과를 보존합니다.
- 청크마다 한 번 요청하며 엔진별 동시 요청 수는 실행당 기본 4개입니다.
  제한 시간은 Laya 120초, Jev 30초입니다. 동시 요청을 늘려도 병렬 추론이나 처리량
  증가를 보장하지 않으며 서버 처리 여력과 수용 제한이 적용됩니다.
- Realtime은 250ms마다 확인하고 완성된 줄을 기다립니다. 회전 시 남은 줄은
  `incomplete`로 표시하며 줄 번호를 초기화합니다. 빠른 회전이나 축소·재증가로
  누락될 수 있습니다. 파일 중복 제거는 내용 중복을 제거하지 않으므로 활성 로그와
  회전 복사본을 함께 매칭하지 않도록 주의하세요.
- Laya는 설정한 서버로, Jev는 TypeSafe로 로그를 전송하며 Jev API 비용이 발생합니다.
  DeciFlow는 서버 디스크에 로그·결과를 저장하지 않습니다. 전송 전 민감 정보를
  제거하고 `.env`를 커밋하지 마세요. 공개 배포에는 인증과 사용량 제한이 필요합니다.

`Ctrl+C`로 DeciFlow를 종료하면 최대 2초 대기 후 남은 요청을 취소합니다.
서버 종료 시 브라우저 메모리의 결과를 저장하지는 않습니다.

## 개발

실제 모델 결과와 남은 제약은 [Laya 로그 검증](docs/laya-validation.ko.md)을 확인하세요.
선택한 Laya 모델로 기대 범주를 기록한 13개 샘플을 다시 검증하려면:

```bash
uv run python -m scripts.evaluate_laya \
  --cases tests/fixtures/general_evaluation.json \
  --output /tmp/laya-validation.json
```

Laya 서버만 호출하며 유료 Jev는 거부합니다. 작은 표본이므로 정확도 보장이 아닙니다.

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

UI 회귀 테스트(Node.js는 테스트에만 필요):

```bash
node --test tests/test_ui.mjs
```

테스트는 유료 호출 없이 두 제공자, 입력 예산, 스트리밍, 취소, 파일 탐색·회전을
확인합니다. 두 README와 실제·예제 `.env`를 함께 관리하며 환경변수 주석은
영어와 한국어를 병기합니다.

선택적 로컬 Laya 개발 환경(0.3.20):

```bash
uv sync --extra laya
uv run --extra laya python laya_server.py
```

DeciFlow의 `LAYA_API_URL`을 루프백으로 설정하고 다른 터미널에서 DeciFlow를 시작하세요.
0.3.20에서는 해당 버전의 HTTP 서버에 없는 토큰 예산 검사와 잘림 메타데이터를
제공하는 이 어댑터를 사용합니다. 로컬 서버 옵션은 프로세스 환경변수로 지정합니다.
별도 Laya 서버를 사용하는 DeciFlow 실행 노드에는 `laya` 추가 의존성이 필요하지 않습니다.

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)
