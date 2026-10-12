<p align="center">
  <img src="images/DeciFlow-Logo.png" alt="DeciFlow" width="480">
</p>

# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**로그를 AI로 실시간 분류하고, 오류·보안 이벤트를 한눈에 확인하세요.**

[Demo Video](https://www.youtube.com/watch?v=wGMtxpeHHBs)

[![YouTube에서 DeciFlow 데모 보기](images/DeciFlow-Demo-Screenshot-2026-10-11-034530.png)](https://www.youtube.com/watch?v=wGMtxpeHHBs)

DeciFlow는 로그 이벤트를 청크로 묶어 Laya 또는 Jev로
**Normal, Warning, Error, Security, Other**로
분류합니다. 기존 파일은 배치로 분석하고 새 로그는 실시간으로 받아보세요.
각 줄을 직접 읽는 대신 분류별 확률과 신뢰도를 참고해 검토할 결과를 추릴 수 있습니다.
소스별 프로필·청크 크기를 지정하고, 실시간 차트로 분포를 보거나 목록 갱신을
일시정지해 개별 결과를 살펴보세요.

현재는 **`choice` 판정만 사용**합니다. 향후 활용 사례에 맞춰
**`score` 기반 평가·등급 산정**과 **`noul` 기반 양품·불량 등 예/아니오 확률 판정**을
추가하고, 각 유형에 맞는 판정 기준과 결과 화면을 업데이트할 예정입니다.

**DeciFlow**는 로그가 있는 노드에서 실행해 이벤트를 읽고 브라우저에 결과를 표시합니다.
**Laya 서버**는 같은 호스트 또는 별도 호스트에서 판정 모델을 실행하며, **Jev 서비스**는 대신 선택할 수
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

## 아키텍처

[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/call518/DeciFlow)

![DeciFlow architecture](images/DeciFlow-Architecture.png)

## 빠른 시작 — Docker + Laya GPU

**전제:** 같은 Linux 호스트에서 실행하며 Git, Docker, 호환 NVIDIA GPU·드라이버와
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)이 준비되어 있어야 합니다.
Laya는 판정 엔진 컨테이너, DeciFlow는 로그 분석·웹 UI 컨테이너입니다.

### 1. 저장소 준비

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
# 기존 .env가 없다면 / Only if .env does not exist
test -f .env || cp .env.example .env
```

### 2. Laya GPU 컨테이너 실행

```bash
bash scripts/run-deciflow-laya-cuda.sh
docker logs --follow DeciFlow-Laya
```

최초 모델 다운로드·로딩이 끝나면 로그 보기만 `Ctrl+C`로 종료합니다.
[준비 상태 확인](#laya-health) 후 다음 단계로 진행하세요.

### 3. DeciFlow 설정 및 컨테이너 실행

`.env`에서 아래 값을 설정합니다. `<HOST_IP>`는 두 컨테이너를 실행하는 호스트의
접근 가능한 IP로 바꾸세요. 컨테이너 안의 `127.0.0.1`은 Laya 호스트 주소가 아닙니다.

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://<HOST_IP>:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

```bash
docker build --tag call518/deciflow-ui:0.0.1 .
bash scripts/run-deciflow-ui.sh
```

### 4. 샘플 로그 분석

같은 호스트에서 **http://127.0.0.1:4000**을 열고 **Batch**를 선택합니다.
소스는 `/host-logs/sample-logs/access-100.log` 하나만 남기고 **HTTP access** 기준,
**Events/chunk: 1**, **Action: None**으로 분석을 시작하세요.

GPU가 없다면 [Laya CPU](#laya-docker), 유료 API를 사용하려면 [Jev](#jev)를 참고하세요.
기본 키 `changeme`는 체험용입니다. 운영 전 Laya 스크립트와 `.env`의 키를 함께 변경하세요.

## 사용법과 설정

| 문서 | 내용 |
| --- | --- |
| [사용법](docs/usage.ko.md) | 입력 모드·판정 기준·필터·수동 검토·재접속·시간 지표 |
| [설정](docs/configuration.ko.md) | 환경변수·모델·입력 예산 |
| [Criteria](docs/criteria.ko.md) | 고정 5개 범주 프로필 관리; Default Criteria는 보기 전용 |
| [Python Actions](docs/actions.ko.md) | 구성 보기·환경 Status·pip 포함 환경·Reset venv·리비전 이력·삭제·소스 할당 |
| [결과 JSON](docs/results.ko.md) | 실제 응답 예시·필드 설명 |

사이드바 화면은 URL에 반영됩니다: Main `/`, Criteria `/#criteria`, Actions `/#actions`.
새로고침·뒤로가기·직접 링크에서도 해당 화면을 유지합니다.

- **Paste:** 텍스트를 붙여 넣어 분석합니다.
- **Batch:** 기존 파일을 분석합니다. Docker에서 호스트 `/var/log`는 `/host-logs/var/log`입니다.
- **Realtime:** 새 로그를 감시합니다. 소스별 판정 기준과 청크 크기를 선택합니다.
- **처리 지표:** Success / Failed / Total로 성공·실패·처리 완료 전체 청크를 표시합니다. Action Success / Failed / Total은 후속 작업을 별도 집계합니다. Needs review는 성공 판정만 집계합니다.
  엔진·모델 옆 연결 상태는 마지막 실제 요청 기준이며 요청 전에는 Not checked입니다.
- **검토:** Needs review로 결과를 추리고 수동 정정·JSON 내보내기를 사용합니다.
  Certain은 정확도 보장이 아닙니다. 서버 재시작 시 작업·결과가 사라지므로 필요하면 내보내세요.

## Docker 배포 상세

<a id="laya-docker"></a>

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

**`call518/deciflow-laya-cpu:0.0.1`** 또는 **`call518/deciflow-laya-cuda:0.0.1`**를 사용합니다.
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

스크립트는 **8000** 포트, `english`·`multilingual`·`typed-decisions` 사전 적재,
`deciflow-laya-model-cache` 공유 볼륨을 사용합니다. CUDA는 컨테이너에 모든 GPU를
노출합니다. 호스트 인터페이스·포트는 `--publish 호스트_IP:호스트_포트:8000`을
수정하고 `LAYA_API_URL`에도 반영하세요. 두 스크립트 모두 `DeciFlow-Laya`를 사용하므로
CPU·CUDA 전환 또는 설정 변경 전에 기존 컨테이너를 중지·제거합니다.

> **NOTE:** Docker Compose로 구성하려면 공식
> [Laya Docker 문서의 HTTP serving 항목](https://nandhakishorm.github.io/laya/docker/#http-serving)을 참고하세요.

<a id="laya-health"></a>

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

#### DeciFlow 연결 설정

DeciFlow 실행 노드의 `.env`에 공용 Laya 서버 URL과 서버와 동일한 API 키를 설정하세요:

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

<a id="jev"></a>

### Jev 엔진 사용

[Jev 설정 안내](https://docs.typesafe.ai/introduction/quickstart)에서 TypeSafe API 키를
발급받아 `.env`에 설정하세요. Jev는 유료이며 Laya 서버는 필요하지 않습니다.

```dotenv
DECISION_ENGINE=jev
JEV_MODEL=jev-1.13.0
JEV_API_KEY=your-typesafe-api-key
PORT=4000
```

### DeciFlow Docker

부록의 **Python 직접 실행 대신 이 방식을 선택**합니다. DeciFlow 호스트에는 Docker만
필요하며 로컬 Python·uv·CUDA는 필요하지 않습니다. 먼저 `.env`에 Laya 또는 Jev를
설정하세요. Laya 추론은 기존의 별도 Laya 서버가 처리합니다.

Git clone한 DeciFlow 디렉토리에서 아래 명령을 실행하세요. 이미지는 Python·uv와 운영 유틸리티를 제공하며, 저장소는 `/app`에 읽기 전용으로 마운트합니다. 시작할 때
`uv sync --frozen`이 현재 버전의 의존성을 별도 Docker 볼륨에 설치합니다.
최초 실행에는 패키지 다운로드를 위한 네트워크 연결이 필요합니다.

```bash
docker build --tag call518/deciflow-ui:0.0.1 .
bash scripts/run-deciflow-ui.sh
```

실행 스크립트는 UI를 `0.0.0.0:4000`에 공개하고 샘플 로그도 마운트합니다.
`deciflow-data` 볼륨은 `/var/lib/deciflow-data`에 연결하며 Actions는 `actions/`,
Criteria는 `criteria/`에 저장합니다. 로컬 체험만 허용하려면 publish 주소를
`127.0.0.1:4000:4000`으로 변경하세요. 포트·마운트 변경 후에는 컨테이너를 다시 생성합니다.

**http://127.0.0.1:4000**에 접속하세요. 호스트의 `/var/log`는 Batch·Realtime에서
`/host-logs/var/log/messages` 같은 `/host-logs/var/log` 경로로 사용합니다. 다른 디렉토리도 필요하면 읽기 전용으로 마운트하세요.
`.env`의 `PORT`가 다르면 실행 스크립트의 호스트·컨테이너 포트를 모두 변경합니다.
원격 접속은 DeciFlow 호스트 IP를 사용하며 파일 접근 출처 설정도 아래 안내를 따릅니다.

#### 호스트 로그 디렉터리 연결

DeciFlow 컨테이너가 호스트의 로그를 읽으려면 해당 디렉터리를 읽기 전용으로
마운트해야 합니다. 실행 스크립트는 `/var/log`와 저장소의 `sample-logs`를 이미
연결합니다. 다른 로그 디렉터리는 `scripts/run-deciflow-ui.sh`의 `docker run` 옵션에
아래 항목을 추가하세요. `/your/logs`는 분석할 호스트 로그 디렉터리로 바꿉니다.

```bash
--mount type=bind,src=/your/logs,dst=/host-logs/custom,readonly \
```

마운트 변경 후 기존 컨테이너를 중지·제거하고 스크립트를 다시 실행합니다.
서버 메모리의 작업·결과는 사라지므로 필요한 결과는 먼저 내보내세요.

```bash
docker stop DeciFlow-UI
docker rm DeciFlow-UI
bash scripts/run-deciflow-ui.sh
```

UI에는 호스트 경로 `/your/logs/app.log` 대신 **컨테이너 경로
`/host-logs/custom/app.log`**를 입력합니다. `readonly`는 컨테이너에서 호스트 로그를
수정하지 못하게 하며, DeciFlow 프로세스에는 해당 파일을 읽을 권한이 필요합니다.

#### 연결 설정과 재시작

Laya URL은 컨테이너에서 접근 가능한 주소를 사용하세요. `127.0.0.1`은 호스트나
원격 Laya 서버가 아닌 컨테이너 자신입니다. 사이드바의 호스트·OS·IP 정보는
컨테이너를 나타냅니다. DeciFlow가 시작할 때마다 마운트된 `/app/.env`를 읽습니다.
Docker `--env`로 지정한 값은 `.env`보다 우선합니다. `.env` 수정 후 재시작하세요:

```bash
docker restart DeciFlow-UI
```

기존 `--env-file .env` 방식의 컨테이너는 새 이미지를 빌드하고 위 명령으로
한 번만 재생성해야 합니다. 포트 매핑·마운트 변경 시에는 여전히 재생성이 필요합니다.
소스 수정이나 Git 버전 변경은 `docker restart DeciFlow-UI`로 적용하며 이미지 재빌드는
필요하지 않습니다. UI 변경 후에는 브라우저도 새로고침하세요. Dockerfile의 실행 환경을
바꿀 때만 이미지를 다시 빌드합니다. 버전 전환 전에는 DeciFlow를 중지하세요.

ngrok·리버스 프록시로 파일을 처리하려면 `DECIFLOW_CSRF_TRUSTED_ORIGINS`에
정확한 UI 출처 또는 랜덤 ngrok 주소용 `https://*.ngrok-free.app`을 지정하고
컨테이너를 재시작하세요(끝에 `/` 제외). 빈 값은 localhost 파일 접근만 허용합니다.
이 설정은 CSRF Origin 검사에 사용하며 CORS·로그인 인증·CSRF 토큰 검증은 아닙니다.
와일드카드는 다른 사용자의 하위 도메인도 신뢰하므로 공개 접속에는 프록시 인증을 적용하세요.

## 제약

- 앱의 파일 크기·줄 수 제한은 없지만 RAM과 브라우저 용량에 영향을 받습니다.
  파일은 점진적으로 읽습니다. 청크는 이벤트 수로 묶으며 현재 비어 있지 않은 한 줄이 1이벤트입니다.
  멀티라인 이벤트 경계는 자동 인식하지 않습니다.
- **Laya:** 선택한 체크포인트를 사용하며 요청 윈도·질문 예산은 [설정 상세](docs/configuration.ko.md)을 따릅니다.
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
백그라운드 작업도 종료하며 서버 메모리의 작업과 결과는 사라집니다.

## Appendix — 추가 활용 가능성

로그 분석은 출발점입니다. 입력 처리와 판정 기준을 확장하면 `tcpdump` 기반 실시간
네트워크 트래픽 감시나 센서·검사 데이터를 활용한 제조 공정의 양품·불량 판정에도
같은 흐름을 적용할 수 있습니다. 이들 활용에는 추가 연동과 분야별 검증이 필요하며,
이미지 검사에는 비전 모델 연동도 필요합니다.

## Appendix — 호스트 직접 실행

Docker 실행 대신 선택합니다. DeciFlow 호스트에 Python 3.11+와 uv가 필요합니다.
Laya Docker 서버 또는 Jev 연결 설정은 동일하며, 별도 Laya 서버를 사용하면 DeciFlow에 GPU가 필요하지 않습니다.
저장소에서 `.env`를 준비하고 선택한 엔진을 설정한 뒤 실행하세요.

```bash
uv sync
uv run python server.py
```

**http://127.0.0.1:4000**을 엽니다. 첫 기동에 기본 Criteria 파일을 생성하므로 공통 데이터 경로에 쓰기 권한이
필요합니다. 기본 `/var/lib/deciflow-data`에 쓸 수 없다면 `.env`에서
`DECIFLOW_DATA_DIR=./data`를 설정하세요. 설정 변경 후 DeciFlow를 재시작합니다.

## Appendix — Docker run 커스텀 이미지(선택)

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
