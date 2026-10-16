# Tasks

[English](tasks.md) | [한국어](tasks.ko.md) | [문서 안내](README.ko.md)

**Task**는 실행 설정이며 시작할 때마다 별도 **run(실행)**을 생성합니다.
Source를 먼저 등록하고 Task에 이름·모드·소스별 설정(Criteria·Events/chunk·선택적
Action·Remote File 대상 Hosts)을 저장합니다. 저장만으로 실행하지 않습니다. Main에서는 실행 중인 Task를 이름순 목록에서
선택해 결과를 확인합니다. 처음에는 선택하지 않은 상태입니다. Tasks 목록은 Run·Stop·View·Edit·History·Delete를 제공합니다.

| 모드 | 실행 방식 |
| --- | --- |
| Batch / Manual | 일치한 파일을 처음부터 한 번 읽고 종료합니다. 다시 실행하려면 Run을 누릅니다. |
| Batch / Cron | 5개 필드 표현식과 명시적 IANA 시간대로 반복합니다. 예: `0 9 * * *`, `Asia/Seoul`. Enable schedule은 이후 자동 실행을 제어하며 수동 Run도 가능합니다. |
| Realtime | Stop까지 새 줄을 계속 감시합니다. 기존 내용은 건너뛰고 새 파일·교체 파일은 처음부터 읽습니다. Resume on restart는 기본적으로 꺼져 있습니다. |

Batch는 매번 처음부터 읽으므로 같은 이벤트에 Action을 반복 실행할 수 있습니다.
증분 체크포인트·자동 재시도는 없습니다. Stop은 현재 실행을 취소합니다. Cron 예약을
끄면 이후 자동 시작만 막고 현재 실행은 중단하지 않습니다. 서버 중단 중 놓친 예약은
재실행하지 않습니다. Realtime 재시작은 새 실행이며 중단 중 기록된 줄을 복구하지 않습니다.

같은 Task는 동시에 하나만 실행합니다. 중복 수동 시작은 거부하고 겹치는 Cron 회차는
Skipped로 기록합니다. 서로 다른 Task는 동시 실행하며 각각 엔진의 실행별 동시 요청
제한을 적용합니다. 엔진은 실행 시작 시 서버 설정을 사용하고 Laya에서 유료 Jev로
자동 전환하지 않습니다.

상태는 Running·Completed·Failed·Stopped·Skipped이며 실행 전 Task는 Idle입니다.
판정 요청 또는 Action이 하나라도 실패하면 실행은 Failed입니다. History는 최근 50개
기록의 시작·종료 시각·시작 원인·처리 수와 View results를 제공합니다. 결과 재생은
판정·Action을 다시 실행하지 않습니다. Main은 선택한 Task의 새 실행을 따라가며
이력에서 특정 실행을 열면 해당 실행을 유지합니다.

편집 내용은 다음 실행부터 적용하고 진행 중 실행은 설정 스냅샷을 유지합니다.
저장한 Task가 사용하는 Source·Criteria·Action 참조는 제거할 수 없습니다.
Task 삭제 전 실행을 중지해야 하며 삭제 후에도 실행 디렉터리는 디스크에 남습니다.

## 여러 대상 Hosts

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
tasks/
  tasks.json
  <task-id>/runs/<run-id>/
    run.json
    events.ndjson
```

데이터 볼륨에 정의·상태·설정·원본 로그·판정·Action 결과를 보존하여 서버 재시작
후에도 조회할 수 있습니다. 중단된 실행은 Stopped가 되며 Batch는 자동 재개하지
않습니다. 자동 재시작을 선택한 Realtime만 서버 시작 시 새 실행을 시작합니다.
수동 정정은 브라우저에만 남으므로 보존하려면 JSON으로 내보내세요.

**데이터 경로마다 서버 프로세스·인스턴스 하나**를 사용합니다. 프로세스 내 예약
실행이며 분산 워커·DAG 의존성은 없습니다. 모든 실행 결과는 서버 종료까지 RAM에도
남습니다. 자동 디스크 이력 정리는 없으므로 큰 Batch·장시간 Realtime에는 적절한
메모리·디스크 용량이 필요합니다.

## API

모든 엔드포인트에 신뢰할 수 있는 파일 접근 UI Origin이 필요합니다:

| 요청 | 용도 |
| --- | --- |
| `POST /api/tasks` | 정의·현재/최근 실행·다음 예약 시각 조회 |
| `PUT /api/tasks` | Task 하나 저장(수정 시 `id` 포함) |
| `DELETE /api/tasks` | `{ "id": "..." }`로 Task 정의 삭제 |
| `POST /api/tasks/<id>/run` | 수동 시작; HTTP 202로 상태·jobId 반환 |
| `POST /api/tasks/<id>/stop` | 현재 실행 중지 |
| `POST /api/tasks/<id>/runs` | 최근 실행 기록 50개 |
| `POST /api/jobs/<jobId>` | 현재·보관 실행 조회 |
| `POST /api/jobs/<jobId>/events` | NDJSON 결과 재생·수신 |

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
  "enabled": false,
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
