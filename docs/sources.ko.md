# Sources

[English](sources.md) | [한국어](sources.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

사이드바 **Source**에서 재사용할 데이터 입력을 등록합니다.
**Add Source**로 Type·Name·File Path / Pattern 순서로 입력하고 **Save Changes**로 저장하세요.
이름·경로로 검색하고 View·Edit·Delete로 관리합니다. 삭제는 저장 시 적용하며,
로그 파일·SSH Host·SSH 키·known_hosts 파일을 삭제하지 않습니다.
Remote File에는 재사용할 경로를 지정합니다. Task의 Source별로 검색 가능한 체크박스에서
대상 **SSH Hosts**를 하나 이상 선택하며 Select all shown·Clear를 제공합니다. 접속 설정은
**Settings → SSH Hosts**에서 관리합니다.

| 타입 | 위치와 요구사항 |
| --- | --- |
| Local File | DeciFlow 노드의 읽기 가능한 UTF-8 일반 파일. 상대 경로는 작업 디렉터리 기준 |
| Remote File (SSH) | SSH/SFTP 호스트의 UTF-8 일반 파일. 절대 POSIX 경로·키 인증·호스트 키 검증 필요 |

경로는 `*`·`?`·`[abc]`·재귀 `**` 패턴을 지원하며 등록 하나로 여러 파일을 선택할 수
있습니다. 초기 예시는 System messages·Sample HTTP access·Sample SSH authentication입니다.
환경에 맞게 편집하세요. 이름·ID는 중복할 수 없으며 이름을 바꿔도 ID는 유지합니다.

**File Path / Pattern**에는 Local File·Remote File 모두 한 줄에 경로·패턴을 하나씩
입력할 수 있습니다. 저장 시 빈 줄과 중복 항목을 제거합니다. 각 경로는 Task 행의
Criteria·청크 크기·Action·Source Hosts 설정을 공유합니다. 같은 Source의 패턴이
겹쳐도 동일 파일은 한 번만 읽으며 SSH 연결은 Source/Host별로 하나를 재사용합니다.
Batch는 어느 항목이든 일반 파일과 일치하지 않으면 실패하고, Realtime은 새로 일치하는
파일을 계속 감시합니다.

## Tasks에서 선택

Batch·Realtime에서 선택 행을 추가하고 풀다운에서 등록한 Source를 선택합니다.
Source·Action 풀다운은 이미 선택한 값과 관계없이 전체 항목을 알파벳·가나다순으로
표시합니다. 선택한 파일 경로·패턴은 Source 아래에 표시하며 옵션의 툴팁에는
타입·경로가 포함됩니다. Action None은 미할당입니다. 입력 필터링은 사용하지 않습니다.

행마다 Criteria·Events/Chunk·Action을 지정합니다. 이 값은 소스 등록이 아닌 Task에 저장하는
설정입니다. Batch는 일치한 파일을 EOF까지 읽고, Realtime은 기존 내용을 건너뛰어
새 줄을 감시하며 새로 발견한 파일은 처음부터 읽습니다. Main은 모든 저장된 Task를
표시하며 실행 중·시작 중인 항목을 먼저 배치합니다. 클릭하면 현재·최근 결과를 표시하고
이전 실행은 Tasks → History → View Results에서 엽니다. Paste 입력 모드는 없습니다. **Reset Selections**는 사용 가능한 샘플 소스
또는 첫 등록 소스를 선택하고 청크당 1이벤트·Action None으로 설정합니다.
Task를 저장하면 이 설정을 서버에 보관합니다.

로컬 경로의 중복 일치는 설정이 같으면 한 번만 처리하고 설정이 다르면 거부합니다.
원격 등록은 각각 독립적으로 읽으므로 같은 실행에서 원격 경로가 겹치는 등록을 함께
선택하지 마세요. 청크는 파일을 섞지 않으며 로컬·원격 모두 같은 Laya/Jev 판정·Action 흐름을 사용합니다.

## SSH 설정

Settings에서 **SSH Keys** 다음에 **SSH Hosts**가 표시됩니다. Add Host로 이름·주소·포트·
SSH 사용자·키를 저장하고 검색 가능한 목록의 View·Edit·Delete 버튼으로 관리합니다.
여러 Source가 하나의 Host를 공유하면서 파일 경로만 다르게 지정할 수 있습니다.
Task의 Source 선택에 `hostIds`를 저장하고 실행할 때 접속 정보를 확정합니다. Host 수정은 새 실행에
적용하며 실행 중인 작업은 기존 설정을 유지합니다. 삭제 시 확인창을 표시하며,
저장된 Task나 실행 중인 작업에서 사용하는 Host는 삭제할 수 없습니다.
저장된 Host에서 사용하는 키도 삭제할 수 없습니다.

다음 필드는 Settings의 Host에 설정합니다:

| 필드 | 의미 |
| --- | --- |
| Host | ssh://·사용자 이름을 제외한 호스트 이름 또는 IP |
| Port | SSH 포트. 기본 22 |
| SSH User | 원격 로그 읽기 권한과 SFTP 서브시스템 접근 권한이 있는 계정 |
| SSH Key | Settings에 등록한 키 선택. 기존 파일 경로 등록도 계속 지원 |

암호 입력 없이 읽을 수 있는 키를 사용하세요. 비밀번호·에이전트 인증, 대화형 입력,
호스트 검증 비활성화는 지원하지 않습니다. 대응하는 공개키를 원격 계정의
`authorized_keys`에 등록하세요. Test Connection에서 미등록 호스트의 fingerprint를
신뢰할 수 있는 경로로 확인하고 승인합니다. 승인한 키는
`DECIFLOW_DATA_DIR/ssh-hosts/known_hosts`에 보존하며 연결 테스트와 Remote File 읽기에
함께 적용합니다. `~/.ssh/known_hosts`와 `/etc/ssh/ssh_known_hosts`는
읽거나 수정하지 않으며 CLI 승인은 별개입니다. 비표준 포트는 `[호스트]:포트` 형식입니다.
기존 키가 바뀌거나 폐기된 키는 거부하므로 호스트를 확인하고 해당 known_hosts 항목을
수정해야 합니다.

DeciFlow는 원격 셸 명령 대신 SFTP를 사용하며 키 내용·비밀번호를 등록 파일에
저장하지 않습니다. SSH/SFTP 실패는 Source/Host 오류로 기록하고 다른 호스트는 계속 처리합니다.
자동 재연결은 하지 않습니다.
Stop은 SFTP 세션과 대기 중인 읽기를 종료합니다.

원격 Realtime은 파일 크기와 앞부분 바이트 비교로 잘림·교체를 감지합니다.
앞부분이 같고 크기가 이전 읽기 위치 이상인 교체는 감지하지 못할 수 있으므로
사용하는 로그 기록 방식의 회전 동작을 확인하세요.

### Test Connection

**SSH Hosts**의 각 행 또는 저장 전 Add·Edit 화면에서 **Test Connection**을
누르면 키 인증·호스트 검증·SFTP 접속을 전체 15초 제한으로 확인합니다. 확인 후
연결을 닫으며 로그를 읽거나 입력값을 저장하지 않습니다. 미등록 fingerprint는
확인창에서 승인한 키로만 재시도하고 SSH 인증 성공 후 승인한 키를 보존합니다.
Remote File과 같은 접속 설정을 사용합니다. 목록에는 Not checked·Checking·Connected·
Failed와 마지막 확인 시각·오류를 표시합니다. SSH Hosts 진입 시 이름순으로 한 번
자동 확인합니다. View·목록 재출력·주기 타이머로 완료한 확인을 반복하지 않습니다.
사이드바로 재진입하면 다시 한 번 확인하며 Test Connection은 수동 재확인이 가능합니다.
Settings를 떠나거나 편집 화면을 열거나 탭을 숨기면 현재 요청 후 나머지를 중단합니다. 자동 확인은 미등록 키를 승인하거나
확인창을 열지 않으므로 수동 Test Connection으로 먼저 승인하세요. 새로고침하면
결과를 초기화하고 접속 정보가 바뀌면 이전 결과를 무효화합니다.
성공해도 특정 로그 경로나 파일 읽기 권한을 확인한 것은 아닙니다.

`POST /api/ssh-hosts/test`는 `{ "id": "saved-host-id" }` 또는 저장 전 Host 전체
필드를 받으며 Host 관리와 같은 신뢰 출처 검사를 적용합니다. `connected`·
`checkedAt`·`elapsedMs`와 연결 실패 시 `error`를 반환합니다. 미등록 키에는 공개키·
SHA256 fingerprint를 포함한 `hostKey`도 반환하며 확인 후 `trustedHostKey`에 해당
공개키를 넣어 다시 요청하면 승인한 키로만 접속합니다.


## Settings에서 SSH 키 관리

사이드바의 **Settings → SSH Keys**(`/#settings/ssh-keys`)에서 이름(영문·숫자·공백·밑줄·하이픈)을
입력하고 등록 방식을 선택하세요. 기본 화면은 이름·개인키 경로·관리 버튼의 목록이며,
이름으로 검색할 수 있습니다. **Add Key**로 등록폼을 열고 **View**로 상세 내용을
확인하며 **Edit**로 중복되지 않는 이름으로 변경합니다. 키 파일은 교체하지 않습니다.

- **Upload Private Key:** 브라우저를 실행한 컴퓨터의 파일을 선택합니다.
- **Private Key File Path:** DeciFlow 실행 프로세스에서 읽을 수 있는 파일 경로를
  입력합니다. Docker에서는 컨테이너 내부 경로이며 전용 저장소로 복사합니다.
- **Paste Private Key:** 머리글·꼬리글을 포함한 개인키 전체를 붙여넣습니다.
  입력 내용은 마스킹하며 전송 후 입력칸을 비웁니다.

세 방식 모두 최대 64 KiB의 암호 없는 전용 개인키를 받아 공개키를 자동으로
추출합니다. 원본 파일은 변경하지 않습니다.
등록한 키는 **SSH Host**에서 선택하고, Task의 Remote File Source 행에서 해당 Host를
선택하세요.

키 쌍은 `deciflow-data` 볼륨의 `DECIFLOW_DATA_DIR/ssh-keys/<key-id>/`에
`private_key`(0600), `public_key.pub`(0644)로 보관하며 디렉터리 권한은 0700입니다.
UUID·이름 메타데이터는 SQLite에 저장하고 SSH Host는 `keyId`로 참조합니다.
실행 시 파일 경로를 확정하며 이름을 바꿔도 파일 위치·Host 연결은 유지합니다.
Settings에는 개인키 경로와 `****`로 마스킹한 개인키, 공개키 경로와 내용을 표시합니다. 개인키 내용은
조회 응답에 포함하지 않습니다. 삭제 시 확인창을 띄우며, 저장된 SSH Host나 실행 중인
작업에서 사용하는 키는 삭제할 수 없습니다. 참조를 먼저 변경하거나 제거하세요.
삭제하면 두 파일을 영구적으로 제거합니다.

DeciFlow 호스트에 이미 있는 키는 경로 입력으로, 브라우저를 실행한 컴퓨터의 키는
업로드나 붙여넣기로 등록할 수 있습니다. SSH Host는 등록한 키의 UUID를 선택합니다. Settings는 `ssh-keys`의 키 쌍만 관리하며 호스트의 다른 키를
자동으로 검색·가져오거나 삭제하지 않습니다.

키는 저장 시 암호화하지 않습니다. Settings·호스트·볼륨 백업의 접근 권한을
관리하세요. Python Action도 DeciFlow 권한으로 실행하므로 키 파일에 접근할 수
있으며, 볼륨 백업에는 개인키가 포함됩니다. 네트워크를 통한 UI 등록에는 HTTPS를
사용하세요.

서버 키 검증에는 `DECIFLOW_DATA_DIR/ssh-hosts/known_hosts`만 사용합니다.
기본 경로는 `/var/lib/deciflow-data/ssh-hosts/known_hosts`이며 사용자 SSH 파일을
마운트할 필요가 없습니다. Test Connection에서 미등록 fingerprint를 사이트 모달의 Cancel·Trust & Connect로
확인하고 승인한 키를 이 파일에 보존합니다. 같은 키는 이후 확인창 없이 접속합니다.
예약·백그라운드 Task는 확인창을 띄울 수 없으므로 새 Host는 Task 실행 전에
Test Connection으로 먼저 승인하세요. 승인한 키는 재시작 후에도 유지합니다.
SSH 실행 파일은 필요 없으며 AsyncSSH를 프로젝트 의존성으로 설치합니다.


### Remote File 폴링

Realtime은 SFTP 디렉터리·패턴 탐색에서 받은 파일 속성을 재사용하고 일반 파일의
상위 경로는 디렉터리마다 한 번만 확정합니다. 변경된 파일의 읽기를 깨우며 변경 없는
파일을 탐색할 때마다 다시 열지 않습니다. 파일 탐색은 한 회차 종료 후 250ms 간격을
유지하며 네트워크·서버 지연이 더해집니다. SFTP의 수정 시간 정밀도로 구분하지 못하는
동일 크기 파일 교체도 감지하도록 1초마다 원문 앞부분을 확인합니다. 파일 위치·미완성
줄 처리·호스트별 공정성·청크·실행 전체의 엔진 동시 요청 제한은 유지합니다.
확인 사이에 빠르게 회전하는 파일은 여전히 이벤트가 누락될 수 있습니다.

## 저장과 API

SSH Host 목록·등록/수정·삭제는 `/api/ssh-hosts`의 `POST`·`PUT`·`DELETE`를 사용하며
`DECIFLOW_DATA_DIR/deciflow.sqlite3`에 저장합니다.
키 목록·등록·이름 변경·삭제는 `/api/ssh-keys`의 `POST`·`PUT`·`PATCH`·`DELETE`를 사용하며
Sources와 같은 신뢰하는 파일 접근 Origin 제한을 적용합니다.

정의는 `DECIFLOW_DATA_DIR/deciflow.sqlite3`에 항목별 레코드로 저장합니다.
Compose의 `deciflow-data` 볼륨을 그대로 사용합니다. 저장은 새 실행에 적용하며
실행 중 작업은 시작 시점의 소스 스냅샷을 유지합니다.

`POST /api/sources`로 목록을 읽고 `PUT /api/sources`로 전체 목록을 교체합니다.
두 요청 모두 파일 접근과 같은 로컬·신뢰 UI Origin이 필요합니다. 저장 시 필드와
이름·타입·경로를 검사하며 SSH 호스트에는 연결하지 않습니다.
Tasks에 소스 ID·hostIds·실행 설정을 저장합니다. 직접 파일 API
`POST /api/file-source`의 Remote File 예시입니다(Local File은 hostIds 생략):

```json
{
  "mode": "batch",
  "sources": [
    {"sourceId": "<registered-source-id>", "profile": "general", "chunkEvents": 1, "actionId": "", "hostIds": ["<ssh-host-id>"]}
  ],
  "persist": true
}
```

서버는 등록 파일에서 ID를 해석하며 요청에 별도로 보낸 접속·경로 값은 무시합니다.
파일 API는 프로그램용 명시적 로컬 경로 입력도 지원합니다.
등록 입력의 결과에는 `sourceId`·`sourceName`·`sourceType`을 포함합니다.
원격 결과와 Action 입력에는 `hostId`·`hostName`·`hostAddress`·`hostPort`·
`chunkSequence`도 포함하며 Host 필터는 재판정 없이 결과만 선택합니다.
원격 `source`·`sourcePatterns`는 호스트 구분을 위해 `ssh://사용자@호스트:포트/경로`를
사용합니다. 인증 정보·SSH 키 경로는 판정 요청이나 결과 항목에 추가하지 않습니다.
[요청·결과 JSON](results.ko.md)을 참고하세요.
