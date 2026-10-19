# 설정

[English](configuration.md) | [한국어](configuration.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

DeciFlow 설정은 `.env`에서 관리하며 프로세스 환경변수가 우선합니다.
Laya 서버 설정은 Laya 호스트에서 관리하며, Compose는 `LAYA_API_KEY`를 DeciFlow와
공유합니다. `COMPOSE_PROFILES`는 `cpu` 또는 `cuda`를 선택하며 빈 값이면 UI만 실행합니다.

| 환경변수 | 미설정 시 코드 기본값 | 역할 |
| --- | --- | --- |
| `COMPOSE_PROFILES` | 미설정(UI만 실행) | Compose 전용. cpu·cuda 중 하나만 선택. .env.example은 cpu 지정 |
| `DECISION_ENGINE` | `laya` | `laya` 또는 `jev` |
| `DECIFLOW_DATA_DIR` | `/var/lib/deciflow-data` | Sources·Tasks/이력·Actions·Criteria·SSH 키·호스트 공통 저장 루트; 쓰기 권한 필요 |
| `DECIFLOW_CSRF_TRUSTED_ORIGINS` | 빈 값 | 쉼표로 구분한 신뢰 UI 출처. https://*.ngrok-free.app 지원. 출처 검사이며 인증 기능은 아님 |
| `DECIFLOW_LOG_DIR` | `/var/log/deciflow` | 서버·접근 로그. 빈 값은 파일 기록 비활성화. Compose는 deciflow-logs에 보존 |
| `PORT` | `4000` | DeciFlow 웹 포트 |
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
`laya`, LAYA_MODEL은 `english`, JEV_MODEL은 `jev-latest`이며 신뢰 UI 출처에
`https://*.ngrok-free.app`을 포함합니다. 기존 `.env` 값은
덮어쓰지 않습니다. 네이티브 DeciFlow·외부 Laya는 접근 가능한 URL을 직접 설정하세요.
CPU·CUDA 모두 8000 포트를 공개합니다.
UI 시작 시 마운트된 `.env`에 명시한 `DECISION_ENGINE`·`LAYA_*`·`JEV_*` 값은
기존 엔진 환경변수보다 우선합니다. 변경 후 Docker Desktop에서 DeciFlow-UI를
Restart하거나 `docker compose restart ui`를 실행하고 브라우저를 새로고침하세요.
파일에 없는 항목은 기존 환경값을 유지합니다. 다른 설정의 환경변수 우선순위는
유지합니다. 포트·마운트·Compose 프로필·Laya 서비스 변경은 `docker compose up -d`로
해당 컨테이너를 재생성해야 합니다. 네이티브 실행은 Python 프로세스를 재시작하세요.
state·세 질문·출력은 [요청·결과 JSON](results.ko.md)을 참고하세요.

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
