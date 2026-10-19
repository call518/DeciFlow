# Tasks

[English](tasks.md) | [한국어](tasks.ko.md) | [문서 안내](README.ko.md)

**Task**는 실행 설정이며 시작할 때마다 별도 **run(실행)**을 생성합니다.

Source 선택을 **None**으로 저장하면 해당 Source의 의존성을 일시적으로 해제할 수 있습니다. Source가 없는 Task도 저장할 수 있지만 실행할 수는 없습니다. 시작 중·실행 중·일시정지 전환 중·일시정지 중인 Task는 Stop 후 편집합니다.

Source를 먼저 등록하고 Task에 이름·모드·소스별 설정(Criteria·Events/Chunk·선택적
Action·Remote File 소스 Hosts)을 저장합니다. 저장만으로 실행하지 않습니다. 비활성화한 Task는 Main의 Task Monitor에서 숨기며 Tasks 관리 목록에는 유지합니다. Main에서는 활성화한 Task 중 실행 중·시작 중인 Task를 먼저, 각 그룹 안에서는 이름순으로 표시한 목록에서
선택해 현재 또는 최근 실행 결과를 확인합니다. 이력이 없으면 빈 결과를 표시하며 처음에는 선택하지 않은 상태입니다. Tasks 목록은 Enabled 토글과 Run·Stop·Pause / Resume·View·Edit·History·Delete를 제공합니다.
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
| Realtime | Stop까지 새 줄을 계속 감시합니다. 기존 내용은 건너뛰고 새 파일·교체 파일은 처음부터 읽습니다. 실행 중인 작업은 재시작 후 복구하며, 복구할 실행이 없을 때 새 실행을 시작하는 옵션은 기본적으로 꺼져 있습니다. |

새 Batch Run은 처음부터 읽으므로 같은 이벤트에 Action을 반복 실행할 수 있습니다.
실행 중 서버가 재시작되면 같은 실행 ID와 저장된 처리 위치로 복구합니다. Stop은 현재 실행을 취소합니다. Task를
Disable하면 현재 실행도 중지하고 수동 Run·Cron·자동 재시작을 모두 차단합니다.
Enable만으로 즉시 시작하지 않으며 Run 또는 다음 Cron 시각에 실행합니다. 서버 중단 중 놓친 예약은
재실행하지 않습니다. 복구 가능한 Realtime 실행은 원본 파일에 남아 있는 중단 중
추가 데이터도 이어 읽습니다. 선택적 시작 옵션은 복구할 실행이 없을 때만 새 실행을
만들며, 이때는 기존 파일 내용을 건너뜁니다.

같은 Task는 동시에 하나만 실행합니다. 중복 수동 시작은 거부하고 겹치는 Cron 회차는
Skipped로 기록합니다. 서로 다른 Task는 동시 실행하며 각각 엔진의 실행별 동시 요청
제한을 적용합니다. 엔진은 실행 시작 시 서버 설정을 사용하고 Laya에서 유료 Jev로
자동 전환하지 않습니다.

상태는 Running·Completed·Failed·Stopped·Skipped이며 실행 전 Task는 Idle입니다.
판정 요청 또는 Action이 하나라도 실패하면 실행은 Failed입니다. History는 최근 50개
기록의 시작·종료 시각·시작 원인·저장된 Decision Engine·Requested Model·처리 수와
View Results를 제공합니다. 결과 화면에도 실행 시작 당시 엔진과 요청 모델을 표시하며
상단의 현재 서버 설정과 구분합니다. 정보가 없는 과거 기록이나 준비 완료 전
실패·건너뛴 실행은 **Not Recorded**로 표시합니다. 결과 재생은
판정·Action을 다시 실행하지 않습니다. Main은 선택한 Task의 새 실행을 따라가며
이력에서 특정 실행을 열면 해당 실행을 유지합니다.

편집 내용은 다음 실행부터 적용하고 진행 중 실행은 설정 스냅샷을 유지합니다.
저장한 Task가 사용하는 Source·Criteria·Action 참조는 제거할 수 없습니다.
Task 삭제 전 실행을 중지해야 하며 삭제하면 실행 이력·결과·리뷰도 영구 삭제합니다.

## 기본 Task

DeciFlow는 **Sample DeciFlow Server Log**를 자동 생성하며 **Sample DeciFlow Server Log** Local File Source를
Sources 목록의 첫 번째에 등록합니다. 경로는
`DECIFLOW_LOG_DIR/server.log` / `DECIFLOW_LOG_DIR/access.log`이며 Sample General System 기준·청크당 1개 이벤트·Action
없음으로 설정됩니다. Realtime 모드이고 Task는 기본 Disable 상태입니다.
Enable로 전환한 뒤 Run으로 직접 시작합니다. 자동 재시작도 꺼져 있습니다. 파일 로깅이 켜져 있어야 합니다.

기본 Task는 UUID로 식별하며 서버 시작 시 없으면 복구합니다. Reset 후에도 동일하며 다른 항목과 이름이 겹치면 숫자 접미사를 붙입니다. 기존 설정을 보존하고
다른 삭제된 Task·이력은 복구하지 않습니다. UI에서 기본 Task만 삭제하면 다음 기동 전까지
삭제 상태를 유지합니다. 실행 중 데이터 파일 직접 삭제는 지원하지 않습니다. Reset DeciFlow로
실행 중지·DB 종료 후 초기화하세요.


Action 선택은 `actionId`, SSH Host의 키 선택은 `keyId`로 저장합니다. 이름은 표시용이므로 변경해도 기존 할당은 유지됩니다.

View와 History는 선택한 Task 바로 아래에 펼쳐집니다. 다른 Task의 View 또는 History를
열면 기존 상세 내용은 닫히며, 같은 버튼을 다시 누르면 접힙니다. 목록이 갱신되어도
펼친 상세 내용은 해당 Task 바로 아래에 유지됩니다.

## 여러 Source Hosts

Remote File Source 행마다 SSH Hosts를 하나 이상 선택합니다. Local File에는 SSH Host
선택이 없습니다. 실행 시작 시 Source × Host를 펼쳐 접속 설정 스냅샷을 확정합니다.

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
deciflow.sqlite3
```

데이터 볼륨에 정의·상태·설정·원본 로그·판정·Action 결과를 보존합니다. 체크포인트가
있는 Running 실행은 같은 실행 ID로 자동 재개하고 Paused·Pausing은 Paused로 복구합니다.
체크포인트가 없는 구버전 실행은 Stopped로 정리합니다. 수동 정정도 SQLite에 보존하고
JSON 내보내기에 포함합니다.

**데이터 경로마다 서버 프로세스·인스턴스 하나**를 사용합니다. 프로세스 내 예약
실행이며 분산 워커·DAG 의존성은 없습니다. 결과는 SQLite에 저장하며 서버는 제한된
이벤트 캐시와 집계만, 브라우저는 현재 페이지만 유지합니다. 자동 디스크 이력 정리는
없습니다. 설정 저장·페이지 조회·백업·한계는 [결과 저장](result-storage.ko.md)을 참고하세요.

## API

모든 엔드포인트에 신뢰할 수 있는 파일 접근 UI Origin이 필요합니다:

| 요청 | 용도 |
| --- | --- |
| `POST /api/tasks` | 정의·현재/최근 실행·다음 예약 시각 조회 |
| `PUT /api/tasks` | Task 하나 저장(수정 시 `id` 포함) |
| `DELETE /api/tasks` | `{ "id": "..." }`로 Task 정의·이력·결과·리뷰 영구 삭제 |
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
      "actionId": "",
      "hostIds": ["<first-host-id>", "<second-host-id>"]
    }
  ]
}
```

Task 삭제 확인창에서 승인하면 Task 정의·실행 이력·결과·수동 정정을 영구 삭제합니다. 원본 Source 파일은 삭제하지 않습니다. SQLite의 삭제 공간은 이후 저장에 재사용하며 DB 파일 크기가 즉시 줄지는 않을 수 있습니다.

말풍선이 열린 뒤에는 Task 카드나 말풍선 위에서 마우스를 움직여도 유지합니다.
말풍선으로 이동해 텍스트를 선택·복사할 수 있으며 양쪽에서 벗어나면 닫힙니다.

시작 시 **Sample VOC Asia Culture Center Consulting QnA** Task를 비활성 수동 Batch로 제공합니다.
Sample VOC Asia Culture Center Consulting QnA Source, 한국어 Criteria, Events/Chunk 1, Action None을 연결합니다.
활성화한 뒤 Run을 누르면 파일을 분석합니다.
기존 Task 설정은 덮어쓰지 않습니다.

**Sample System Messages**도 비활성 Realtime Task로 자동 제공합니다. Sample General System,
Events/Chunk 1, Action None으로 기존 **Sample System Messages** Source를 재사용합니다.
초기 로컬 경로는 `/host-logs/var/log/messages`이며 Remote File 변경 등 사용자 설정은
유지합니다. SSH라면 원격 호스트의 실제 경로(보통 `/var/log/messages`)를 입력하고
Task에서 Source Hosts를 선택하세요. 잘못 추가된 System Message Source가 원본
그대로이면 삭제하고 Task 참조를 Sample System Messages로 연결하며, 수정한 중복 Source는 보존합니다.

Tasks에서 Run을 누르면 Main으로 자동 이동하여 해당 Task의 실행 결과를 표시합니다.

## Task 이력과 현재 Run의 차이

Task는 저장된 작업 정의이며 Run을 누를 때마다 별도 실행 ID와 0부터 시작하는
집계를 만듭니다. Main은 선택한 실행 하나의 결과를 보여주며 Task의 평생 누적 합계가
아닙니다. Stop은 해당 실행을 끝내고, 다음 Run은 체크포인트 재개가 아닌 새 실행입니다.
이전 결과·리뷰는 Tasks → History → View Results에서 확인합니다. Batch는 처음부터
다시 읽고 새 Realtime 실행은 새 입력을 감시합니다. 예를 들어 100건에서 Stop한 뒤
Run하면 이전 100건은 History에 남고 새 실행은 완료 건이 생길 때까지 0으로 보입니다.
이 동작은 이전 결과 삭제를 의미하지 않습니다. 실행 간 누적 대시보드는 제공하지 않습니다.
Pause/Resume와 서버 재시작 복구는 기존 실행을 이어가지만 Stop 후 Run은 새 실행입니다. History는 최근 50개 실행을
표시하며, 이는 보관기간이나 자동 삭제 제한이 아닙니다.


## Pause와 Resume

Tasks의 버튼 하나가 실행 상태에 따라 **Pause / Resume**으로 바뀝니다. **Pause**를 누르면 새 건의 처리 시작을 멈춥니다. **Pausing**은 이미
처리를 시작한 판단과 Action을 마무리하는 상태이며, 결과 저장까지 끝나면 **Paused**가
됩니다. **Resume**은 같은 실행 ID로 결과·리뷰·건수·열린 소스의 처리 위치를 유지하여
이어갑니다. 일시정지 중에도 Stop할 수 있으며, 이후 Run은 새 실행입니다. 일시정지한
실행도 중복 수동 실행과 cron 실행을 막습니다. 다른 Task의 처리는 계속됩니다.

Batch와 Realtime 모두 지원합니다. 소스에서 미리 읽은 일부 건은 제한된 크기로
대기할 수 있지만 파일 전체를 계속 쌓는 대기열은 만들지 않습니다. Realtime은 원본
파일이 남아 있다면 일시정지 중 추가된 데이터를 Resume 후 읽습니다. 파일 회전·잘림·삭제나
SSH 연결 중단에 따른 누락 가능성은 기존 소스 처리 규칙을 따릅니다.
체크포인트가 있는 실행은 DeciFlow 서버 재시작 후에도 Paused로 복구되어 Resume을
기다립니다.

Total Elapsed Time과 전체 실행 기준 Throughput에는 일시정지와 서버 중단 시간이 포함됩니다.
Processing Time에는 일시정지 게이트에서 기다린 시간이 포함되지 않습니다.
**Pause Display Updates**는 결과 목록 갱신만 멈추며 실행을 일시정지하지 않습니다.


## 서버 재시작 후 복구

새 파일 기반 Task 실행은 판단 요청 전에 입력 건과 소스 위치를 SQLite에 함께 저장합니다.
결과 저장과 대기열 제거도 하나의 트랜잭션으로 처리합니다. 미완료 입력부터 복구한 뒤
저장 위치 이후를 이어 읽으므로 기존 결과·리뷰·통계·실행 ID·고정된 Criteria와 Action
정의를 유지합니다. 미완료 추론은 다시 요청할 수 있으며 Jev 요청 비용도 재발생할 수
있습니다. 저장된 결과는 다시 판단하지 않습니다. 엔진과 모델은 원래 실행과 같아야 하며
다른 제공자로 자동 전환하지 않습니다.

수동·cron Batch와 Local/SSH Realtime에 적용합니다. Realtime은 첫 이벤트가 없어도
처음 감시한 위치를 저장합니다. 로컬 파일은 파일 식별자·크기·앞부분 지문으로 검사하고,
SSH는 SFTP에서 이식 가능한 inode를 제공하지 않으므로 크기·앞부분 지문으로 검사합니다.
이는 모든 파일 덮어쓰기를 탐지하는 보장은 아닙니다. 파일 교체·잘림·삭제 등으로 위치를
신뢰할 수 없으면 임의로 처음부터 읽지 않고 복구 실패를 표시합니다. 중단 중 삭제된
파일은 재구성할 수 없습니다.

외부 Action은 실행 전에 실행 의도와 event ID를, 반환 후에는 결과를 저장합니다.
재시작 시 실행 여부가 불확실하면 자동으로 반복하지 않고 판정 결과를 검토 대상으로
보존하며 Action 실패와 설명을 표시합니다. event ID로 외부 목적지를 확인하세요.
자동 중복 실행을 방지하지만 정확히 한 번 전달을 보장하는 구조는 아닙니다.
성공 결과가 저장된 Action은 다시 실행하지 않고 저장된 결과만 복구합니다.

사용자의 Stop·Task 비활성화·Reset은 명시적 종료로 유지됩니다. 데이터 경로마다
DeciFlow 프로세스 하나만 사용해야 합니다. 기존 SQLite에 테이블을 추가하며 이력은
삭제하지 않습니다. 이 기능 이전 실행에는 영구 입력 위치가 없으므로 안전하게 이관할
수 없습니다. 최초 적용 재시작에서는 기존 실행이 종료되고, 이후 새 Run부터 복구를
지원합니다. 데이터 볼륨과 원본 파일을 유지하세요.

Criteria도 **None**으로 저장해 해당 의존성을 잠시 해제할 수 있습니다. Task를 실행하려면 모든 Source에 Criteria를 지정해야 합니다.

정부기관 샘플의 Source·한국어 Criteria·비활성 Batch Task도 시작 시 자동 제공됩니다.
[Sample VOC Central Gov Consulting QnA 설정](voc.ko.md#정부기관-qna-샘플)을 참고하세요.
