# 개발과 릴리즈

[English](development.md) | [프로젝트 소개](../README.ko.md) | [설치](../INSTALL.ko.md)

개발 명령은 [소스 직접 실행 설치](../INSTALL.ko.md#direct-processes)로 준비한
Git 저장소 루트에서 프로젝트 uv 환경으로 실행합니다. PyPI 명령 설치만으로는
테스트 저장소가 준비되지 않습니다.

관리자는 [태그 릴리즈 워크플로](development.ko.md#git-태그로-게시)로
태그와 같은 버전을 TestPyPI·PyPI에 게시한 뒤, 직전 게시된 Release 이후의 커밋
메시지를 담은 GitHub Release를 생성합니다.

모델 평가 명령·보고서·한계는 [Laya 검증](laya.ko.md#evaluation)에 모았습니다.

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

최소 지원 버전은 Python 3.11이며, 개발에는 Python 3.12를 권장하고 Docker 실행 환경도
3.12를 사용합니다. GitHub Actions는 push마다 Ubuntu에서 Python 3.11과 3.12 각각으로
전체 pytest를 실행하며, 개인 `.env`나 운영 인증 정보는 사용하지 않습니다.
저장소의 **Actions → Pytest**에서
결과를 확인하고, **Run workflow**로 수동 실행할 수도 있습니다.

OAuth2-Proxy 테스트의 다운로드·오프라인 준비는 [인증 테스트](#authentication-tests)를 참고하세요.

Action 테스트는 세션당 한 번 PyPI·패키지 인덱스에서 버전이 고정된 `pip`,
`setuptools`, `wheel` 파일을 임시 저장소에 준비합니다. 이후 Action 환경 설치는
테스트 중인 Python 버전과 로컬 인덱스를 사용하여 오프라인으로 수행합니다.
테스트는 임시 데이터·로그 경로와 자체 Compose 설정을 사용하므로 root 권한이나
개인 `.env`가 필요하지 않습니다.

UI 회귀 테스트(Node.js는 테스트에만 필요):

```bash
node --test tests/test_ui.mjs
```

테스트는 유료 호출 없이 두 제공자, 입력 예산, 스트리밍, 취소, 파일 탐색·회전을
확인합니다. 두 README와 실제·예제 `.env`를 함께 관리하며 환경변수 주석은
영어와 한국어를 병기합니다.

로컬 Laya 설치·기동은 [네이티브 안내](../INSTALL.ko.md#direct-processes)에서 설명합니다.

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)

## Git 태그로 게시

관리자용 `.github/workflows/pypi-publish.yml`은 태그 push 시 Python 3.12 테스트,
sdist·wheel 빌드, 태그와 패키지 버전 일치 검사, 설치된 wheel 검증을 수행합니다.
동일한 배포 파일을 **TestPyPI에 먼저** 게시하고 성공한 경우에만 **PyPI**에 게시합니다.
마지막 별도 작업은 PyPI 성공 후에만 동일한 태그의 GitHub Release를 영문 머리말과 함께 생성합니다.
일반 브랜치 push는 패키지나 Release를 게시하지 않으며, 별도 pytest 워크플로는
Python 3.11·3.12를 검사합니다.

`pyproject.toml`은 `dynamic = ["version"]`과 Hatch의 `hatch-vcs` 플러그인
(내부적으로 `setuptools-scm` 사용)을 적용합니다. 변경 사항 없는 `0.5.7` 또는
`v0.5.7` 태그에서 빌드하면 패키지 버전은 `0.5.7`입니다. 이는 예시이며 실제 릴리즈
버전을 지정한 것은 아닙니다. `0.5.7rc1`과 같은 표준 사전 릴리즈 태그도 허용하며
두 인덱스에 모두 게시합니다. 태그 이후 커밋이나 수정된 저장소에서는 개발 버전이
생성됩니다. CI는 버전 판별을 위해 전체 Git 이력을 가져옵니다. 수동 버전 수정이나
API 토큰은 필요하지 않습니다. 저장소에서 빌드할 때는 Git이 필요하며, 게시된 sdist는
버전 메타데이터를 보존하므로 sdist에서 wheel을 빌드할 때 Git 이력이 필요하지 않습니다.

첫 태그 push 전에 다음을 준비하세요.

1. GitHub 저장소 **Settings → Environments**에 `testpypi`와 `pypi` 환경을
   설정합니다. 배포 제한에서 릴리즈 태그를 허용해야 합니다. 필수 검토자를 지정하면
   해당 게시 작업은 승인을 기다립니다.
2. **각** 인덱스에 프로젝트 `deciflow`, 소유자 `call518`, 저장소 `DeciFlow`,
   워크플로 `pypi-publish.yml`, 해당 환경(`testpypi` 또는 `pypi`)으로
   Trusted Publisher를 등록합니다. Pending Publisher는 첫 업로드 성공 시 프로젝트를
   생성하며 프로젝트 이름을 예약하지는 않습니다.
3. 이 워크플로를 포함한 릴리즈 변경 사항을 커밋한 뒤, 해당 커밋에 원하는 버전 태그를
   생성하고 push합니다. 워크플로가 없는 과거 커밋을 태그로 push하면 새 게시 절차가
   적용되지 않습니다.

패키지 게시는 GitHub OIDC를 사용하며 인덱스 게시 작업에만 `id-token: write`를
부여합니다. GitHub Release 작업에만 `contents: write`를 부여하고 자동 제공되는
`GITHUB_TOKEN`을 사용합니다. 개인 토큰이나 저장소 전체의 쓰기 기본 권한은 필요하지
않습니다. 워크플로는 태그나 커밋을 생성하지 않습니다.

릴리즈노트는 병합 커밋·호환성 변경 설명을 포함한 **커밋 메시지 전체**를 오래된
위상 순서부터 커밋 링크와 함께 수집합니다. 기준은 직전 Git 태그가 아니라 가장 최근에
**게시된 GitHub Release**입니다. 게시된 사전 릴리즈도 기준에 포함하며 초안과 현재
태그는 제외합니다. Release가 없는 중간 태그 때문에 수집 범위가 줄어들지 않습니다.
게시된 Release가 없으면 현재 태그에서 도달 가능한 전체 이력을 포함합니다.
커밋 메시지는 번역·요약하지 않고 원문 그대로 보존합니다.

Release 작업은 원격 태그·로컬 태그·체크아웃 커밋의 일치를 확인하며, 직전 Release
태그가 없거나 현재 태그의 조상이 아니면 중단합니다. 재실행 시 기존 게시된 Release는
변경하지 않고, 같은 태그의 초안이 있으면 수동 검토가 필요합니다. `aN`·`bN`·`rcN`으로
끝나는 태그는 prerelease로 생성하며 Latest로 지정하지 않습니다. 정식 Release의
Latest는 GitHub가 자동 선택합니다. Release 작업만 직렬화하며 최대 100개의 대기 작업을
유지합니다. 버전 태그는 한 번에 하나씩 push하세요. 동시 또는 역순 게시에서는 새 Release가
이전 버전 태그의 잘못된 기준이 될 수 있으며, 추측하여 게시하지 않고 안전하게 실패합니다.

이미 게시된 패키지 버전은 덮어쓸 수 없습니다. TestPyPI 성공 후 PyPI가 실패하면 원인을
해결하고 같은 워크플로 실행에서 실패한 작업을 재실행하여 기존 배포 파일을 사용하세요.
GitHub Release 생성만 실패하면 실패한 Release 작업만 재실행하고 성공한 패키지 업로드는
재실행하지 마세요. Release 실패는 이미 인덱스에 게시된 패키지를 되돌리지 않습니다.
설치나 로컬 검증은 업로드하지 않습니다. `python3 -m scripts.publish_release TAG`는
워크플로용 게시 명령입니다.


## 배포 파일 검증

Git 저장소에서 sdist와 wheel을 빌드한 뒤 wheel을 검증합니다.

```bash
uv build
uv run python scripts/check_distribution.py dist/*.whl
```

출력 디렉터리에는 검증할 wheel 하나만 두세요. 검증은 저장소 밖의 임시 uv tool
환경에 설치하고, UI 리소스 포함·개인 파일 제외를 확인한 뒤 설치된 서버를
기동·재시작·종료합니다. 의존성 다운로드 연결이 필요하며 추론 요청은 보내지 않습니다.
GitHub Actions도 Python 3.11과 3.12 각각에서 pytest 후 이 검증을 실행합니다.


<a id="authentication-tests"></a>

## 인증 스모크 테스트

준비된 Git 저장소 루트에서 실행합니다.

로컬 자동 스모크 테스트는 Linux/macOS amd64/arm64용 OAuth2-Proxy v7.15.5를
자동 다운로드하고 고정된 공식 SHA-256으로 검증합니다. 압축 파일은 저장소 밖의
`~/.cache/deciflow/test-tools/`에 캐시하며 실행 파일·테스트 인증서는 pytest 임시
디렉터리에 생성합니다. OpenSSL과 최초 실행 시 GitHub 접근이 필요하며 검증된 캐시는
재다운로드하지 않습니다. 다운로드·체크섬 오류는 생략하지 않고 테스트 실패로 처리합니다.

```bash
uv run pytest -q tests/test_oauth2_proxy.py
```

오프라인 환경이거나 기존 실행 파일을 사용하려면 절대 경로를 지정하세요.

```bash
OAUTH2_PROXY_BINARY=/path/to/oauth2-proxy uv run pytest -q tests/test_oauth2_proxy.py
```

이 테스트는 일회용 로컬 설정·자체 서명 테스트 인증서를 사용하며 Google에 접속하거나
실제 자격 증명을 사용하지 않습니다. 테스트 전용 공개 경로로 스트림 중계도 확인합니다.
실제 Google 계정 허용·거부와 운영 HTTPS는 [접근 검증](authentication.ko.md#verify)을 별도로 수행해야 합니다.


<a id="storage"></a>

## 저장소 구현

`ResultRepository`는 결과 저장 인터페이스이며 `open_result_store()`가 현재 유일한
구현인 `SQLiteResultStore`를 선택합니다. 설정 SQL은 `config_store.py`에 있습니다.
PostgreSQL·MySQL 구현이나 접속 설정은 없습니다. 운영·백업 절차는
[설정](configuration.ko.md#storage), 외부 JSON 계약은 [결과 JSON](results.ko.md)에 둡니다.

- 정의는 내부 ID별 레코드로 저장하고 중첩 필드는 JSON으로 보존합니다. 번들 프로필은
  `deciflow/profiles/`의 읽기 전용 초기값이며 샘플 초기화는 애플리케이션 시작 시 수행합니다.
- `result_decisions`에는 판정 선택값·구간·Choice 확실성을 인덱싱합니다. 필터·커서 조회를
  서버에서 적용하며 브라우저는 현재 페이지만 유지합니다. 부분 문자열 검색은 여전히 많은
  행을 조회할 수 있으므로 일정한 CPU 비용을 보장하지 않습니다.
- 실행 객체는 최근 이벤트 최대 128건을 캐시하고 완료 객체 캐시는 32개를 넘으면 제거합니다.
  저장된 이력은 남습니다. 활성 파일·호스트·개별 이벤트·동시성·SQLite/OS 캐시는 메모리를
  사용하지만 누적 결과 전체를 메모리에 보존하지 않습니다.
- 집계는 증분 갱신합니다. `processing_times`에는 실행별 서로 다른 처리 시간당 한 행을
  저장하여 정확한 Median·P95·P99를 계산합니다. 처리량은 성공 건수를 활성 분류 시간으로
  나눈 값입니다. 실행 지표는 표시 필터와 무관하며 차트는 일치하는 전체 결과를 집계합니다.
- 내보내기는 시작 커서까지 제한된 크기의 배치로 스트리밍합니다. 검토된 결과는 부분
  인덱스로 조회하며 전체 결과와 `reviewerDecisions`를 별도 결과 저장소 없이 반환합니다.
- `pending_work` 삽입과 `source_checkpoints` 전진, 결과 저장과 대기열 제거는 각각 하나의
  트랜잭션입니다. Action 의도·결과를 별도 기록하여 불확실한 외부 효과를 자동 반복하지
  않습니다. Criteria·Action 스냅샷은 해당 실행에 고정됩니다.
- 원문은 한 번 저장하고 반복 Criteria·진단 질문은 `result_contexts`에 해시로 공유합니다.
  조회·검토·재생·내보내기에서 정의를 복원하며 캐시는 제한합니다. 독립 Action·내보내기
  JSON에는 필요한 정의를 포함합니다. `log_folded`는 검색용 의도적 사본입니다.
- SQLite는 WAL·FULL 동기 커밋·연결 캐시 2 MiB를 사용합니다. Task 삭제 시 히스토그램과
  공유 정의도 제거합니다. 읽기는 저장된 원본이나 Elasticsearch 문서를 다시 쓰지 않습니다.

## Docker 런타임과 이미지 상세

#### DeciFlow Docker

Docker 또는 [네이티브 설치](../INSTALL.ko.md#direct-processes) 중 하나를 선택합니다. DeciFlow 호스트에는
Compose가 포함된 Docker가 필요하며 로컬 Python·uv·CUDA는 필요하지 않습니다.
먼저 `.env`에 Laya 또는 Jev를 설정하세요. 외부 Laya 또는 Jev를 사용하면
`COMPOSE_PROFILES=`로 두고 선택한 접근 모드로 실행합니다:

```bash
docker compose up -d
```

Compose는 Docker Hub에 공개된 `call518/deciflow-ui:0.0.2` 이미지를 사용합니다.
이미지는 Python·uv와 운영 유틸리티를 제공합니다. 저장소는 `/app`에 읽기 전용으로
마운트하며, 시작할 때 `uv sync --frozen`으로 `deciflow-venv` 볼륨에 의존성을 설치합니다.
최초 실행에는 네트워크 연결이 필요합니다. Compose가 `.env`를 UI에 전달하며
`PORT`는 UI 포트(기본값: 4000)입니다. HTTP 모드는 `DECIFLOW_BIND_HOST`에
해당 포트를 공개하고 OAuth2-Proxy 모드는 HTTPS 4443만 공개합니다.
`pull_policy: always`로 `up` 실행 시마다 이미지 업데이트를 확인합니다.
UI·Laya 서비스는 `extra_hosts`로 `host.docker.internal`을 Docker 호스트 게이트웨이에 연결합니다. 기존 컨테이너에는 재생성 후 적용됩니다.

<a id="docker-runtime"></a>

##### Dockerfile과 Compose의 역할

[`Dockerfile`](../Dockerfile)은 `python:3.12-slim`을 기반으로 uv `0.7.20`과 운영 도구를
설치하고 작업 디렉터리를 `/app`으로 지정합니다. PyArrow `23.0.1`에서 사용할 Java와
Apache Hadoop `3.5.0` 클라이언트 라이브러리(`libhdfs`), PATH의 `hdfs`·`hadoop` 명령도 포함합니다. Hadoop 배포 파일은
고정한 SHA-512 체크섬으로 검증하며 빌드 시 Linux amd64·arm64 바이너리를 선택합니다.
`core-site.xml`·`hdfs-site.xml`·환경 스크립트·정책·SSL 예제를 포함한 표준 Hadoop 설정
템플릿은 `/etc/hadoop/conf`에 설치합니다. 로깅 기본값은 stderr의 WARN이며 클러스터
주소와 인증 정보는 미리 설정하지 않습니다.
앱 소스나 프로젝트 의존성은 이미지에
미리 포함하지 않습니다. 시작 명령은 `uv sync --frozen --no-dev --no-install-project --no-cache`
이후 `server.main(host='0.0.0.0')`을 실행합니다. 따라서 공개된 UI 이미지에도 복제한
저장소를 `/app`에 마운트해야 합니다. 추론은 UI 이미지가 아닌 Laya 또는 Jev가 처리합니다.
SSH 키 관리와 원격 파일 요구사항은 [Sources](sources.ko.md)를 참고하세요.

HDFS Source는 **HDFS (Native)**·**HDFS (WebHDFS)** 방식으로 UTF-8 TEXT·JSONL 파일의
Batch 읽기를 지원합니다. 클러스터 마운트,
인증과 실행 제한은 [HDFS 설정](sources.ko.md#hdfs)을 참고하세요.
HDFS 서버 없이 PyArrow/JVM/libhdfs 로딩과 파일 읽기를 확인하려면 로컬에서 빌드한
이미지로 다음을 실행하세요. 임시 컨테이너는 자체 가상환경을 사용합니다.

```bash
docker build --tag deciflow-ui:hdfs-runtime-check .
docker run --rm --mount type=bind,src="$PWD",dst=/app,readonly \
  deciflow-ui:hdfs-runtime-check sh -c \
  'uv sync --frozen --no-dev --no-install-project --no-cache && /opt/deciflow-venv/bin/python scripts/check_hdfs_runtime.py'
```

이 검사는 JNI와 `hdfs dfs -ls`로 Hadoop의 로컬 파일시스템을 사용합니다. HDFS 연결, Kerberos 인증,
실제 클러스터와의 호환성을 검증하지는 않습니다.

[`docker-compose.yml`](../docker-compose.yml)은 실행 구성을 제공합니다:

| 항목 | 동작 |
| --- | --- |
| `name: deciflow` | 소문자 Compose 프로젝트·그룹 이름. 개별 컨테이너 이름은 DeciFlow 표기 유지. |
| `ui` | 항상 활성화. 공개 UI 이미지가 없으면 다운로드하고 .env·PORT·소스·로그·데이터 마운트를 적용. 빌드 단계 없음. |
| `laya-cpu` / `laya-cuda` | COMPOSE_PROFILES=cpu 또는 cuda로 선택. laya 네트워크 별칭·8000 포트 공유. CUDA만 GPU 요청. |
| `oauth2-proxy` | OAUTH2_PROXY_ENABLED=true일 때 DeciFlow-OAuth2-Proxy로 실행. 4443에 HTTPS를 공개하고 승인된 사용자를 ui로 중계. |
| `x-laya` | Laya 공통 설정을 재사용하는 YAML 앵커이며 별도 컨테이너가 아님. |
| 이름 있는 볼륨 | deciflow-venv·deciflow-data·deciflow-logs·deciflow-laya-model-cache의 기존 이름 유지. |

Compose는 `.env`를 변수 치환에 사용하고 `env_file`로 UI에 전달합니다.
Laya에는 명시한 서버 변수만 전달하며 `LAYA_API_KEY`는 같은 설정을 공유합니다.
변수 치환 시 프로세스 환경변수가 `.env`보다 우선합니다. `COMPOSE_PROFILES`는
`DECISION_ENGINE`과 독립적이므로 Jev·외부 Laya 사용 시 프로필을 비우세요. UI는 계속 실행되며 OAuth2-Proxy는 OAUTH2_PROXY_ENABLED에 따릅니다. UI가 Laya 준비 전에 시작할 수 있으므로 로그 분석 전 준비 상태를
확인하세요. 유료 엔진으로 자동 전환하지 않습니다.

OAuth2-Proxy 활성 시 HTTPS 4443만 공개하고 `OAUTH2_PROXY_PUBLIC_URL`로 접속합니다.
비활성 시 `http://localhost:4000` 또는 설정한 HTTP 주소·포트로 접속합니다.
별도 Laya API는 8000을 유지합니다.
`deciflow-data` 볼륨은 `DECIFLOW_DATA_DIR`(기본값: `/var/lib/deciflow-data`)에
Sources·Tasks와 실행 이력·Actions·Criteria·SSH 키 쌍·SSH Host를 저장하고, `deciflow-logs`는 서버 로그를 저장합니다.
사용자 지정 데이터·로그 디렉터리는 컨테이너 안의 절대 경로로 설정하세요.

##### 호스트 로그 디렉터리 연결

호스트 `/var/log`와 저장소의 `sample-logs`를 `/host-logs/var/log`,
`/host-logs/sample-logs`에 읽기 전용으로 연결합니다. 다른 로그를 읽으려면
`docker-compose.yml`의 `services.ui.volumes`에 추가하세요:

```yaml
      - /your/logs:/host-logs/custom:ro
```

`docker compose up -d ui`로 마운트 변경을 적용합니다. UI 재생성은 진행 중 실행을
중단하며 Task 이력은 데이터 볼륨에 보존합니다. UI에서는 컨테이너 경로
`/host-logs/custom/app.log`를 사용합니다. 프로세스에는 호스트 파일을 읽을 권한이 필요합니다.

##### 연결 설정과 재시작

UI 저장값은 `.env`보다 우선합니다. 변경한 환경값을 사용하려면 해당 Use UI Override를 해제하세요.

Compose Laya 주소는 `http://laya:8000/v1/systemone`입니다. 외부 서버는 컨테이너에서
접근 가능한 주소를 사용하세요. `127.0.0.1`은 UI 컨테이너 자신입니다.
사이드바의 호스트·OS·IP 정보도 컨테이너를 나타냅니다.
`.env`의 엔진 설정(`DECISION_ENGINE`·`LAYA_*`·`JEV_*`)은 Docker Desktop에서
Configurations의 **Restart DeciFlow**, DeciFlow-UI Restart 또는 `docker compose restart ui`를 실행한 뒤 브라우저를
새로고침하면 적용됩니다. UI가 시작할 때 마운트된 파일의 엔진 설정을 다시 읽습니다.
포트·마운트·Compose 프로필·Laya 서비스 설정은 `docker compose up -d`로
해당 컨테이너를 재생성해야 합니다.
소스 변경은 `docker compose restart ui`로 적용하고 UI 변경 후 브라우저를 새로고침하세요.
Dockerfile을 수정한 경우에만 `docker build --tag call518/deciflow-ui:0.0.2 .`로
UI 이미지를 직접 빌드한 뒤 `docker compose up -d --force-recreate ui`로 적용합니다.
소스 버전 전환 전에는 DeciFlow를 중지하세요.

OAuth2-Proxy 활성 시 Compose는 HTTPS 포트를 포함한
`OAUTH2_PROXY_PUBLIC_URL`을 UI 신뢰 출처로 지정합니다.
이 URL을 변경하면 Google 승인 원본·리디렉션 URI도 바꾸고
`docker compose up -d ui oauth2-proxy`로 적용하세요.
`DECIFLOW_CSRF_TRUSTED_ORIGINS`로 추가 UI 출처를 허용할 수 있으며 공개 URL을 대체하지는 않습니다.
네이티브 네트워크·인증 설정은 [네이티브 안내](../INSTALL.ko.md#direct-processes)를 참고하세요.
인증정보·허용 목록·인증서 변경은 [인증 운영 안내](authentication.ko.md#verify)를 참고하세요.

### Appendix — Docker 커스텀 이미지(선택)

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

`docker-compose.yml`에서 선택한 Laya 서비스의 이미지를 커스텀 태그로 바꾸세요.
`cpu`는 CPU 전용 PyTorch, `cu130`은 CUDA **13.0**을 뜻합니다. GPU·드라이버와
Dockerfile의 `TORCH_VERSION`에 맞는 CUDA 빌드를
[PyTorch 설치 목록](https://pytorch.org/get-started/previous-versions/)에서 선택하세요.
Laya 업그레이드 시 API 호환성을 검증합니다.

### Docker 업데이트와 종료

컨테이너만 중지하려면 `docker compose stop`, 구성의 컨테이너·네트워크를 제거하려면
`docker compose down`을 사용합니다. `down`은 이름 있는 데이터 볼륨을 보존합니다.
결과가 필요하면 `--volumes`를 추가하지 마세요. 소스 업데이트 전에는 실행을 중지하고
필요한 데이터·설정을 백업한 뒤 저장소 루트에서 실행합니다.

```bash
docker compose down
git pull --ff-only
docker compose up -d --remove-orphans
```

기존 `.env`는 다시 복사하지 말고 바뀐 설정만 검토하세요. `pull_policy: always`가
설정된 이미지를 확인하고, UI는 마운트된 새 소스를 사용합니다. 엔진 준비 상태를
다시 확인하고 UI를 새로고침하세요. Dockerfile 수정은 위 절차와 별도로 이미지를
빌드해야 하며 [실행 이미지 상세](#docker-runtime)를 따릅니다.
