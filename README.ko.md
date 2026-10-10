# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**쌓이는 로그를 AI로 분류하고, 오류·보안 이벤트를 한눈에 확인하세요.**

DeciFlow는 Laya 또는 Jev로 로그를 **Normal, Warning, Error, Security, Other**로
분류합니다. 기존 파일은 배치로 분석하고 새 로그는 실시간으로 받아보세요.
각 줄을 직접 읽는 대신 분류별 확률과 신뢰도를 참고해 검토할 결과를 추릴 수 있습니다.

- **로그가 있는 곳에서 바로 시작합니다.** 붙여 넣기부터 여러 디렉터리의 파일·
  와일드카드 입력까지 지원하므로 파일을 수동으로 합칠 필요가 없습니다.
- **일회성 분석과 실시간 감시를 함께 제공합니다.** Batch로 기존 로그를 읽거나
  Follow로 새 줄과 파일 회전을 감시합니다. 최근 판정 완료 결과부터 표시합니다.
- **최종 검토는 사람이 합니다.** 불확실한 판정을 필터링하고 검토자 수정값을 기록해
  JSON으로 내보내세요. 거절된 이벤트도 원문을 검토 대상으로 보존합니다.
- **여러 노드가 추론 서버를 공유합니다.** 로그 노드에는 가벼운 Python 클라이언트를
  실행하고 원격 Laya 서버에 연결합니다. 클라이언트에는 GPU·PyTorch가 필요하지 않습니다.
- **엔진을 선택합니다.** 기본 Laya를 자체 운영하면 Jev API 호출료가 없습니다.
  `.env`에서 Jev로 전환해도 사용 흐름은 같으며 유료 엔진으로 자동 전환하지 않습니다.

access 로그, 애플리케이션 오류, 운영 이벤트에 활용하세요.
기존 로그 파일 하나로 시작해 브라우저에서 판정 결과를 검토할 수 있습니다.

## 빠른 시작

**Python 3.11 이상**과 **uv**가 필요합니다. 원격 클라이언트에는 Docker·CUDA가 필요하지 않습니다.

`.env`가 없으면 [.env.example](.env.example)을 복사하고 Laya 서버 URL과
서버와 동일한 API 키를 설정하세요:

```dotenv
DECISION_ENGINE=laya
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

DeciFlow 디렉터리에서 실행합니다:

```bash
uv sync
uv run python server.py
```

**http://127.0.0.1:4000**에 접속하세요. 설정 변경 후 서버를 재시작합니다.
Jev를 사용하려면 `DECISION_ENGINE=jev`와 `TYPESAFE_API_KEY`를 설정하세요.

## 원격 Laya 서버

원격 Laya 호스트에서 **아래 두 방법 중 하나만 선택**하세요.

- **Docker run:** 스크립트로 이미 빌드된 이미지를 실행합니다.
- **Docker Compose:** 공식 Laya 저장소를 복제하고 소스에서 빌드합니다.

이 문서는 CPU·CUDA 모두 Docker로 Laya 서버를 간편하게 실행하는 절차를 안내합니다.
CUDA 실행에는 NVIDIA 드라이버와
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)도
필요합니다. `nvidia-smi`로 GPU·드라이버를 확인하세요. `CUDA Version`은 드라이버의
지원 버전이며 설치된 Toolkit 버전이 아닙니다. 로컬 Toolkit은 `nvcc --version`으로
확인하며 이 컨테이너에는 설치가 필요하지 않습니다. CUDA 13.0 이미지에는 호환 GPU와
[580 이상 드라이버](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)가 필요합니다.

### Docker run

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

### Docker Compose

Docker Compose v2가 필요합니다. Laya를 복제하고 공식 Compose 파일을 사용합니다.
이 방법은 소스에서 로컬 이미지를 빌드합니다.
`changeme` 대신 강한 API 키를 사용하고 DeciFlow의 `.env`에도 같은 키를 설정하세요.

```bash
git clone --branch v0.4.1 --depth 1 https://github.com/NandhaKishorM/laya.git
cd laya

export LAYA_API_KEY="${LAYA_API_KEY:-changeme}"
export LAYA_BIND_ADDRESS=0.0.0.0
export LAYA_PORT=8000
export LAYA_PRELOAD=1
export LAYA_MODELS=multilingual
```

**CPU 또는 CUDA 중 하나**를 선택하세요.

**CPU**

```bash
export COMPOSE_FILE=compose.yaml:compose.http.yaml
export LAYA_DEVICE=cpu
export LAYA_TORCH_INDEX=cpu

docker compose up --detach --build --wait laya-serve
```

**CUDA**

```bash
export COMPOSE_FILE=compose.yaml:compose.http.yaml:compose.cuda.yaml
export LAYA_DEVICE=cuda
export LAYA_TORCH_INDEX=cu130

docker compose up --detach --build --wait laya-serve
```

`compose.http.yaml`은 HTTP 서버 설정, `compose.cuda.yaml`은 GPU 사용과 CUDA 빌드
설정입니다. `LAYA_BIND_ADDRESS`로 호스트 IP, `LAYA_PORT`로 호스트·컨테이너 포트를
설정하고 `LAYA_API_URL`에도 반영하세요. 관리 시 같은 디렉터리, `COMPOSE_FILE`,
export한 설정을 유지하고 변경 후 `up`을 다시 실행합니다.
모델 적재가 느리면 `--wait-timeout 1200`을 추가하세요.

### 상태 확인과 관리

상태 확인 시 `LAYA_API_KEY`에 서버와 동일한 키를 사용하세요(기본값: `changeme`).

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${LAYA_API_KEY:-changeme}" \
  http://127.0.0.1:8000/health
```

DeciFlow 노드에서는 `127.0.0.1`을 서버 주소로 바꾸세요.
`checkpoint_devices`·`device`와 `cpu_fallbacks`로 실제 GPU 사용을 확인합니다.
신뢰할 수 있는 클라이언트로 접근을 제한하고 외부 네트워크에는 TLS를 사용하세요.
잘림 메타데이터를 위해 `LAYA_JEV_STRICT=0`을 유지합니다. 최초 모델 적재에는 수 분이
걸릴 수 있으며 시작 오류는 컨테이너 로그에서 확인하세요.

| 작업 | Docker run | Compose |
| --- | --- | --- |
| 상태 | `docker ps --filter name=laya-server` | `docker compose ps` |
| 로그 | `docker logs --tail=100 laya-server` | `docker compose logs --tail=100 laya-serve` |
| 중지 | `docker stop laya-server` | `docker compose stop laya-serve` |
| 재시작 | `docker start laya-server` | `docker compose up --detach` |
| 제거 | 중지 후 `docker rm laya-server` | `docker compose down` |

제거 시 모델 캐시는 유지됩니다. 배포 방법은 한 번에 하나만 사용하세요.

### Docker run 커스텀 이미지(선택)

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

## 설정

클라이언트 설정은 `.env`에서 관리하며 프로세스 환경변수가 우선합니다.
Laya 서버 설정은 원격 호스트에서 별도로 관리합니다.

| 환경변수 | 기본값 | 역할 |
| --- | --- | --- |
| `DECISION_ENGINE` | `laya` | `laya` 또는 `jev` |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | 프록시 접두사를 포함한 전체 Laya URL |
| `LAYA_API_KEY` | `changeme` | Laya 서버와 동일한 키 |
| `PORT` | `4000` | DeciFlow 웹 포트 |
| `TYPESAFE_API_KEY` | 미설정 | Jev API 키 |
| `MAX_JEV_INPUT_BYTES` | `30000` | Jev 요청 JSON의 UTF-8 바이트 예산; 1~30000 허용 |

## 사용법

| 입력 소스 | 동작 |
| --- | --- |
| Paste logs | 비어 있지 않은 줄마다 이벤트 하나 처리 |
| Batch file | 매칭 파일을 처음부터 EOF까지 처리 |
| Follow file | 기존 파일 끝부터 감시; 새 파일·교체 파일은 처음부터 처리 |

파일 입력은 로컬 브라우저 접속(`localhost`·`127.0.0.1`)과 DeciFlow가 읽을 수 있는
UTF-8 일반 파일이 필요합니다. 경로·패턴을 한 줄씩 입력하세요. 절대 경로, 여러
디렉터리, `*`, `?`, `[abc]`, 재귀 `**`를 지원합니다. 상대 경로는 서버 실행
디렉터리 기준이며 파일 단위로 중복 매칭을 제거합니다. Batch는 매칭 파일이 필요하고
Follow는 새 매칭 파일을 기다릴 수 있습니다.

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

**Stop processing**은 파일 읽기와 진행 중 클라이언트 요청을 취소하고 완료 결과를
보존합니다. 원격 서버에서 이미 실행 중인 추론은 완료될 수 있습니다.

## 제약

- 앱의 파일 크기·줄 수 제한은 없지만 RAM과 브라우저 용량에 영향을 받습니다.
  파일은 점진적으로 읽으며 여러 줄 이벤트는 묶지 않습니다.
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
- Follow는 250ms마다 확인하고 완성된 줄을 기다립니다. 회전 시 남은 줄은
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

클라이언트 URL을 루프백으로 설정하고 다른 터미널에서 DeciFlow를 시작하세요.
0.3.20에서는 해당 버전의 HTTP 서버에 없는 토큰 예산 검사와 잘림 메타데이터를
제공하는 이 어댑터를 사용합니다. 로컬 서버 옵션은 프로세스 환경변수로 지정합니다.
원격 클라이언트에는 `laya` 추가 의존성이 필요하지 않습니다.

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)
