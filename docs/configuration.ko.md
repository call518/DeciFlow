# 설정

[English](configuration.md) | [한국어](configuration.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

DeciFlow 운영 설정은 **Settings → Configurations**에서 수정할 수 있습니다.
UI 저장값 → `.env`/프로세스 환경변수 → 코드 기본값 순으로 적용합니다.
**Use UI Override**를 해제하면 환경변수/기본값으로 복원합니다. 초기 환경은 `.env`에서 준비합니다.
Laya 서버 설정은 Laya 호스트에서 관리하며, Compose는 `LAYA_API_KEY`를 DeciFlow와
공유합니다. `COMPOSE_PROFILES`는 `cpu` 또는 `cuda`를 선택하며 빈 값이면 로컬 Laya를 실행하지 않습니다.

## 환경 파일 위치

추천 순서는 **PyPI / uv tool → Docker Compose → Git 복제 기반 네이티브 Python**이며
실행 방식 하나를 선택합니다. PyPI 설치 방법은
[uv tool 안내](tool-install.ko.md)를 따르세요.
아래 `<checkout>`은 호스트에 복제한 DeciFlow 저장소 루트입니다.

| 방식 | DeciFlow가 읽는 파일 | 준비·선택 방법 |
| --- | --- | --- |
| PyPI / uv tool | `~/.config/deciflow/.env` | `deciflow init`으로 샘플 생성 후 수정 |
| Git clone + Docker Compose | 호스트 `<checkout>/.env`, UI 컨테이너 내부 `/app/.env`로 마운트 | `<checkout>/.env.example`을 `<checkout>/.env`로 복사하고 저장소에서 Compose 실행 |
| Git clone + 네이티브 Python | `<checkout>/.env` | 샘플 복사 후 `uv run deciflow run --config-dir "$PWD"`, `uv run --extra laya python laya_server.py`가 같은 파일을 읽음 |

uv tool의 `~`는 명령 실행 사용자의 홈입니다. 따라서 root는
`/root/.config/deciflow/.env`를 사용합니다. `--config-dir /path/to/deciflow-config`를
지정하면 `init`, `config list`, `config test`, `run`, `status`, `stop` 모두
`/path/to/deciflow-config/.env`를 사용하므로 매번 같은 옵션을 전달하세요.
현재 셸 디렉터리의 `.env`를 자동 선택하지 않으며, 초기화는 기존 파일을 보존합니다.

Git 네이티브 CLI는 저장소에서 실행하고 `--config-dir "$PWD"`로 경로를 명시해야 합니다.
생략하면 저장소 안에서도 `~/.config/deciflow`를 사용합니다. `server.py` 직접 실행은
셸 위치와 관계없이 저장소의 파일을 읽습니다. Source 상대 경로를 명확히 하려면
안내된 명령을 저장소에서 실행하세요. 로컬 Laya 어댑터도 같은 파일을 읽지만,
별도 배포한 Laya 서버는 해당 호스트의 자체 설정을 사용합니다.

Compose는 저장소 파일을 변수 치환과 UI의 `env_file`에 사용하고, DeciFlow는 기동 시
마운트된 `/app/.env`도 읽습니다. `docker compose --env-file ...`만 지정해도 UI의
`env_file`이나 마운트된 `/app/.env`가 바뀌지는 않으므로 uv tool 설정 파일로
Docker 배포 전체를 전환하는 방법이 아닙니다. `--config-dir`은 DeciFlow CLI 옵션이며
Compose나 `server.py` 옵션이 아닙니다.

각 파일은 독립적이며 자동 검색·동기화·대체 사용을 하지 않습니다. 설치형 명령으로 기존
네이티브 저장소 파일을 의도적으로 재사용하려면 `--config-dir /path/to/DeciFlow`를 지정하세요.
Docker의 `http://laya:8000`은 해당 네트워크 내부 주소이므로 호스트에서 실행할 때는
접근 가능한 Laya URL을 설정해야 합니다.

설정 파일 위치와 `DECIFLOW_DATA_DIR`·`DECIFLOW_LOG_DIR`은 별개입니다. 기본값은
데이터 `/var/lib/deciflow-data`(빈 값도 동일), 로그 `/var/log/deciflow`를 유지합니다.
Docker는 컨테이너 내부 경로를 이름 있는 볼륨으로 보존하고, uv tool·네이티브는 호스트
디렉터리를 사용합니다. 네이티브 빠른 시작은 명시적으로 `./data`·`./logs`로 덮어씁니다.

## 환경 설정

| 환경변수 | 미설정 시 코드 기본값 | 역할 |
| --- | --- | --- |
| `COMPOSE_PROFILES` | 미설정(로컬 Laya 미실행) | Compose 전용. cpu·cuda 중 하나만 선택. .env.example은 cpu 지정 |
| `OAUTH2_PROXY_ENABLED` | `false` | true: Google 로그인·HTTPS, false: 인증 없는 HTTP 데모. Docker·네이티브 공통 |
| `DECIFLOW_BIND_HOST` | `127.0.0.1` | OAuth2-Proxy 비활성 시 HTTP 주소. 0.0.0.0은 외부 접속 허용; 활성 시 UI 포트 미공개 |
| `DECISION_ENGINE` | `laya` | `laya` 또는 `jev` |
| `DECIFLOW_DATA_DIR` | `/var/lib/deciflow-data` | Sources·Tasks/이력·Actions·Criteria·SSH 키·호스트 공통 저장 루트; 쓰기 권한 필요 |
| `DECIFLOW_CSRF_TRUSTED_ORIGINS` | 빈 값 | 쉼표로 구분한 신뢰 UI 출처. https://*.ngrok-free.app 지원. 출처 검사이며 인증 기능은 아님. OAuth2-Proxy 활성 시 OAUTH2_PROXY_PUBLIC_URL 사용 |
| `DECIFLOW_LOG_DIR` | `/var/log/deciflow` | 서버·접근 로그. 빈 값은 파일 기록 비활성화. Compose는 deciflow-logs에 보존 |
| `PORT` | `4000` | UI 수신 포트. OAuth2-Proxy 비활성 시 Docker도 같은 포트를 공개 |
| `OAUTH2_PROXY_PUBLIC_URL` | OAuth2-Proxy 활성 시 필수 | :4443을 포함한 공개 HTTPS 출처. 콜백·신뢰 UI 출처 설정 |
| `OAUTH2_PROXY_CLIENT_ID` | OAuth2-Proxy 활성 시 필수 | Google 웹 애플리케이션 클라이언트 ID |
| `OAUTH2_PROXY_CLIENT_SECRET` | OAuth2-Proxy 활성 시 필수 | Google 클라이언트 비밀값. Git 제외된 .env에 보관 |
| `OAUTH2_PROXY_COOKIE_SECRET` | OAuth2-Proxy 활성 시 필수 | 무작위 32바이트를 Base64 인코딩한 쿠키 키 |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | 프록시 접두사를 포함한 전체 Laya URL. Compose CPU·CUDA는 모두 `http://laya:8000/v1/systemone`, 네이티브 실행은 루프백 사용 |
| `LAYA_API_KEY` | `changeme` | Laya 서버와 동일한 키 |
| `LAYA_MODEL` | `multilingual` | 내장 모델 또는 등록한 사용자 체크포인트 이름; 서버에 모델 필요 |
| `LAYA_MAX_TOKENS` | 빈 값 | `max_len`으로 전달; 빈 값은 내장 모델 기본값 유지, 사용자 모델은 필수 |
| `LAYA_HEAD_TOKENS` | `256` | `head_max_len`으로 전달; 질문·선택지 예산이며 전체 윈도 미만 |
| `LAYA_CONCURRENCY` | `4` | 실행별 최대 Laya 동시 요청 수; 양의 정수 |
| `JEV_API_KEY` | 미설정 | Jev API 키 |
| `JEV_MODEL` | `jev-1.13.0` | TypeSafe 지원 버전 ID 또는 `jev-latest` 등의 별칭 |
| `JEV_MAX_INPUT_BYTES` | `30000` | Jev 요청 JSON의 UTF-8 바이트 예산; 1~30000 허용 |
| `JEV_CONCURRENCY` | `4` | 실행별 최대 Jev 동시 요청 수; 양의 정수 |

`.env.example`은 일부 코드 기본값을 덮어씁니다. LAYA_API_URL은 Compose 호스트
`laya`, LAYA_MODEL은 `multilingual`, JEV_MODEL은 `jev-latest`입니다. 신뢰 UI 출처는
기본적으로 비워두며 `https://*.ngrok-free.app`은 선택적 예시입니다. 기존 `.env` 값은
덮어쓰지 않습니다. 네이티브 DeciFlow·외부 Laya는 접근 가능한 URL을 직접 설정하세요.
CPU·CUDA 모두 8000 포트를 공개합니다.
재시작 후에도 UI 저장값이 우선합니다. UI 시작 시 마운트된 `.env`에 명시한 `DECISION_ENGINE`·`LAYA_*`·`JEV_*` 값은
기존 엔진 환경변수보다 우선합니다. 환경 파일의 엔진 설정·인증정보를 변경한 후에는
**Restart DeciFlow**, Docker Desktop의 DeciFlow-UI Restart 또는 `docker compose restart ui`를
실행하고 브라우저를 새로고침하세요.
파일에 없는 항목은 기존 환경값을 유지합니다. 다른 설정의 환경변수 우선순위는
유지합니다. 포트·마운트·Compose 프로필·Laya 서비스 변경은 `docker compose up -d`로
해당 컨테이너를 재생성해야 합니다. 네이티브 실행은 Python 프로세스를 재시작하세요.
state·세 질문·출력은 [요청·결과 JSON](results.ko.md)을 참고하세요.

OAuth2-Proxy 모드·수신 주소 변경 후 Docker는 `docker compose up -d --remove-orphans`,
네이티브는 DeciFlow를 종료한 뒤 다시 실행하세요. 인증 없는 외부 HTTP는 접근 가능한
누구나 관리 기능을 사용할 수 있습니다.

OAuth 값은 UI 재정의가 아닌 배포 설정입니다. Google 클라이언트 ID·비밀값 또는 쿠키 키를
바꾸면 `docker compose up -d --force-recreate oauth2-proxy`로 적용하세요.
**Restart DeciFlow**만으로 프록시 설정은 갱신되지 않습니다.
`OAUTH2_PROXY_PUBLIC_URL` 변경 시 Google 등록 원본·리디렉션 URI도 바꾸고
`docker compose up -d ui oauth2-proxy`를 실행하세요. 파일·인증서 갱신은
[인증 운영 안내](authentication.ko.md#운영)를 참고하세요.

`LAYA_HEAD_TOKENS=384`이면 매 Laya 요청에 `"head_max_len": 384`를 전송합니다.
`LAYA_MAX_TOKENS=1024`는 `"max_len": 1024`를 전송합니다. 해당 요청에서
체크포인트 기본값을 덮어씁니다. `.env` 변경은 위 실행 방식별 절차로 적용하세요.
DeciFlow 설정이므로 이 값을 전송하기 위해 원격 Docker를 변경할 필요는 없습니다.

**내장 모델은 `LAYA_MAX_TOKENS=`를 비워두는 것을 권장합니다.** DeciFlow가
`LAYA_MODEL`에 따라 English 512, Multilingual·Typed-decisions 8192를 자동 적용합니다.
빈 값이면 내장 모델을 바꿀 때 `LAYA_MODEL`만 변경하고 토큰 예산은 수정하지 않아도
됩니다. 사용자 모델은 예산을 명시해야 합니다. 숫자를 직접 지정하면 자동 선택 대신
그 값을 사용합니다. English는 최대 512,
다른 모델은 최대 8192를 허용합니다. 질문 예산은 양의 정수이며 전체 윈도 미만이어야
합니다. 256은 기본값이며 Laya API 최대값이 아닙니다. 이는 **DeciFlow 검증 범위**입니다.
공식 체크포인트 기본값은 English 512/192, 나머지 1024/256 토큰입니다.
서버는 별도로 `LAYA_MAX_TOKEN_BUDGET`(기본 8192)을 두 예산에 적용하며 초과하면
422를 반환합니다. 요청 예산은 결과 JSON의 `inputBudget`에 기록됩니다.

예산은 고정 예약량이 아닙니다. 실제 로그 공간은 렌더링된 질문에 따라 달라지므로
단순히 `max_len - head_max_len`으로 계산하면 안 됩니다. `usage.truncated`는 로그
잘림 정보이며 지시문 전체 보존을 뜻하지 않습니다. Laya가 범주 선택지의 구별 손실을
보고하면 DeciFlow는 Uncertain·Needs Review로 표시하고 이유를 보여줍니다.
원래 판정 범주·확률·응답은 그대로 보존합니다.

사용자 체크포인트는 원격 서버의 `LAYA_EXTRA_MODELS`에 이름을 등록한 뒤
`LAYA_MODEL`에 그 이름을 넣고, 검증한 입력 용량 내에서 `LAYA_MAX_TOKENS`를
명시하세요. 이름은 영문자로 시작하며 영문자·숫자·`_`·`-`를 허용합니다.
URL·경로는 받지 않습니다. 응답의 `routing.model`이 지정한 사용자 모델을
확인해 주지 않으면 거절하여 다른 모델로 조용히 전환되는 것을 막습니다.
DeciFlow가 모델을 설치하거나 학습하지는 않습니다.

동시 요청 수는 Batch·Realtime Task와 직접 API 요청에 적용됩니다. Laya v0.4.1 추론 워커는
1개입니다. `LAYA_CONCURRENCY`는 클라이언트 요청 수, 서버 `LAYA_MAX_CONCURRENT`는
수용 제한입니다(기본 16, 초과하면 503). GPU 추론 병렬도 설정은 아닙니다.
잘림·라우팅 정보를 위해 서버 `LAYA_JEV_STRICT=0`을 유지하고 CPU `LAYA_THREADS`는
물리 코어 수 이하로 설정하세요. 파일 Batch는 여전히 개별 요청을 전송하며
실제 추론 배치 API를 사용하지 않습니다.

Jev는 Laya 예산을 무시합니다. Jev API는 `head_max_len`에 해당하는 옵션이 없으며
Jev 1.13은 state + 가장 긴 질문 32k, 전체 요청 64k 토큰 제한을 적용합니다.
`JEV_MAX_INPUT_BYTES`는 보수적 바이트 검사이며 토큰 할당량이 아닙니다.
Jev 모델 가용성은 계정·API에 따르며 별칭의 제한은 바뀔 수 있습니다.

요청 검증과 서버 설정은 [Laya 연동](laya-integration.ko.md)을
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


## 애플리케이션 영구 데이터

`DECIFLOW_DATA_DIR` 아래에서 다음 파일을 관리합니다:

| 경로 | 내용 |
| --- | --- |
| `deciflow.sqlite3` | Source·Criteria·Task·Action·SSH Host·SSH Key 메타데이터·일반 설정·실행 스냅샷·결과·리뷰·집계(SQLite WAL) |
| `actions/<name>-<id>/` | Action 코드·venv·프로젝트·잠금 파일 |
| `ssh-keys/<key-id>/` | 관리되는 개인키와 파생 공개키 |
| `ssh-hosts/known_hosts` | DeciFlow에서 명시적으로 승인한 호스트 키 |


전체 디렉터리를 백업하고 접근 권한을 관리하세요. 원본 로그·개인키가 포함됩니다.
실행 이력은 자동 정리하지 않으며 데이터 경로마다 DeciFlow 프로세스 하나를 사용합니다.
엔진 동시 요청 제한은 실행의 모든 소스 Hosts가 공유하고 서로 다른 Task는 별도 제한을
사용합니다. 예약·저장 제약은 [Tasks](tasks.ko.md)를 참고하세요.

실행 중 DB 파일 하나만 복사하면 WAL의 데이터가 빠질 수 있습니다. 서버를 중지한 뒤 전체 데이터 경로를 백업하거나 SQLite 백업 API를 사용하세요. [결과 저장](result-storage.ko.md)을 참고하세요.

## DeciFlow 초기화

**Settings → Configurations → Reset DeciFlow**를 엽니다. 사이트 디자인의 확인창에
삭제 항목과 실제 `DECIFLOW_DATA_DIR` 경로를 표시합니다. Cancel·Escape·닫기는
변경하지 않습니다. **Yes, Reset DeciFlow**는 스케줄러·Task·Action 하위 프로세스를
중지하고 SQLite를 닫은 뒤 해당 디렉토리 내부 항목과 숨김 파일을 영구
삭제하되 `ssh-keys` 폴더와 키 등록 정보(ID·이름)는 보존합니다. 디렉토리 자체는 유지하며 내부 심볼릭 링크의 외부 대상은 삭제하지 않습니다.

Sources·Tasks·Actions 및 가상환경·사용자 Criteria·결과/이력/리뷰·관리 SSH Hosts·
승인한 known_hosts·저장 설정이 삭제됩니다. 필요한 데이터는 먼저 백업하고 결과·리뷰를
내보내세요. 앱 파일·`.env`·Laya/모델 캐시·데이터 디렉토리 밖의 입력/로그는 유지합니다.
설정한 데이터 디렉토리는 DeciFlow 전용으로 사용하세요.

서버는 원래 Python 실행 명령으로 프로세스를 교체하므로 Docker 소켓이나 제어 권한이
필요하지 않습니다. 데이터 디렉토리당 서버 프로세스 하나를 사용해야 합니다.
샘플 Criteria·샘플 Sources·비활성 기본 Task·기본 설정으로 복구하고 브라우저는 새 서버
인스턴스를 확인해 새로고침합니다. 삭제 요청은 자동 재시도하지 않습니다. 삭제가
불완전하면 재시작 후 붉은 오류를 표시하므로 재시도 전에 서버 로그를 확인하세요.
기존 Task 정의도 삭제되므로 기존 실행은 자동 재개하지 않습니다.

신뢰 UI Origin에서만 `POST /api/reset/status`로 경로·서버 인스턴스를 조회하고,
`POST /api/reset`에 `{ "confirmation": "RESET DECIFLOW" }`를 보내 초기화합니다.
HTTP 202 응답 후 정상 종료를 시작하며 초기화 중 중복 요청은 거부합니다.
보호된 시스템/프로젝트 경로와 데이터 루트 심볼릭 링크는 거부합니다.
파일·Action 관리와 같은 신뢰 출처 경계를 사용하므로 신뢰하지 않는 사용자에게
노출하지 마세요.

**Settings → Configurations**에서 설정들을 수정한 뒤 맨 아래 **Save Changes**로 한 번에 반영합니다. **Reset DeciFlow**는 별도의 확인창을 거쳐 즉시 실행하는 동작입니다.

## 런타임 설정

**Configurations → Save Changes**는 페이지 크기와 선택한 런타임 설정을 SQLite에
한 번에 저장합니다. Decision Engine, Laya URL·모델·전체/질문 토큰 예산·동시 요청 수,
Jev 모델·요청 바이트 예산·동시 요청 수, OpenAI Criteria 작성 모델을 지원합니다.
각 항목에는 환경변수명, 적용 출처·시점, 간단한 도움말과 `.env.example`의 영문
상세 설명을 제공합니다. 저장 전에 두 엔진의 적용 설정을 검증합니다. Jev 선택에는
`JEV_API_KEY` 설정과 비용 확인이 필요하며 자동 대체 엔진을 사용하지 않습니다.
저장 후 브라우저를 새로 고쳐 반영하며 서버 재시작은 필요 없습니다.

새 실행부터 저장값을 사용합니다. 실행 중인 작업은 시작 당시 엔진·모델·URL·예산·동시
요청 수를 유지합니다. 새로 시작한 복구 가능 실행에는 이 비밀값 없는 설정을 저장하여
Configurations가 바뀌어도 원래 설정으로 복구합니다. 스냅샷이 없는 기존 실행은
엔진·모델 변경 시 복구를 중단하는 기존 정책을 유지합니다. 인증정보는 환경변수에서
읽으며 실행 스냅샷에 저장하지 않습니다. AI Criteria 생성도 요청 시작 시 설정을 사용합니다.

API 키(`LAYA_API_KEY`, `JEV_API_KEY`, `OPENAI_API_KEY`)는 `.env`에 남기고 UI에는
설정 여부만 표시합니다. 포트·데이터/로그 경로·신뢰 출처·Compose 프로필은 배포 환경에서
관리하며 Environment and Deployment에 편집 없이 설명합니다. 원격 Laya의 모델 적재·GPU·
워커·포트·볼륨은 해당 호스트/컨테이너에서 관리합니다. UI 저장은 `.env`를 수정하지 않습니다.

## DeciFlow 재시작

**Reset DeciFlow** 아래 **Restart DeciFlow**는 데이터를 삭제하지 않고 DeciFlow의
Python 프로세스만 재시작합니다. 확인창은 활성 실행 수와 미저장 설정 변경을 안내합니다.
취소·Escape는 아무 작업도 하지 않습니다. 실행 중인 작업은 체크포인트와 함께 일시 중단하고,
조건을 충족하는 활성 Task는 원래 ID·설정으로 복구합니다. 일시정지 상태는 유지하며 기존
Task 복구 규칙을 적용합니다. 외부 추론은 이미 공급자에 전달되었을 수 있고 Action은 기존의
보수적 복구 정책을 따릅니다. 무중단이나 정확히 한 번 실행을 보장하는 기능은 아닙니다.

UI는 확인한 재시작 요청을 한 번만 보내고 최대 60초 동안 새 서버 인스턴스를 기다린 뒤
새로 고칩니다. 서버가 돌아오지 않으면 오류를 표시하므로 로그 확인 후 직접 새로 고치세요.
동시 Reset/Restart는 거부합니다. 재시작은 마운트된 `.env`의 엔진·인증정보 항목을 다시
읽지만 Laya 재시작·모델 적재나 Docker 포트·볼륨·프로필·GPU 변경은 수행하지 않습니다.
그런 변경은 해당 컨테이너를 재생성하세요. 원래 실행 명령으로 프로세스를 교체할 수 있는
실행 방식이 필요하며 데이터 디렉터리당 프로세스 하나를 사용하세요.

`POST /api/configuration`은 비밀값 없는 설정 정보를 조회합니다. `PUT /api/configuration`은
`resultsPerPage`와 `runtimeOverrides`(지원하는 비밀값 없는 환경변수명만)를 받습니다.
`POST /api/restart`는 `{ "confirmation": "RESTART DECIFLOW" }`를 요구하며 202를 반환합니다.
앱은 신뢰 출처를 검사합니다. `OAUTH2_PROXY_ENABLED=true`이면 Docker·네이티브 모두
OAuth2-Proxy가 UI·API 요청에 Google 로그인을 요구합니다. false이면 로그인 없이 사용합니다. [인증 안내](authentication.ko.md)를 참고하세요.


## 로그

`DECIFLOW_LOG_DIR`는 DeciFlow 로그 디렉터리이며 기본값은 `/var/log/deciflow`입니다.
이 파일들은 운영 로그입니다. 원본 입력 로그·판정·Action 결과는 Task History와
결과 저장소에서 확인합니다.

| 파일 | 내용과 용도 | 보존 정책 |
| --- | --- | --- |
| `access.log` | HTTP 클라이언트 주소·메서드·요청 경로·응답 상태. 실패한 요청을 찾는 출발점입니다. HTTP 200이어도 응답의 분석 결과나 스트림 이벤트는 실패일 수 있습니다. | 10 MiB마다 회전, 백업 5개 유지 |
| `server.log` | Uvicorn 시작·종료·경고·처리되지 않은 요청 예외와, 처리된 엔진 설정·저장소/I/O·Criteria 생성·파일 스트림·백그라운드 작업·초기화 실패 진단. error.log 역할을 하며 정보 메시지도 포함합니다. | 10 MiB마다 회전, 백업 5개 유지 |
| `daemon.log` | `deciflow run --daemon`이 생성합니다. 시작 검사·일반 표준 출력/오류·관리 중인 OAuth2-Proxy 출력을 수집합니다. 기동·Google 로그인 실패 시 확인합니다. Uvicorn 서버·접근 로그는 전용 파일에만 기록하여 여기에 중복하지 않습니다. | 재실행 시 이어 쓰기, 자동 회전 없음 |

포그라운드와 Docker 실행은 서버·접근 파일과 함께 Uvicorn 콘솔 출력도 유지합니다.
Docker는 `daemon.log`를 만들지 않습니다. OAuth2-Proxy 활성화 시 컨테이너 콘솔·프록시
출력은 `docker compose logs ui oauth2-proxy`로 확인합니다. Laya 로그는 별도 서비스에서 확인합니다.

문제 조사 시 `access.log`에서 요청과 시각을 찾고 같은 시각의 `server.log`를 확인하세요.
애플리케이션 실패 진단은 작업 위치·예외 종류·코드 위치와 사용 가능한 OS/SQLite 오류 코드를
기록합니다. 자격 증명이나 입력 데이터가 복사되지 않도록 예외 값·소스 코드 줄·지역 변수·
요청 본문·공급자 응답 본문은 기록하지 않습니다. 래핑된 예외는 직접 원인을 우선 사용하며,
전체 예외 원문을 제공하지 않습니다.

일반적인 입력 검증 실패·접근 거부·항목 없음은 보통 HTTP 상태와 응답에서만 확인합니다.
개별 이벤트의 분류·Action 실패와 SSH Host 수집 상세는 결과 및 Task History에서 확인합니다.
엔진 상태 검사는 연결 상태를 UI에 반환합니다. 모든 4xx/5xx가 별도 진단을 생성하지 않으며,
스트림 실패는 HTTP 200 이후에도 발생할 수 있습니다. Uvicorn의 미처리 예외 추적·접근 URL·
외부 프록시 출력은 자동으로 마스킹하지 않으므로 로그 파일을 보호하고 공유 전에 검토하세요.

`DECIFLOW_LOG_DIR`가 비어 있으면 서버·접근 파일 기록을 끄고 콘솔 출력을 유지합니다.
데몬 모드에는 비어 있지 않은 기존의 쓰기 가능한 디렉터리가 필요합니다. 상대 경로는
DeciFlow 작업/설정 디렉터리 기준입니다. `daemon.log`는 호스트에서 회전 정책을 설정하세요.
Compose는 `deciflow-logs`에 서버·접근 로그를 보존합니다. 호스트 디렉터리에서 접근하려면
쓰기 가능한 바인드 마운트를 사용하세요. 로그 설정 변경 후 DeciFlow를 재시작하세요.
