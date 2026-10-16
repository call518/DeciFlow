# Sources

[English](sources.md) | [한국어](sources.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

사이드바 Main 아래의 **Sources**에서 재사용할 로그 입력을 등록합니다.
**Add source**로 이름·타입·경로를 입력하고 **Save changes**로 저장하세요.
이름·경로·호스트로 검색하고 View·Edit·Delete로 관리합니다. 삭제는 저장 시 적용하며,
로그 파일·SSH Host·SSH 키·known_hosts 파일을 삭제하지 않습니다.
Remote File은 등록된 **SSH host**와 원격 파일 경로만 지정합니다. 접속 설정은
**Settings → SSH Hosts**에서 관리합니다.

| 타입 | 위치와 요구사항 |
| --- | --- |
| Local File | DeciFlow 노드의 읽기 가능한 UTF-8 일반 파일. 상대 경로는 작업 디렉터리 기준 |
| Remote File (SSH) | SSH/SFTP 호스트의 UTF-8 일반 파일. 절대 POSIX 경로·키 인증·호스트 키 검증 필요 |

경로는 `*`·`?`·`[abc]`·재귀 `**` 패턴을 지원하며 등록 하나로 여러 파일을 선택할 수
있습니다. 초기 예시는 System messages·Sample HTTP access·Sample SSH authentication입니다.
환경에 맞게 편집하세요. 이름·ID는 중복할 수 없으며 이름을 바꿔도 ID는 유지합니다.

## Main에서 선택

Batch·Realtime에서 선택 행을 추가하고 등록한 Source 이름을 입력해 제안을 검색합니다.
제안에는 타입·경로·SSH 호스트도 표시합니다. 등록 항목을 선택해야 하며 자유 입력으로
새 소스를 만들지는 않습니다. 선택한 파일 경로·패턴은 Source 선택창 아래에 표시합니다.
Action도 같은 검색 방식을 사용하며 빈 값은 None입니다.
등록하지 않은 Action 이름은 거부합니다.

행마다 Criteria·Events/chunk·Action을 지정합니다. 이 값은 소스 등록이 아닌 실행별
설정입니다. Batch는 일치한 파일을 EOF까지 읽고, Realtime은 기존 내용을 건너뛰어
새 줄을 감시하며 새로 발견한 파일은 처음부터 읽습니다. Paste는 직접 텍스트 입력을
유지하며 등록 소스가 필요하지 않습니다. **Reset selections**는 사용 가능한 샘플 소스
또는 첫 등록 소스를 선택하고 청크당 1이벤트·Action None으로 설정합니다.
Criteria·청크 설정은 소스 ID 기준으로 브라우저에 저장하며 Action 선택은 페이지 세션에만 유지합니다.

로컬 경로의 중복 일치는 설정이 같으면 한 번만 처리하고 설정이 다르면 거부합니다.
원격 등록은 각각 독립적으로 읽으므로 같은 실행에서 원격 경로가 겹치는 등록을 함께
선택하지 마세요. 청크는 파일을 섞지 않으며 로컬·원격 모두 같은 Laya/Jev 판정·Action 흐름을 사용합니다.

## SSH 설정

Settings에서 **SSH Keys** 다음에 **SSH Hosts**가 표시됩니다. Add host로 이름·주소·포트·
SSH 사용자·키를 저장하고 검색 가능한 목록의 View·Edit·Delete 버튼으로 관리합니다.
여러 Source가 하나의 Host를 공유하면서 파일 경로만 다르게 지정할 수 있습니다.
Source는 `hostId`를 저장하고 실행할 때 접속 정보를 읽습니다. Host 수정은 새 실행에
적용하며 실행 중인 작업은 기존 설정을 유지합니다. 삭제 시 확인창을 표시하며,
저장된 Source나 실행 중인 작업에서 사용하는 Host는 삭제할 수 없습니다.
저장된 Host에서 사용하는 키도 삭제할 수 없습니다.
기존 Source에 직접 저장된 SSH 설정은 자동으로 Host에 옮기며 같은 접속 설정은
하나의 Host를 공유합니다. Source ID는 유지합니다.

다음 필드는 Settings의 Host에 설정합니다:

| 필드 | 의미 |
| --- | --- |
| Host | ssh://·사용자 이름을 제외한 호스트 이름 또는 IP |
| Port | SSH 포트. 기본 22 |
| SSH user | 원격 로그 읽기 권한과 SFTP 서브시스템 접근 권한이 있는 계정 |
| SSH key | Settings에 등록한 키 선택. 기존 파일 경로 등록도 계속 지원 |

암호 입력 없이 읽을 수 있는 키를 사용하세요. 비밀번호·에이전트 인증, 대화형 입력,
호스트 검증 비활성화는 지원하지 않습니다. 대응하는 공개키를 원격 계정의
`authorized_keys`에 등록하세요. 서버 호스트 키의 지문은 신뢰할 수 있는 경로로
확인한 뒤 DeciFlow 실행 계정의 `~/.ssh/known_hosts`에 준비합니다. 비표준 포트는 `[호스트]:포트` 형식의 항목을
사용합니다. 알 수 없거나 일치하지 않는 호스트 키는 연결을 거부합니다.

DeciFlow는 원격 셸 명령 대신 SFTP를 사용하며 키 내용·비밀번호를 등록 파일에
저장하지 않습니다. SSH/SFTP 실패 시 오류로 실행을 중단하며 자동 재연결하지 않습니다.
Stop은 SFTP 세션과 대기 중인 읽기를 종료합니다.

원격 Realtime은 파일 크기와 앞부분 바이트 비교로 잘림·교체를 감지합니다.
앞부분이 같고 크기가 이전 읽기 위치 이상인 교체는 감지하지 못할 수 있으므로
사용하는 로그 기록 방식의 회전 동작을 확인하세요.

## Settings에서 SSH 키 관리

사이드바 하단의 **Settings**(`/#settings`)에서 이름(영문·숫자·공백·밑줄·하이픈)을
입력하고 등록 방식을 선택하세요. 기본 화면은 이름·개인키 경로·관리 버튼의 목록이며,
이름으로 검색할 수 있습니다. **Add key**로 등록폼을 열고 **View**로 상세 내용을
확인합니다.

- **Upload private key:** 브라우저를 실행한 컴퓨터의 파일을 선택합니다.
- **Private key file path:** DeciFlow 실행 프로세스에서 읽을 수 있는 파일 경로를
  입력합니다. Docker에서는 컨테이너 내부 경로이며 전용 저장소로 복사합니다.
- **Paste private key:** 머리글·꼬리글을 포함한 개인키 전체를 붙여넣습니다.
  입력 내용은 마스킹하며 전송 후 입력칸을 비웁니다.

세 방식 모두 최대 64 KiB의 암호 없는 전용 개인키를 받아 공개키를 자동으로
추출합니다. 원본 파일은 변경하지 않습니다.
Remote File Source의 **SSH key**에서 등록한 키를 선택하세요.

키 쌍은 `deciflow-data` 볼륨의 `DECIFLOW_DATA_DIR/ssh-keys/<이름>/`에
`private_key`(0600), `public_key.pub`(0644)로 보관하며 디렉터리 권한은 0700입니다.
Settings에는 개인키 경로와 `****`로 마스킹한 개인키, 공개키 경로와 내용을 표시합니다. 개인키 내용은
조회 응답에 포함하지 않습니다. 삭제 시 확인창을 띄우며, 저장된 Source나 실행 중인
작업에서 사용하는 키는 삭제할 수 없습니다. 참조를 먼저 변경하거나 제거하세요.
삭제하면 두 파일을 영구적으로 제거합니다.

DeciFlow 호스트에 이미 있는 키는 경로 입력으로, 브라우저를 실행한 컴퓨터의 키는
업로드나 붙여넣기로 등록할 수 있습니다. 마운트된 키 파일 경로를 사용하는 기존 Source도
계속 동작합니다. Settings는 `ssh-keys`의 키 쌍만 관리하며 호스트의 다른 키를
자동으로 검색·가져오거나 삭제하지 않습니다.

키는 저장 시 암호화하지 않습니다. Settings·호스트·볼륨 백업의 접근 권한을
관리하세요. Python Action도 DeciFlow 권한으로 실행하므로 키 파일에 접근할 수
있으며, 볼륨 백업에는 개인키가 포함됩니다. 네트워크를 통한 UI 등록에는 HTTPS를
사용하세요.

서버 키 검증에는 DeciFlow 실행 계정의 `~/.ssh/known_hosts`를 사용합니다.
기본 Docker 이미지는 root로 실행하므로, 준비한 파일을 읽기 전용으로 연결하도록
`docker-compose.yml`의 `services.ui.volumes`에 다음을 추가합니다:

```yaml
      - /opt/deciflow-ssh/known_hosts:/root/.ssh/known_hosts:ro
```

호스트 파일을 먼저 만들고 신뢰할 수 있는 경로로 서버 지문을 검증한 뒤
`docker compose up -d ui`를 실행하세요. 실행 계정을 변경하면 컨테이너 경로도
맞춰 주세요. SSH 실행 파일은 필요 없으며 AsyncSSH를 프로젝트 의존성으로 설치합니다.

## 저장과 API

SSH Host 목록·등록/수정·삭제는 `/api/ssh-hosts`의 `POST`·`PUT`·`DELETE`를 사용하며
`DECIFLOW_DATA_DIR/ssh-hosts/hosts.json`에 저장합니다.
키 목록·등록·삭제는 `/api/ssh-keys`의 `POST`·`PUT`·`DELETE`를 사용하며
Sources와 같은 신뢰하는 파일 접근 Origin 제한을 적용합니다.

정의는 `DECIFLOW_DATA_DIR/sources/sources.json`에 저장합니다.
기본값은 `/var/lib/deciflow-data/sources/sources.json`이며 Compose의 `deciflow-data`
볼륨을 그대로 사용합니다. 저장한 변경은 새 실행에 적용하고, 실행 중인 작업은
등록을 수정·삭제해도 시작할 때의 소스 설정을 유지합니다.

`POST /api/sources`로 목록을 읽고 `PUT /api/sources`로 전체 목록을 교체합니다.
두 요청 모두 파일 접근과 같은 로컬·신뢰 UI Origin이 필요합니다. 저장 시 필드와
SSH Host 참조를 검사하며 SSH 호스트에는 연결하지 않습니다.
Main은 `POST /api/file-source`에 소스 ID와 실행별 설정을 전달합니다:

```json
{
  "mode": "batch",
  "sources": [
    {"sourceId": "<registered-source-id>", "profile": "general", "chunkEvents": 1, "action": ""}
  ],
  "persist": true
}
```

서버는 등록 파일에서 ID를 해석하며 요청에 별도로 보낸 접속·경로 값은 무시합니다.
파일 API는 프로그램용 명시적 로컬 경로 입력도 지원합니다.
등록 입력의 결과에는 `sourceId`·`sourceName`·`sourceType`을 포함합니다.
원격 `source`·`sourcePatterns`는 호스트 구분을 위해 `ssh://사용자@호스트:포트/경로`를
사용합니다. 인증 정보·SSH 키 경로는 판정 요청이나 결과 항목에 추가하지 않습니다.
[요청·결과 JSON](results.ko.md)을 참고하세요.
