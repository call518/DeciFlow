# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**쌓이는 로그를 AI로 분류하고, 오류·보안 이벤트를 한눈에 확인하세요.**

DeciFlow는 Laya 또는 Jev로 로그를 **Normal, Warning, Error, Security, Other**로
분류합니다. 기존 파일은 배치로 분석하고 새 로그는 실시간으로 받아보세요.
각 줄을 직접 읽는 대신 분류별 확률과 신뢰도를 참고해 검토할 결과를 추릴 수 있습니다.

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
복제·빌드는 필요하지 않습니다. 사용할 스크립트를 Laya 호스트로 복사하세요.

CPU: [run-deciflow-laya-cpu.sh](scripts/run-deciflow-laya-cpu.sh)

```bash
bash scripts/run-deciflow-laya-cpu.sh
```

CUDA: [run-deciflow-laya-cuda.sh](scripts/run-deciflow-laya-cuda.sh)

```bash
bash scripts/run-deciflow-laya-cuda.sh
```

스크립트는 `LAYA_API_KEY` 기본값으로 `changeme`를 설정하며 기존 환경변수 값이
있으면 이를 우선합니다. 실제 배포에는 강한 키를 사용하고 DeciFlow의 `.env`에도
같은 값을 설정하세요.

스크립트는 **8000** 포트, `multilingual` 사전 적재,
`deciflow-laya-model-cache` 공유 볼륨을 사용합니다. CUDA는 컨테이너에 모든 GPU를
노출합니다. 호스트 인터페이스·포트는 `--publish 호스트_IP:호스트_포트:8000`을
수정하고 `LAYA_API_URL`에도 반영하세요. 두 스크립트 모두 `laya-server`를 사용하므로
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
| 상태 | `docker ps --filter name=laya-server` |
| 로그 | `docker logs --tail=100 laya-server` |
| 중지 | `docker stop laya-server` |
| 재시작 | `docker start laya-server` |
| 제거 | 중지 후 `docker rm laya-server` |

제거 시 모델 캐시는 유지됩니다. 배포 방법은 한 번에 하나만 사용하세요.

#### Docker run 커스텀 이미지(선택)

직접 만든 이미지가 필요한 경우에만 Laya **v0.4.1**에서 빌드합니다:

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
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

### Jev 엔진 사용

[Jev 설정 안내](https://docs.typesafe.ai/introduction/quickstart)에서 TypeSafe API 키를
발급받아 `.env`에 설정하세요. Jev는 유료이며 Laya 서버는 필요하지 않습니다.

```dotenv
DECISION_ENGINE=jev
TYPESAFE_API_KEY=your-typesafe-api-key
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
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | 프록시 접두사를 포함한 전체 Laya URL |
| `LAYA_API_KEY` | `changeme` | Laya 서버와 동일한 키 |
| `PORT` | `4000` | DeciFlow 웹 포트 |
| `TYPESAFE_API_KEY` | 미설정 | Jev API 키 |
| `MAX_JEV_INPUT_BYTES` | `30000` | Jev 요청 JSON의 UTF-8 바이트 예산; 1~30000 허용 |
| `LAYA_CONCURRENCY` | `4` | 실행별 최대 Laya 동시 요청 수; 양의 정수 |
| `JEV_CONCURRENCY` | `4` | 실행별 최대 Jev 동시 요청 수; 양의 정수 |

동시 요청 수는 Paste·Batch·Realtime 모두에 적용됩니다. Laya 서버 워커 수가 아닌
DeciFlow의 요청 수이며, 서버 처리 여력과 API 제한을 확인하며 조금씩 늘리세요.

## 사용법

사이드바에 로그를 읽는 DeciFlow 호스트의 hostname, 확인된 IP, OS 이름·버전을 표시합니다.
WSL·컨테이너에서는 해당 환경의 정보이며, 모든 네트워크 인터페이스를 나열하지는 않습니다.

### 판정 프로필과 청크

각 경로·패턴에 프로필과 **Lines/chunk**를 지정하세요. Paste도 별도로 선택합니다.
기본값은 **General system**, **비어 있지 않은 1라인**입니다.
[`profiles/`](profiles/)의 JSON을 수정·추가한 뒤 재시작하면 선택 항목에 반영됩니다.
기본 프로필은 General system, Authentication, HTTP access,
Application, Network / tcpdump text입니다. 새 프로필도 기존 5개 분류 키를 유지하세요.
Laya·Jev에 동일한 선택 기준을 적용하며 자동 유형 판단은 사용하지 않습니다.

서로 다른 파일의 줄은 섞지 않습니다. Batch는 EOF에 남은 줄도 판정합니다.
Realtime은 청크가 차거나 새 줄이 1초 동안 들어오지 않으면 판정하며 파일 회전
경계도 분리합니다. 중단하면 아직 제출하지 않은 청크는 버립니다.
겹치는 경로의 설정이 같으면 중복 제거하며, 다르면 오류로 알립니다.
**Pause updates**는 결과 목록만 고정하며 분석·지표 갱신은 계속합니다.
필터·페이지 이동은 고정된 목록에 적용하고, **Resume updates**로 새 결과를 반영합니다.
JSON 내보내기는 일시정지 중에도 수신한 모든 결과를 포함합니다.

각 결과의 **View JSON**으로 실패 정보와 수동 리뷰 값을 포함한 개별 JSON을 확인합니다.

Batch의 **File line(s)**는 실제 파일 라인 번호입니다. Realtime의
**Observed line(s)**는 감시 시작 또는 파일 회전 이후 읽은 라인 순번입니다.

결과·JSON에는 프로필, 설정한 청크 크기, 실제 라인 수, 파일 라인 범위를 남깁니다.
지표의 처리 개수와 요청 시간은 개별 라인이 아닌 청크 기준입니다.
모델 입력 예산은 청크 전체와 질문에 적용하며, 초과·잘린 입력은 임의 축약하지 않고
검토 대상으로 보존합니다. Network는 UTF-8 tcpdump 텍스트용이며 바이너리 PCAP은
지원하지 않습니다. 특화 기준은 실제 로그로 검증해야 하며 청크가 크다고 정확도가
보장되지는 않습니다.

| 입력 소스 | 동작 |
| --- | --- |
| Realtime | 기존 파일 끝부터 감시; 새 파일·교체 파일은 처음부터 처리 |
| Batch | 매칭 파일을 처음부터 EOF까지 처리 |
| Paste | 비어 있지 않은 줄을 선택한 청크 크기로 묶어 처리 |

파일 입력은 로컬 브라우저 접속(`localhost`·`127.0.0.1`)과 DeciFlow가 읽을 수 있는
UTF-8 일반 파일이 필요합니다. 경로·패턴을 한 줄씩 입력하세요. 절대 경로, 여러
디렉터리, `*`, `?`, `[abc]`, 재귀 `**`를 지원합니다. 상대 경로는 서버 실행
디렉터리 기준이며 파일 단위로 중복 매칭을 제거합니다. Batch는 매칭 파일이 필요하고
Realtime은 새 매칭 파일을 기다릴 수 있습니다.

분류는 **Normal, Warning, Error, Security, Other**이며 기준은
[classifier.py](classifier.py)에 있습니다. 확률, 신뢰도, 진행 상황, 시간을
표시하며 최근 판정 완료 결과부터 나열합니다. 신뢰도 70% 미만, Other, 요청 실패는 검토 대상입니다. 전체·검토 필요·검토 불필요
필터, 검토자 분류 수정,
JSON 내보내기를 지원하고 페이지당 100건을 표시합니다. 결과는 브라우저 메모리에
보관하므로 화면을 떠나기 전에 내보내세요.
Reviewer category는 사람의 수정값을 JSON의 `reviewerCategory`로 저장합니다.
모델 판정·검토 대상 여부를 변경하거나 모델을 학습시키지는 않습니다.
평균 처리시간은 실패를 포함한 완료 요청의 소요시간 평균이며 네트워크·서버 대기를
포함하고 새 로그 줄을 기다리는 시간은 제외합니다.
Active processing time은 요청이 하나 이상 진행 중인 구간을 중복 없이 합산합니다.
전체 경과시간 대비 0~100%이며 네트워크·서버 대기는 포함하고 유휴시간은 제외합니다.
대기 중에도 1초마다 갱신합니다. 중단·연결 종료 시 마지막 수신 값을 보존하므로
약 1초의 지연이 있을 수 있습니다. CPU 가동률을 의미하지 않습니다.

**Stop processing**은 파일 읽기와 진행 중 Laya·Jev 요청을 취소하고 완료 결과를
보존합니다. 원격 서버에서 이미 실행 중인 추론은 완료될 수 있습니다.

## 제약

- 앱의 파일 크기·줄 수 제한은 없지만 RAM과 브라우저 용량에 영향을 받습니다.
  파일은 점진적으로 읽습니다. 청크는 비어 있지 않은 줄 수로 묶으며
  이벤트 경계를 자동 인식하지 않습니다.
- **Laya:** `multilingual`, 질문 포함 8192 토큰(질문 헤드 256 토큰).
  문서의 서버 버전은 이벤트 50,000자, 요청 2 MiB 제한도 적용합니다.
  잘린 응답이나 잘림 메타데이터가 없는 응답은 거절합니다.
- **Jev:** `jev-1.13.0`, [state + 가장 긴 질문 32k, 전체 요청 64k 토큰](https://docs.typesafe.ai/models).
  바이트 예산은 보수적 검사이며 정확한 토큰 수나 수용 보장이 아닙니다.
- 거절 이벤트는 원문을 검토 대상으로 남기고 다른 이벤트는 계속 처리합니다.
  소스 읽기·UTF-8 오류는 처리를 중단하고 완료 결과를 보존합니다.
- 이벤트마다 한 번 요청하며 최대 4개를 동시에 호출합니다(Laya 제한 시간 120초,
  Jev 30초). Laya는 추론을 순차 실행합니다. 속도는 하드웨어·네트워크·제공자 제한에
  따라 다르며 신뢰도는 모델 확신도이지 실측 정확도가 아닙니다.
- Realtime은 250ms마다 확인하고 완성된 줄을 기다립니다. 회전 시 남은 줄은
  `incomplete`로 표시하며 줄 번호를 초기화합니다. 빠른 회전이나 축소·재증가로
  누락될 수 있습니다. 파일 중복 제거는 내용 중복을 제거하지 않으므로 활성 로그와
  회전 복사본을 함께 매칭하지 않도록 주의하세요.
- Laya는 설정한 서버로, Jev는 TypeSafe로 로그를 전송하며 Jev API 비용이 발생합니다.
  DeciFlow는 서버 디스크에 로그·결과를 저장하지 않습니다. 전송 전 민감 정보를
  제거하고 `.env`를 커밋하지 마세요. 공개 배포에는 인증과 사용량 제한이 필요합니다.

## 개발

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
