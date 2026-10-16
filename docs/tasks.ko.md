# Tasks

[English](tasks.md) | [한국어](tasks.ko.md) | [문서 안내](README.ko.md)

**Task**는 실행 설정이며 시작할 때마다 별도 **run(실행)**을 생성합니다.
Source를 먼저 등록하고 Task에 이름·모드·소스별 설정(Criteria·Events/Chunk·선택적
Action·Remote File 소스 Hosts)을 저장합니다. 저장만으로 실행하지 않습니다. Main에서는 실행 중·시작 중인 Task를 먼저, 각 그룹 안에서는 이름순으로 표시한 목록에서
선택해 현재 또는 최근 실행 결과를 확인합니다. 이력이 없으면 빈 결과를 표시하며 처음에는 선택하지 않은 상태입니다. Tasks 목록은 Enabled 토글과 Run·Stop·View·Edit·History·Delete를 제공합니다.
Task Monitor는 첫 행에 Task 이름·활성 여부·실행 상태, 다음 행에 Source와 중복을 제외한 Source Host 수를 표시하고
그 아래에 Type / Mode / Action을 표시합니다. Action이 없으면 None으로 표시합니다. 긴 설정은 말줄임합니다. 항목 위에서 마우스를 1초간 움직이지 않거나 키보드 포커스를 두면 말풍선에
모든 Source 경로·설정·전체 Source Host 목록(이름·SSH 주소)을 표시합니다.
Local File은 DeciFlow를 Source Host 1개로 셉니다. Escape로 말풍선을 닫습니다.
클릭하면 결과를 표시하고 실행 중인 Task를 먼저 배치합니다. 처리 건수·시각·예약은
결과와 Tasks에서 확인합니다.

| 모드 | 실행 방식 |
| --- | --- |
| Batch / Manual | 일치한 파일을 처음부터 한 번 읽고 종료합니다. 다시 실행하려면 Run을 누릅니다. |
| Batch / Cron | 5개 필드 표현식과 명시적 IANA 시간대로 반복합니다. 예: `0 9 * * *`, `Asia/Seoul`. Enabled 토글로 Task 실행 가능 여부를 제어합니다. |
| Realtime | Stop까지 새 줄을 계속 감시합니다. 기존 내용은 건너뛰고 새 파일·교체 파일은 처음부터 읽습니다. Resume on restart는 기본적으로 꺼져 있습니다. |

Batch는 매번 처음부터 읽으므로 같은 이벤트에 Action을 반복 실행할 수 있습니다.
증분 체크포인트·자동 재시도는 없습니다. Stop은 현재 실행을 취소합니다. Task를
Disable하면 현재 실행도 중지하고 수동 Run·Cron·자동 재시작을 모두 차단합니다.
Enable만으로 즉시 시작하지 않으며 Run 또는 다음 Cron 시각에 실행합니다. 서버 중단 중 놓친 예약은
재실행하지 않습니다. Realtime 재시작은 새 실행이며 중단 중 기록된 줄을 복구하지 않습니다.

같은 Task는 동시에 하나만 실행합니다. 중복 수동 시작은 거부하고 겹치는 Cron 회차는
Skipped로 기록합니다. 서로 다른 Task는 동시 실행하며 각각 엔진의 실행별 동시 요청
제한을 적용합니다. 엔진은 실행 시작 시 서버 설정을 사용하고 Laya에서 유료 Jev로
자동 전환하지 않습니다.

상태는 Running·Completed·Failed·Stopped·Skipped이며 실행 전 Task는 Idle입니다.
판정 요청 또는 Action이 하나라도 실패하면 실행은 Failed입니다. History는 최근 50개
기록의 시작·종료 시각·시작 원인·처리 수와 View Results를 제공합니다. 결과 재생은
판정·Action을 다시 실행하지 않습니다. Main은 선택한 Task의 새 실행을 따라가며
이력에서 특정 실행을 열면 해당 실행을 유지합니다.

편집 내용은 다음 실행부터 적용하고 진행 중 실행은 설정 스냅샷을 유지합니다.
저장한 Task가 사용하는 Source·Criteria·Action 참조는 제거할 수 없습니다.
Task 삭제 전 실행을 중지해야 하며 삭제하면 실행 이력·결과·디렉토리도 영구 삭제합니다.

## 기본 Task

DeciFlow는 **DeciFlow Server Log**를 자동 생성합니다. Local File Source는
`DECIFLOW_LOG_DIR/server.log` / `DECIFLOW_LOG_DIR/access.log`이며 General system 기준·청크당 1개 이벤트·Action
없음으로 설정됩니다. Realtime 모드이고 Task는 기본 Disable 상태입니다.
Enable로 전환한 뒤 Run으로 직접 시작합니다. 자동 재시작도 꺼져 있습니다. 파일 로깅이 켜져 있어야 합니다.

서버 시작 시 기본 Task가 없으면 복구하고, 실행 중 `tasks/tasks.json`이 사라져도
재생성합니다. Tasks 디렉토리 전체를 비운 경우도 포함합니다. 기존 Task 설정은
보존하며 다른 삭제된 Task나 이력은 복구하지 않습니다. UI에서 기본 Task만 삭제하면
다음 서버 시작 전까지는 삭제 상태를 유지합니다.

## 여러 Source Hosts

Remote File Source 행마다 SSH Hosts를 하나 이상 선택합니다. Local File에는 SSH Host
선택이 없습니다. 실행 시작 시 Source × Host를 펼쳐 접속 설정 스냅샷을 확정하며
기존 Source의 Host 연결은 Task 행으로 자동 이전합니다.

호스트별로 독립 수집하고 준비된 청크를 호스트 순환으로 제출합니다. 빈 차례는
추가 원격 존재 확인 없이 건너뜁니다. 호스트마다 병합된 청크 하나를 대기시키고,
내부 Source별 읽기도 제한된 대기만 허용합니다. Source가 많은 호스트도 하나인
호스트와 같은 차례를 받습니다. 느리거나 로그가 없는 호스트는 다른 호스트를 막지
않고 준비되면 자기 차례를 받습니다. 엔진 동시 요청 제한은 호스트별 배수가 아닌
실행 전체에 적용합니다.

청크는 호스트·파일을 섞지 않습니다. 결과는 완료 순서로 표시하며 호스트 정보와
Source/Host별 chunkSequence를 유지합니다. Source·Host 필터는 함께 적용하고 전체
집계나 Action 실행을 바꾸지 않습니다. 호스트 수집 상태는 판정 건수와 구분해 표시합니다.

SSH Source 읽기 실패는 호스트 정보가 있는 `sourceFailure` 결과로 기록하며 엔진·Action을
호출하지 않습니다. 다른 호스트·Source는 계속 처리합니다. 수집 실패 기록은 실패
건수에 포함합니다. 로컬 파일 읽기·UTF-8 오류는 실행을 중단합니다.
Batch는 읽기·판정·Action 중 실패가 있으면 최종 Failed가 됩니다.
Realtime은 정상 호스트를 계속 감시하며 실패한 읽기는 자동 재시도하지 않습니다.
Batch에서 일치하는 파일이 없으면 실패로 기록하며 Realtime은 새 파일을 계속 기다립니다.

## 저장과 운영

`DECIFLOW_DATA_DIR`(기본 `/var/lib/deciflow-data`) 아래에 저장합니다:

```text
results.sqlite3
settings.json
tasks/
  tasks.json
  <task-id>/runs/<run-id>/
    run.json
```

데이터 볼륨에 정의·상태·설정·원본 로그·판정·Action 결과를 보존하여 서버 재시작
후에도 조회할 수 있습니다. 중단된 실행은 Stopped가 되며 Batch는 자동 재개하지
않습니다. Enabled 상태이면서 자동 재시작을 선택한 Realtime만 서버 시작 시 새 실행을 시작합니다.
수동 정정은 SQLite에 실행 결과와 함께 저장하며 JSON 내보내기에도 포함합니다.

**데이터 경로마다 서버 프로세스·인스턴스 하나**를 사용합니다. 프로세스 내 예약
실행이며 분산 워커·DAG 의존성은 없습니다. 결과는 SQLite에 저장하며 서버는 제한된
이벤트 캐시와 집계만, 브라우저는 현재 페이지만 유지합니다. 자동 디스크 이력 정리는
없습니다. 이전 이력 이전·페이지 조회·백업·한계는 [결과 저장](result-storage.ko.md)을 참고하세요.

## API

모든 엔드포인트에 신뢰할 수 있는 파일 접근 UI Origin이 필요합니다:

| 요청 | 용도 |
| --- | --- |
| `POST /api/tasks` | 정의·현재/최근 실행·다음 예약 시각 조회 |
| `PUT /api/tasks` | Task 하나 저장(수정 시 `id` 포함) |
| `DELETE /api/tasks` | `{ "id": "..." }`로 Task 정의·이력·결과·파일 영구 삭제 |
| `POST /api/tasks/<id>/run` | 수동 시작; HTTP 202로 상태·jobId 반환 |
| `POST /api/tasks/<id>/stop` | 현재 실행 중지 |
| `POST /api/tasks/<id>/enabled` | `{ "enabled": true/false }` 설정. false는 현재 실행도 중지 |
| `POST /api/tasks/<id>/runs` | 최근 실행 기록 50개 |
| `POST /api/jobs/<jobId>` | 현재·보관 실행 조회 |
| `POST /api/jobs/<jobId>/events` | NDJSON 결과 재생·수신 |
| `POST /api/jobs/<jobId>/results` | 필터 결과 페이지와 실행 전체 집계 조회 |
| `POST /api/jobs/<jobId>/review` | 결과의 `{ "sequence": ..., "category": "..." }` 리뷰 저장 |
| `POST /api/jobs/<jobId>/export` | 선택한 실행의 Export All JSON |
| `POST /api/jobs/<jobId>/export-reviewed` | 리뷰 Category가 변경된 결과만 Export Reviewed JSON |

저장 필드: `name`, `mode`(`batch`/`realtime`), `sources`(각각 `sourceId`, `profile`,
`chunkEvents`, 선택적 `action`, Remote File의 `hostIds`), `cron`(수동은 빈 값), `timezone`, `enabled`,
`resumeOnRestart`. ID는 서버가 생성합니다. 실행 준비 실패도 오류를 포함한 Failed
실행으로 기록합니다.

### Remote File Task 예시

아래 본문을 `PUT /api/tasks`에 보내되 ID는 등록한 Source·SSH Host ID로 바꿉니다.
두 호스트에 Source의 공통 경로를 적용하며 Action은 선택 사항입니다. 반환된 Task
ID로 `POST /api/tasks/<id>/run`을 호출해 실행합니다.

```json
{
  "name": "System logs across hosts",
  "mode": "batch",
  "cron": "",
  "timezone": "Asia/Seoul",
  "enabled": true,
  "resumeOnRestart": false,
  "sources": [
    {
      "sourceId": "<remote-source-id>",
      "profile": "general",
      "chunkEvents": 1,
      "action": "",
      "hostIds": ["<first-host-id>", "<second-host-id>"]
    }
  ]
}
```

Task 삭제 확인창에서 승인하면 Task 정의·실행 이력·결과·수동 정정·Task 디렉토리를 영구 삭제합니다. 원본 Source 파일은 삭제하지 않습니다. 기존 미등록 Task의 잔여 폴더는 자동 정리하지 않습니다. SQLite의 삭제 공간은 이후 저장에 재사용하며 DB 파일 크기가 즉시 줄지는 않을 수 있습니다.

말풍선이 열린 뒤에는 Task 카드나 말풍선 위에서 마우스를 움직여도 유지합니다.
말풍선으로 이동해 텍스트를 선택·복사할 수 있으며 양쪽에서 벗어나면 닫힙니다.
