# Python Actions

목록의 **Manage → Ref.** 버튼과 Edit의 **References** 링크는 참조 대화상자를 엽니다.
View는 세부 정보 위 **References**에 같은 내용을 직접 표시합니다.
Task 할당, 실행 중 작업, 복구 가능한 실행의 종류·이름·ID만 표시합니다.
상세 화면이 있는 항목의 ID 링크는 새 탭으로 열리며,
열 때 현재 참조를 조회합니다.


[English](actions.md) | [한국어](actions.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

## 기본 샘플 Action

최초 초기화 또는 Reset DeciFlow 후 **Sample Elasticsearch**를 자동 등록합니다.
Python **3.12**, 모듈 **elasticsearch**를 사용하며 결과에 UTC `@timestamp`를 추가해
`http://host.docker.internal:9200`의 `deciflow` 인덱스에 저장하는 코드입니다.
Task 시작 전에 스크립트·venv를 자동 생성하고 Python·모듈을 설치합니다.
최초 준비에는 다운로드 연결이 필요하며 서버 기동이 지연될 수 있습니다.
실패하면 Actions에 **Not ready**와 오류를 표시합니다. **Save & Prepare Environments**
또는 DeciFlow 재시작으로 재시도할 수 있습니다. 준비 과정에서 샘플 코드를 실행하지는 않습니다.
이후 수정·삭제한 설정은 재기동 시 보존합니다. Compose에서 `host.docker.internal`은
Docker 호스트 게이트웨이를 가리킵니다. Python 직접 실행 시에는 DeciFlow 호스트에서
접근 가능한 주소로 수정하세요.

## Action 관리

Add·Edit에서는 목록을 숨기고 입력폼만 표시합니다. 저장 또는 Cancel Edit 후 목록으로 돌아옵니다.

**View**는 선택한 행 아래에서 이름·Python 버전·모듈·코드·경로를 공통 라벨·값 형식으로 표시합니다. 같은 View를 다시 누르면 접으며 편집 초안이나 환경을 변경하지 않습니다. Python Code는 View와 Add/Edit 모두 키워드·문자열·주석 등에 구문 색상을 적용합니다. 색상은 표시 기능이며 코드 내용과 저장·실행 동작은 유지합니다. 외부 CDN은 사용하지 않으며 구문 검증이나 자동완성 기능은 아닙니다. Edit·Add는 View를 닫습니다.

좌측 사이드바의 **Actions**에서 핸들러를 생성·수정·삭제합니다.
**Add Action**을 누르고 이름, Python 버전(예: `3.12`), 모듈 목록,
Python 코드를 편집기에 직접 입력한 뒤 **Save & Prepare Environments**를
누릅니다. 스크립트 경로나 별도 파일 업로드는 필요하지 않습니다.
목록은 Action별 이름·Python 버전·모듈·환경 Status와 **View**/**Edit**/**Reset venv**/**Delete** 버튼을 한 줄에
표시합니다. **Search by Name**에서 대소문자 구분 없이 이름의 일부로 검색합니다.
**Edit**으로 하나의 편집기를 열고 **Cancel Edit**으로 변경을 취소합니다.
삭제도 저장하면 반영됩니다. **Tasks**으로 돌아가 로그 파일·패턴마다 Action 또는
**None**을 선택하고 Batch/Realtime을 실행합니다. 화면을 전환해도 진행 중인
분석은 유지됩니다. 사이드바에서 Actions로 재진입하면 목록으로 돌아가고
미저장 초안은 버립니다. 할당은 Task별로 저장합니다.

모듈은 한 줄에 하나씩 입력하며 extras와 버전 조건을 지원합니다.
예: `httpx==0.28.1`, `requests>=2.32,<3`. URL, 로컬 경로, 인덱스 옵션,
환경 마커는 지원하지 않습니다. 표준 라이브러리만 사용하면 목록을 비워둡니다.
코드에서는 `result = json.load(sys.stdin)`으로 판정을 받습니다.
새 편집기에는 실행 가능한 기본 템플릿이 제공됩니다.

**Status**는 환경 상태를 표시합니다. Ready는 스크립트·Python 실행 파일·의존성 잠금 파일·설치 완료 표시가 모두 존재하는 상태,
Preparing...은 준비 중, Not ready는 환경 누락·불완전 상태입니다. 외부 Python을
사용하는 Action은 External입니다. 저장·Reset 중에는 Preparing...을 표시하며,
준비 중인 상태가 있으면 완료될 때까지 자동 갱신합니다. 편집 화면에도 상태를 표시합니다.

DeciFlow의 PATH에 `uv`가 있고 영구 저장 경로에 쓰기 권한이 있어야 합니다.
`uv venv --seed`, `uv add`, `uv sync`로 독립 환경을 준비합니다. Python·패키지
설치에는 네트워크 접근이 필요할 수 있습니다. 준비는 uv 명령마다 최대 5분이며
실패하면 기존 등록 정보를 유지합니다. 기존 파일 기반 등록도 계속 실행할 수
있습니다. Actions 화면에서 기존 코드를 불러오며, 저장하면 UI에서 관리하는
코드와 실행 환경으로 전환됩니다.

Actions는 공통 `DECIFLOW_DATA_DIR` 아래 `actions/`에 저장합니다.
기본 경로는 Python·Docker 모두 `/var/lib/deciflow-data/actions`입니다.
Python 직접 실행에서는 쓰기 권한이 필요하며, 필요하면 공통 경로를 `./data`로 설정하세요.
Docker에서는 공통 데이터 루트와 볼륨 목적지를 동일하게 유지합니다.
등록 정보는 `DECIFLOW_DATA_DIR/deciflow.sqlite3`에 저장하고 코드·프로젝트·lockfile·venv는 Actions 디렉터리에 보관합니다.
새 Task Source 행의 Action 기본값은 **None**입니다. Action 할당·Criteria·청크 크기는
Task에 서버 측으로 저장하며 새로고침 후에도 유지합니다. 각 실행은 시작 시 설정을
보존하고 변경 사항은 새 실행에 적용합니다. 저장 경로를 변경해도 기존 데이터는
자동으로 이동하지 않습니다.

현재 설정은 공통 SQLite DB에서 관리합니다. UI에서 관리하는 Action은
`<Action UUID>/` 디렉터리를 사용합니다.
Edit에서 중복되지 않는 이름으로 변경할 수 있으며 대소문자는 구분하지 않습니다.
Task 할당·실행 대상 선택·삭제 의존성 검사는 표시 이름 대신 `actionId`를 사용합니다.
이름 변경 시 UUID·최초 디렉터리·코드·가상환경은 그대로 유지하며 실행 중 작업은 기존 스냅샷을 유지합니다.
코드와 실행 환경은 해당 디렉터리 바로 아래에 둡니다:

```text
<Action UUID>/
├── action.py
├── .venv/
├── pyproject.toml
├── uv.lock
└── .ready
```

`action.py`는 현재 스크립트, `.venv`는 해당 Python 환경입니다.
`pyproject.toml`·`uv.lock`은 환경 설정과 해석된 패키지 버전을 보관하고,
`.ready`는 준비 완료를 표시합니다. 코드만 수정하면 환경은 재사용하며,
Python·모듈을 변경하면 같은 경로에 `.venv`를 재생성합니다.
변경하지 않은 준비 완료 설정은 재사용합니다.

저장 중에는 변경할 파일을 임시 백업하고 성공하면 백업을 제거합니다.
준비·저장 실패 시 해당 파일을 복구하고 저장된 설정을 유지합니다.
백업은 작업 중에만 사용하는 임시 파일이며 보관 버전이 아닙니다.

분석에서 사용 중인 Action은 수정·Reset·삭제할 수 없습니다. 먼저 해당 분석을
중지하세요. 변경 없는 Action 저장과 다른 Action 수정은 가능합니다.
설정 변경 중인 Action을 사용하는 새 분석은 시작할 수 없습니다. 저장은 단일
DeciFlow 프로세스 안에서 직렬화하며 여러 프로세스가 볼륨에 함께 쓰는 방식은
지원하지 않습니다. 저장된 Task가 참조하는 Action도 삭제할 수 없습니다.
먼저 해당 Task에서 다른 Action이나 None으로 변경하세요.

목록의 **Reset venv**는 저장된 Action의 현재 `.venv`를 삭제하고 Python·모듈 설정과
`uv.lock`을 기준으로 다시 생성합니다. pip도 포함하며 코드·등록 정보·lockfile은 유지합니다.
초안에는 적용하지 않고 저장된 설정을 사용합니다. 실패하면 불완전한 환경을 실행하지 않으며
Reset venv를 다시 눌러 재시도할 수 있습니다. 외부 Python을 지정한 Action은 대상이 아닙니다.

**Delete → Save & Prepare Environments**로 삭제를 확정하면 해당 Action의 데이터 폴더를
제거합니다. 코드·실행 환경·lockfile·데이터가 함께 삭제됩니다.
DeciFlow가 관리하지 않는 외부 스크립트·Python은 삭제하지 않습니다.
사용 중인 분석이 있으면 수정·Reset·삭제를 거부합니다. 먼저 **Stop**을 누르세요.
재생성 중에는 해당 Action을 사용하는 새 분석도 시작할 수 없습니다.

venv가 삭제됐다면 Actions를 다시 저장하여 복구합니다. 해석된 패키지 버전을
복원하려면 프로젝트와 `uv.lock`을 유지해야 합니다. 삭제하면 다시 해석해야 합니다.
로그 처리 중에는 패키지를 설치하지 않습니다. 환경이 없거나 준비가 불완전하면
Action 실패로 표시합니다. 중복 패턴은 프로필, 청크 크기, Action이 같아야 합니다.

성공한 판정마다(불확실한 판정 포함) 새 Python 프로세스의 표준 입력으로 JSON
객체 하나를 전달합니다. 기존 결과의 로그 원문, 출처, 줄 범위, 프로필, 확률,
검토 표시와 함께 `schemaVersion: 2`, `eventId`, UTC `decidedAt`, `engine`이
포함됩니다. 이벤트 ID는 이번 실행을 식별하며, 같은 배치를 다시 실행하면 새 ID가
생성됩니다. 코드에서 범주나 검토 표시를 기준으로 필터링할 수 있습니다.
Laya와 Jev는 같은 계약을 사용합니다. 판정 실패·Source 읽기 실패·미할당 소스에는 실행하지 않습니다.
원격 입력에는 `hostId`·`hostName`·`hostAddress`·`hostPort`·`chunkSequence`도
포함하며, 로그 원문을 바꾸지 않고 대상 호스트를 식별합니다.

모든 프로필은 검증한 답변을 `decisions[decision_id]`, 고정한 구성을
`decisionDefinitions`에 제공합니다. JSONL에는 추출한
`log`, 본문을 제외한 `inputRecord` 메타데이터, `inputContentInLog: true`,
`recordNumber`가 추가됩니다. 유효한 입력의 중복 `rawInput`은 생략합니다.
필요한 업무 중복 방지는 출처·레코드 번호 등을 사용하세요. eventId는 재실행 시 바뀝니다.
Action은 이후 사람의 수정 전에 실행되며 검토자가 결과를 수정해도 자동 재실행하지 않습니다.

[Python 핸들러 예제](../examples/action_print.py)를 편집기에 복사해 사용할 수 있습니다.

종료 코드 0은 성공입니다. DeciFlow는 이름, 상태, 종료 코드, 실행 시간을
`actionExecution`으로 표시하며 실패한 실행의 stderr를 최대 4 KiB 보관합니다.
stdout은 버리므로 스크립트에서 직접 파일을 저장하거나 외부 시스템을 호출해야 합니다.
Action은 실행 단위별로 순차 처리하며 시간 제한은 30초이고 자동 재시도는 없습니다.
느린 Action은 결과 전달을 늦추고 처리량을 낮춥니다. 실패를 기록한 뒤 다음 판정을
계속 처리합니다. **Stop**은 현재 Action 프로세스를 취소하지만 브라우저 연결이
끊겨도 UI 작업은 계속 실행합니다. 취소 시 이미
발생한 외부 동작은 되돌리지 못합니다. 스크립트가 생성한 하위 프로세스는 직접 관리해야
합니다. Task 실행 이력은 Action 실행 결과를 디스크에 저장하고 UI·JSON 내보내기로
제공합니다. 영구 Action 작업 큐나 자동 재시도는 제공하지 않습니다.

신뢰하는 스크립트만 등록하세요. Action은 샌드박스 없이 DeciFlow의 OS 권한,
환경 변수, 작업 디렉터리를 사용합니다. 등록은 파일 접근과 같은 로컬·신뢰 출처
제한을 사용하므로 신뢰 출처에 코드 실행 권한도 부여됩니다. 인증 정보는 환경 변수나
비밀 저장소에 보관하고 stderr에 출력하지 마세요.

Docker Compose는 `deciflow-data` 볼륨을 `DECIFLOW_DATA_DIR`
(기본 `/var/lib/deciflow-data`)에 연결하며 Criteria와 공유합니다. 읽기 전용 `/app`
밖에 있으므로 호스트에 별도 데이터 디렉터리가 필요하지 않습니다. 경로를 바꾸면
기존 Actions를 이전하고 새 경로에 가상환경을 준비한 뒤
`docker compose up -d ui`로 적용하세요. 데이터 경로 변경에는 UI 이미지 재빌드가
필요하지 않습니다. [Docker 배포](../README.ko.md#deciflow-docker)를 참고하세요.

구문 색상은 로컬에 포함한 PrismJS 1.30.0의 Core·Python 구성(약 9.4KiB, MIT)으로 처리합니다. 실행 중 외부 CDN을 요청하지 않으며 버전이 고정된 파일은 브라우저에 캐시합니다. 원본·라이선스·SHA-256은 `public/vendor/prism/`에 기록하며 버전 교체 시 해당 기록과 UI 검증을 함께 갱신합니다. 편집 입력·스크롤은 기존 방식을 유지합니다.


항목별 처리는 `decisions`와 `decisionAssessments`를 사용하고 기록 전체 불확실성은
`anyUncertain`으로 확인합니다. `defaultDecision` 변경은 표시만 바꾸며 Action을 재실행하지 않습니다.

## 간결한 결과 JSON 계약 (버전 2)

상담 원문은 `log` 한 곳에 저장하고 JSONL의 나머지 필드는 `inputRecord`에 유지합니다.
`inputContentInLog: true`이면 `contentField`가 가리키는 값은 `log`에 있습니다.
기존 사용자 Action에서 `inputRecord[contentField]`를 읽었다면 `log`로 변경하세요.
원래 JSON 객체가 필요하면 다음처럼 복원합니다(원래 줄의 공백·이스케이프 형식까지
복원하는 것은 아닙니다).

```python
record = dict(result.get("inputRecord", {}))
if result.get("inputContentInLog"):
    record[result["contentField"]] = result["log"]
```

잘못된 JSONL·불일치하는 원본의 `rawInput`과 오류 진단은 보존합니다. 성공한 결과의
반복 `questions`는 제외하며, 판정 정의는 `decisionDefinitions`에 있습니다.
`providerResponse.answersInDecisions: true`이면 동일한 답변은 `decisions`에 한 번만
있습니다. 사용량·모델·라우팅과 다른 제공자 정보는 유지합니다. 내부 DB 작업 ID와
체크포인트는 Action에 전달하지 않습니다. 사용자 스크립트나 기존 ES 문서는 자동으로
수정하지 않으며, Elasticsearch 샘플처럼 전체 결과를 보내는 Action은 새 계약을 그대로
전달합니다. Laya·Jev, TEXT·JSONL에 공통 적용합니다.
