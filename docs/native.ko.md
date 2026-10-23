# Git 복제 기반 네이티브 설치

[English](native.md) | [프로젝트 README](../README.ko.md) | [문서 안내](README.ko.md)

DeciFlow를 로컬에서 실행하고 브라우저로 샘플 로그를 분류합니다.
이 로컬 절차에는 Docker·도메인·인증서가 필요하지 않습니다.
이 방식은 [PyPI / uv tool](tool-install.ko.md),
[Docker Compose](../README.ko.md#대안-설치-docker--laya-cpu) 다음인 세 번째 권장 방식입니다.
하나를 선택하며, 이 안내에서는 Git 저장소의 스크립트를 직접 실행합니다.

**DeciFlow**는 소스를 읽고 UI·API를 제공합니다. **Laya 서버**는 로컬·원격에서
추론하며 **Jev**는 대안인 유료 호스팅 추론 서비스입니다. **OAuth2-Proxy**는
브라우저 접근을 보호할 수 있지만 별도로 실행하는 네이티브 프로세스입니다.
같은 설치에서는 Compose 배포 대신 네이티브 실행을 선택하세요.

## 환경 파일

`server.py`와 로컬 `laya_server.py` 어댑터는 모두 복제한 저장소 루트의
`<checkout>/.env`를 읽으며 `~/.config/deciflow/.env`는 읽지 않습니다.
안내된 명령은 저장소에서 실행하세요. 설치형 명령의 `--config-dir` 옵션으로
소스 스크립트의 참조 파일이 바뀌지는 않습니다.
[환경 파일 위치](configuration.ko.md#환경-파일-위치)를 참고하세요.

## 빠른 시작: 로컬 CPU

Git·[uv](https://docs.astral.sh/uv/getting-started/installation/)·잠긴 의존성과 호환되는
Python 3.11 이상, 의존성·모델 다운로드 연결이 필요합니다.
Linux·WSL2 기준 예시이며 GPU는 필요하지 않습니다. 최초 Laya 모델 다운로드·적재는
수 분 걸릴 수 있습니다. Laya 서버가 이미 있다면 [기존 엔진 사용](#기존-엔진-사용)을 선택하세요.

### 1. 저장소 준비

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
test -f .env || cp .env.example .env
uv sync --frozen --extra laya
```

### 2. 로컬 실행 설정

`.env`의 기존 항목을 수정합니다. 다른 값과 예제의 항목 순서·주석은 유지하세요.

```dotenv
OAUTH2_PROXY_ENABLED=false
DECIFLOW_BIND_HOST=127.0.0.1
DECISION_ENGINE=laya
PORT=4000
DECIFLOW_DATA_DIR=./data
DECIFLOW_LOG_DIR=./logs
DECIFLOW_CSRF_TRUSTED_ORIGINS=
LAYA_API_URL=http://127.0.0.1:8000/v1/systemone
LAYA_MODEL=multilingual
LAYA_MAX_TOKENS=
LAYA_HEAD_TOKENS=512
```

저장소의 로컬 Laya 어댑터는 DeciFlow와 동일한 `.env`의 API 키를 읽습니다.
다른 Laya 서버에는 해당 서버와 일치하는 `LAYA_API_KEY`를 지정하세요.
Compose의 `laya` 호스트 이름과 `/host-logs` 마운트는 Docker 밖에서 사용할 수 없습니다.
위 네이티브 명령은 `COMPOSE_PROFILES`를 사용하지 않습니다. `OAUTH2_PROXY_ENABLED=false`이면 OAuth 값을
비워 둬도 됩니다. 외부 HTTP 접속에는 `DECIFLOW_BIND_HOST=0.0.0.0`과
`DECIFLOW_CSRF_TRUSTED_ORIGINS`의 공개 브라우저 출처를 설정하고 재시작하세요.
접근 가능한 누구나 모든 데이터를 관리할 수 있습니다.

### 3. Laya와 DeciFlow 시작

저장소 루트에서 터미널 A로 실행합니다.

```bash
uv run --extra laya python laya_server.py
```

로컬 어댑터를 `127.0.0.1:8000`에서 시작합니다. 프로세스 환경값으로 장치를
바꾸지 않으면 CPU를 사용합니다. 모델 적재가 끝날 때까지 기다리세요.
이 어댑터는 토큰 예산을 검사하고 Laya API에 잘림 메타데이터를 제공합니다.

같은 저장소에서 터미널 B로 실행합니다.

```bash
uv run --extra laya python server.py
```

두 명령에 `--extra laya`를 지정해 동일한 환경을 유지합니다.
DeciFlow는 기본 `127.0.0.1:4000`에서 수신하며 두 터미널을 열어 두세요.

### 4. 첫 결과 확인

**http://127.0.0.1:4000**을 엽니다. 이 로컬 절차에는 Google 로그인이 없습니다.

1. **Sources**의 **Sample HTTP access**를 수정해 저장소의
   `sample-logs/access-100.log` 실제 절대 경로를 지정합니다.
2. **Tasks**에 **Batch / Manual** Task를 추가하고 해당 Source,
   **Sample HTTP access** Criteria, **Events/Chunk: 1**, **Action: None**을 선택합니다.
3. 저장·활성화한 뒤 **Run**을 누르면 Main에 결과가 표시됩니다.

Source에는 절대 경로를 사용하세요. Docker 전용 `/host-logs/sample-logs/...`는
동작하지 않습니다. 시작 시 생성되는 Elasticsearch Action은 이 데모에 필요하지 않습니다.
시작 과정에서 해당 Python 환경·모듈을 다운로드할 수 있지만 Task의 Action이 None이면
Elasticsearch 서버는 필요하지 않습니다. 다른 사용 흐름은 [사용법](usage.ko.md)을 참고하세요.

### 5. 종료와 재시작

터미널 B에서 `Ctrl+C`로 DeciFlow를 종료하고 터미널 A에서 Laya를 종료합니다.
같은 명령을 다시 실행하면 됩니다. Source·설정·실행 이력은 `./data`, 로그는
`./logs`에 남습니다. 체크포인트가 있는 활성 실행은 복구할 수 있으며 일시정지는
유지됩니다. [Task 복구](tasks.ko.md#서버-재시작-후-복구)를 참고하세요.
환경값을 바꾸면 해당 네이티브 프로세스를 재시작합니다.

## 기존 엔진 사용

로컬 Laya 기동 대신 아래 중 하나를 선택합니다. DeciFlow 호스트에 로컬 모델·GPU·
`laya` 추가 의존성은 필요하지 않습니다. 위 1–2단계를 따르되 설치 명령은
`uv sync --frozen --extra laya` 대신 `uv sync --frozen`을 사용하세요.

| 엔진 | `.env` 설정 |
| --- | --- |
| 기존 Laya | `DECISION_ENGINE=laya`, `/v1/systemone`을 포함한 접근 가능한 `LAYA_API_URL`, 동일한 `LAYA_API_KEY`·모델 |
| Jev | `DECISION_ENGINE=jev`, 본인의 `JEV_API_KEY`와 지원하는 `JEV_MODEL`. API 호출은 과금됨 |

동일 호스트의 Laya에는 `http://127.0.0.1:8000/v1/systemone`, 원격 서버에는 실제
접근 가능한 URL을 지정합니다. 유료 Jev로 자동 전환하지 않습니다.
2단계의 쓰기 가능한 데이터·로그 경로를 유지하고 아래만 실행하세요.

```bash
uv run python server.py
```

같은 로컬 UI를 열고 앞의 샘플 절차를 따릅니다.

## 선택: OAuth2-Proxy를 통한 네이티브 HTTPS

`OAUTH2_PROXY_ENABLED=true`로 설정하면 같은
`uv run --extra laya python server.py` 명령이 OAuth2-Proxy도 자동 실행합니다.
DeciFlow는 루프백에 유지되며 OAuth2-Proxy가 외부 HTTPS를 수신합니다.

```text
Browser → OAuth2-Proxy HTTPS :4443 → DeciFlow HTTP 127.0.0.1:4000 → Laya or Jev
```

1. OS·아키텍처에 맞는 공식 [OAuth2-Proxy v7.15.5 바이너리](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.5)를
   PATH에 설치하고 릴리즈 체크섬을 검증하세요.
2. [DNS·TLS 준비](dns-tls.ko.md)에 따라 도메인과 신뢰할 수 있는 인증서를 준비합니다.
   Docker deploy hook은 네이티브에 적용하지 않습니다. 실제 인증서 파일을
   `oauth2-proxy/tls/`에 두고 네이티브 실행 사용자가 개인 키를 읽도록 소유권·600 권한을
   지정하세요. Docker UID 65532는 네이티브 소유권 규칙이 아닙니다.
3. [Google 등록·이메일 허용 목록](authentication.ko.md)을 설정합니다. `.env`의
   클라이언트 ID·비밀값·쿠키 키를 채운 뒤 다음을 지정하세요.

```dotenv
OAUTH2_PROXY_ENABLED=true
OAUTH2_PROXY_PUBLIC_URL=https://deciflow.example.com:4443
```

터미널 B에서 같은 명령으로 DeciFlow를 다시 실행합니다. 기존 엔진을 사용한다면 앞의
안내처럼 `--extra laya`를 제외하세요. 실행기가 네이티브 경로·설정한 `PORT`·콜백·신뢰
출처를 자동 지정합니다. OAuth 설정과 개인 파일은 Git에서 제외하며 내부 UI 포트를
공개하지 마세요. 설정·바이너리 누락이나 OAuth2-Proxy 종료 시 실행을 중단하고 HTTP로 자동 전환하지 않습니다.

공개 HTTPS URL에서 승인·미등록 계정과 쿠키 없는 `/api/status` 요청(401)을 확인합니다.
`Ctrl+C`는 DeciFlow와 OAuth2-Proxy를 함께 종료하며 터미널 A의 Laya는 유지합니다.
UI Restart/Reset도 OAuth2-Proxy를 정리한 뒤 DeciFlow를 다시 실행합니다.

모드 전환이나 인증정보·인증서·허용 목록·정책 변경 시 터미널 B를 `Ctrl+C`로 종료하고
파일을 수정한 뒤 같은 명령으로 실행하세요. 인증서 자동 갱신 반영에는 호스트의 서비스
관리자로 네이티브 배포를 재시작하세요. Docker 재생성 명령으로 관리되지 않으며
프로젝트가 네이티브 서비스 unit을 자동 설치하지 않습니다.

## 문제 해결

| 증상 | 확인 |
| --- | --- |
| 데이터·로그 권한 오류 | `./data`·`./logs` 또는 쓰기 가능한 네이티브 경로 |
| 모델 다운로드·적재가 느림 | 터미널 A 상태. 최초 적재에는 다운로드 연결·충분한 메모리 필요 |
| 엔진 접속 실패 | Laya 실행·준비 상태, 네이티브 URL·API 키. `laya`는 Compose에서만 조회됨 |
| Source를 찾지 못함 | `/host-logs/...` 대신 호스트의 절대 경로 |
| 네이티브 OAuth2-Proxy 경유 UI API가 403 | `DECIFLOW_CSRF_TRUSTED_ORIGINS`의 공개 HTTPS 출처. 수정 후 DeciFlow 재시작 |
| OAuth2-Proxy 인증서 읽기 실패 | 네이티브 경로·개인 키 소유권과 권한 |
| 포트 사용 중 | 다른 설치를 종료하거나 관련 포트를 일관되게 변경 |

HDFS 네이티브 Source에는 호스트의 Java·Hadoop·libhdfs도 필요합니다.
[Sources](sources.ko.md#hdfs)의 요구사항을 따르세요. 로컬 TEXT 샘플에는 필요하지 않습니다.
엔진 설정 상세는 [설정 안내](configuration.ko.md)를 참고하세요.
