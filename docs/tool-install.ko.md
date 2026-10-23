# DeciFlow 명령 설치

[English](tool-install.md) | [프로젝트 README](../README.ko.md)

가장 권장하는 설치 방식입니다. PyPI에 게시된 후에는 저장소를 복제하거나 Docker를
사용하지 않고 실행할 수 있습니다. 두 번째는 [Docker](../README.ko.md#빠른-시작--docker--laya-cpu),
세 번째는 [Git 복제 기반 네이티브](native.ko.md)이며 설치별로 하나를 선택합니다.

**DeciFlow**는 UI/API를 제공하고 소스를 읽습니다. **Laya 서버**는 별도로 추론을
수행하며, **Jev**는 대안으로 선택할 수 있는 유료 추론 API입니다.
DeciFlow 설치가 Laya를 기동하거나 OAuth2-Proxy를 설치하지는 않습니다.

## 설치와 초기 설정

[uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.11 이상
(3.12 권장), 의존성 다운로드 연결이 필요합니다. 기준 환경은 Linux/WSL2입니다.
HDFS·SSH·Actions의 외부 준비 사항은 해당 기능 문서를 따릅니다.

이 브랜치는 아직 PyPI에 게시하지 않았습니다. 현재 구현을 테스트하려면
해당 Git 저장소에서 실행합니다.

```bash
uv tool install .
deciflow init
```

본 프로젝트의 배포 파일이 PyPI에 게시된 후에는 다음과 같이 설치합니다.

```bash
uv tool install deciflow
deciflow init
```

셸에서 `deciflow`를 찾지 못하면 `uv tool update-shell`을 실행하고 새 셸을 여세요.

`deciflow init`은 소유자만 읽고 쓸 수 있는 `~/.config/deciflow/.env`와
OAuth2-Proxy 샘플 파일을 준비합니다. 설정 검사나 서버 기동은 하지 않습니다.
생성된 파일을 수정한 뒤 `deciflow`를 실행하세요.
기존 설정 파일은 덮어쓰지 않습니다. `OAUTH2_PROXY_ENABLED=false`이면
도메인·인증서·Google 설정이 필요하지 않습니다.
기본 경로는 명령 실행 사용자의 홈을 기준으로 하므로 root는
`/root/.config/deciflow/.env`를 사용합니다. 저장소나 현재 디렉터리의 `.env`를
자동으로 읽지는 않습니다. 설치 방식을 바꾸기 전에
[환경 파일 위치](configuration.ko.md#환경-파일-위치)를 확인하세요.

## 엔진 연결과 기동

엔진은 **하나를 선택**합니다. [네이티브 Laya 안내](native.ko.md)나 기존 배포 방식으로
별도의 Laya 서버를 기동한 뒤 다음 항목을 설정합니다.

```dotenv
DECISION_ENGINE=laya
LAYA_API_URL=http://127.0.0.1:8000/v1/systemone
LAYA_API_KEY=your-laya-server-key
```

실제 Laya 서버의 주소와 인증 키를 사용하세요. 유료 Jev를 선택한다면:

```dotenv
DECISION_ENGINE=jev
JEV_API_KEY=your-jev-api-key
```

DeciFlow를 실행할 사용자가 쓸 수 있도록 기본 저장 디렉터리를 준비하세요.
다음 관리자 명령은 필요하면 디렉터리를 생성하며 최초 한 번 수행합니다.

```bash
sudo install -d -o "$(id -un)" -g "$(id -gn)" \
  /var/lib/deciflow-data /var/log/deciflow
```

또는 `DECIFLOW_DATA_DIR`과 `DECIFLOW_LOG_DIR`을 쓰기 가능한 다른 경로로 지정하고,
기동 전에 해당 디렉터리를 생성하세요. 이후 실행합니다.

```bash
deciflow
```

`http://127.0.0.1:4000`에 접속하고 Task 실행 전에 엔진 상태를 확인하세요.
`deciflow`는 UI Restart를 포함해 기동할 때마다 전체 설정 검사를 먼저 수행하고,
모두 통과해야 서버를 시작합니다. Jev 키 누락, 엔진 연결 불가 등 준비 조건이 실패하면
기동을 중단합니다. `.env`가 없다고 자동 생성하지 않으므로 `deciflow init`으로
준비하세요. Jev로 자동 전환하지 않습니다.

생성된 설정은 루프백 HTTP를 사용합니다. `DECIFLOW_DATA_DIR`이 비어 있으면
`/var/lib/deciflow-data`를 사용하고, `DECIFLOW_LOG_DIR` 기본값은 `/var/log/deciflow`로
Docker 컨테이너 내부 경로와 동일합니다. 설치형 명령은 디렉터리가 없거나 쓰기 권한이
없으면 짧은 오류와 `config test` 명령을 안내하고 중단하며, 홈 디렉터리로 자동 변경하지 않습니다.
`DECIFLOW_LOG_DIR`을 비우면 콘솔에만 로그를 기록합니다.
Source와 Action의 상대 경로는 설정 디렉터리 기준입니다. 내장 Docker 샘플 Source는
`/host-logs/...`를 사용하므로 실제 로컬 파일을 가리키는 Source를 새로 만들거나
수정하세요. Ctrl+C로 애플리케이션을 종료합니다.

## 설정과 저장 경로

다른 설정 디렉터리를 선택하려면 모든 명령에 같은 옵션을 전달합니다.

```bash
deciflow init --config-dir /path/to/deciflow-config
deciflow config list --config-dir /path/to/deciflow-config
deciflow config test --config-dir /path/to/deciflow-config
deciflow --config-dir /path/to/deciflow-config
```

이 디렉터리에는 `.env`와 `oauth2-proxy/`가 위치합니다. 데이터·로그는
`--config-dir`과 별개로 지정된 저장 경로를 사용합니다.
현재 셸 디렉터리나 다른 Git 저장소의 `.env`를 자동으로 읽지 않습니다.
기존 네이티브 저장소 설정을 사용하려면 `--config-dir /path/to/DeciFlow`로
명시적으로 선택하세요.

`DECIFLOW_DATA_DIR`은 DB·Actions·SSH 키 저장 경로를,
`DECIFLOW_LOG_DIR`은 서버·접근 로그 경로를 지정합니다. 설치된 앱을 교체하거나
업데이트할 때 해당 디렉터리와 인증 정보를 보존하세요. 설치된 패키지와 분리되어
있으므로 도구를 제거해도 사용자 데이터는 삭제되지 않습니다.
환경변수와 UI 저장 설정의 우선순위는 [설정](configuration.ko.md)을 따릅니다.

## 설정 검사

DeciFlow를 기동하기 전에 동일한 설정 디렉터리로 검사합니다.

```bash
deciflow config test
deciflow config test --config-dir /path/to/deciflow-config
```

설치 경로에 맞는 명령 하나를 선택하세요. 개별 항목이 실패해도 나머지 검사를 계속하며,
마지막에 **Config Test Passed** 또는 **Config Test Failed**를 표시합니다. 터미널에서는
**Passed**를 녹색, **Failed**를 밝은 빨강으로 표시합니다. 파일로 리디렉션하면 일반
텍스트를 사용하고, `NO_COLOR`로 색상을 끌 수도 있습니다. 종료 코드는 성공 `0`, 실패 `1`입니다.

`init`은 샘플 생성, `config test`는 준비 상태 진단, 기본 `deciflow`는 검사 후 기동입니다.
`init`, `config test`, `config list`, 도움말은 서버를 시작하지 않으며, 전체 준비 검사가
필수인 작업은 서버 기동입니다.

검사 대상은 `.env` 문법, 번들 UI 파일, 데이터·로그 쓰기 권한, 기존 DB 접근·UI 저장 설정,
엔진 설정과 추론 없는 상태·인증 요청, `uv` 실행 파일, UI 수신 포트입니다.
OAuth2-Proxy가 활성화되어 있으면 실행 파일·인증 정보·쿠키 키 형식·HTTPS 출처·정책·이메일
허용 목록·TLS 파일의 일치 여부·인증서 유효 기간과 호스트명·HTTPS 수신 포트도 검사합니다.
인증을 비활성화했다면 TLS 파일은 필요하지 않습니다.

검사 중 설정·DB 생성, 서버 기동, 의존성 설치, 추론 요청은 하지 않습니다. 쓰기 권한은
즉시 삭제되는 임시 파일로 확인하며, 기동 시와 같은 UI 저장 설정을 적용합니다.
이미 DeciFlow가 실행 중이면 포트 검사가 실패할 수 있으므로 기동 전 검사 시에는 종료하세요.
Google 클라이언트 등록, 공개 DNS/NAT 접근, 인증서 체인 신뢰, 실제 추론·모델 가용성,
개별 Source·Action 요구 사항은 실행 환경에서 추가 확인해야 합니다.
기동 시에도 같은 검사를 수행하지만 종합 결과만 출력합니다. 항목별 결과와 준비 방법은
`config test`에서 확인합니다. 검사 통과 이후 발견된 기동 오류는 짧은 메시지와
`config test` 명령으로 안내합니다.

## 실제 적용 설정 조회

```bash
deciflow config list
deciflow config list --config-dir /path/to/deciflow-config
```

설치 경로에 맞는 명령 하나를 선택하세요. 알려진 애플리케이션 설정과 적용 출처를
**UI Override**, **Environment**(`.env` 포함), **Default**로 표시하며,
인증된 브라우저 출처는 **OAuth2-Proxy**로 표시합니다. 데이터 경로가 비어 있어도
실제 기본 경로를 확인할 수 있습니다. API 키·비밀값은 마스킹하고 URL의 인증 정보·
쿼리 값·프래그먼트도 숨깁니다. 엔진 연결이나 DB 초기화를 수행하지 않으며,
전체 준비 검사가 통과하지 않은 상태에서도 조회할 수 있습니다.

## 선택적 Google 로그인

[네이티브 인증 설정](native.ko.md#선택-oauth2-proxy를-통한-네이티브-https)과
[DNS/TLS 준비](dns-tls.ko.md)를 따르세요. OAuth2-Proxy 실행 파일을 PATH에 설치하고,
Google 인증 정보와 `OAUTH2_PROXY_PUBLIC_URL`을 설정한 뒤 다음 파일을 준비합니다.

```text
<workspace>/oauth2-proxy/oauth2-proxy.cfg
<workspace>/oauth2-proxy/allowed-emails.txt
<workspace>/oauth2-proxy/tls/fullchain.pem
<workspace>/oauth2-proxy/tls/privkey.pem
```

명령은 정책 파일과 `allowed-emails.example.txt`를 준비합니다. 이메일 샘플을
`allowed-emails.txt`로 복사해 수정하세요. 준비가 끝난 뒤에만
`OAUTH2_PROXY_ENABLED=true`로 설정하세요. 실행 파일·인증 정보·인증서·허용 목록이
없으면 오류와 `config test` 명령을 표시하고 중단하며, 인증 없는 HTTP로 전환하지 않습니다.

## 업데이트와 제거

PyPI에 게시된 패키지를 설치했다면:

```bash
uv tool upgrade deciflow
uv tool uninstall deciflow
```

브랜치 테스트 중에는 수정된 저장소나 wheel을 `uv tool install --force .`로 설치합니다.
게시는 아래의 태그 워크플로로 수행하며, 이 브랜치의 설치·테스트는
패키지를 업로드하지 않습니다.

## Git 태그로 게시

관리자용 `.github/workflows/pypi-publish.yml`은 태그 push 시 Python 3.12 테스트,
sdist·wheel 빌드, 태그와 패키지 버전 일치 검사, 설치된 wheel 검증을 수행합니다.
동일한 배포 파일을 **TestPyPI에 먼저** 게시하고 성공한 경우에만 **PyPI**에 게시합니다.
일반 브랜치 push는 패키지를 게시하지 않으며, 별도 pytest 워크플로는 Python 3.11·3.12를
검사합니다.

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

게시는 GitHub OIDC를 사용하며 게시 작업에만 `id-token: write` 권한을 부여합니다.
워크플로는 태그·커밋·GitHub Release를 생성하지 않습니다. 이미 게시된 패키지 버전은
덮어쓸 수 없습니다. TestPyPI 성공 후 PyPI가 실패하면 원인을 해결하고 같은 워크플로
실행에서 실패한 작업을 재실행하여 기존 배포 파일을 사용하세요.
설치나 로컬 검증은 패키지를 업로드하지 않습니다.

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
