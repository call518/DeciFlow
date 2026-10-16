# 사용법

[English](usage.md) | [한국어](usage.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

넓은 화면에서는 왼쪽 **40%**에 **Classification Overview → Task Monitor**, 오른쪽
**60%**에 **Classification Results**를 배치하고 좌우 패널을 독립적으로 스크롤합니다.
좁은 화면은 세로 배치와 일반 페이지 스크롤을 사용합니다.
사이드바에는 로그를 읽는 DeciFlow 노드의 hostname, 확인된 IP, OS·버전을 표시합니다.
WSL·컨테이너에서는 해당 환경의 정보이며 호스트 OS 정보가 아닙니다. IP는 전체
인터페이스 목록이 아닙니다. 대상 SSH 로그 호스트는 Tasks의 Source별로 지정합니다. 엔진명 뒤 괄호의 상태는 마지막 실제 엔진 요청 결과입니다. 예: **Laya (Connected)**. 요청 전에는
Not checked, 이후에는 Connected·Disconnected·Timed out·API error를 표시합니다.
지속적인 상태 검사는 아니며 로컬 입력 거절은 연결 상태를 바꾸지 않습니다.

### Tasks와 판정 기준

**Sources**에 입력을 등록한 후 **Tasks**에 소스별 Criteria·Events/Chunk·Action을
저장합니다. Main은 실행 중·시작 중인 Task를 먼저, 각 그룹 안에서는 이름순으로 표시하며 현재 또는 최근 실행 결과를 보여줍니다. 처음에는 선택하지 않은 상태입니다.
수동 Batch, 시간대를 지정하는 Cron Batch, 연속 Realtime을 지원하며 Paste 입력은
제거했습니다. 저장만으로 분석을 시작하지 않습니다. Task 목록에서 Enabled 토글과 Run·Stop·View·Edit·History·Delete를
사용합니다. Disable은 현재 실행을 중지하고 수동·Cron·자동 재시작을 차단합니다.
Enable만으로 즉시 시작하지는 않습니다. 예약·재시작·저장 정책은 [Tasks](tasks.ko.md)를 참고하세요.

Task 편집의 **Reset Selections**는 사용 가능한 샘플 Source 또는 첫 등록 항목과
샘플 기준·청크당 1이벤트·Action None을 선택합니다. 저장한 설정은 서버에 보관하고
저장하지 않은 초안은 브라우저에만 남습니다. 파일은 브라우저나 Laya가 아닌
DeciFlow가 읽으며 로컬·신뢰 UI Origin과 읽을 수 있는 UTF-8 일반 파일이 필요합니다.

Batch는 선택한 파일을 동시에 읽고 준비된 청크를 교차 공급하며 파일별 순서·프로필·
청크 크기는 유지합니다. 결과는 완료한 최신 순서이므로 병렬 요청은 수집 순서와
다르게 완료될 수 있습니다. 엔진 동시 요청 제한은 파일별이 아닌 전체 실행에 적용하고
값이 1이면 순차 요청합니다. 원격 입력도 로컬 파일과 같은 엔진·Action 흐름을 사용합니다.

선택한 Source에 **Criteria**와 **Events/Chunk**를 지정하세요.
기본값은 **General system**, **청크당 1이벤트**입니다. 현재 비어 있지 않은
한 줄이 1이벤트이며 멀티라인 경계는 아직 자동 인식하지 않습니다. 모든 프로필은
`choice`로 **Normal, Warning, Error, Security, Other** 중 하나를 선택하며 설명과
지시문만 다릅니다. Laya·Jev에 동일한 선택 기준을 적용합니다. 유형은 사용자가
선택합니다. 같은 요청에서 `score`로 긴급도(0–3: Low, Medium, High, Critical),
`noul`로 작업 티켓 발행 필요 확률도 평가합니다. 이 두 운영 질문은 모든
프로필·엔진에서 고정입니다. 각 결과 상단에는 **Category (Choice)**,
**Urgency (Score)** 연속 점수(0–3), **Work Ticket (Noul)** Yes 확률의 상세 카드를
기본 표시하고 좁은 영역에서는 세로로 배치합니다. 배지는 모두 같은 작은 크기
(132×22px)이며 간략 보기나 접기·펼치기 전환은 없습니다. 처리 시간·분류 검토 상태는
카드 아래에 표시합니다. 각 카드에는 범주별·긴급도 단계별(0–3)·티켓 Yes/No의
확률 분포를 각각 표시합니다. No 확률은 `1 − Yes`로 계산하며 세 판단을 합친
확률이 아닙니다. 분류 불확실성 사유는 Category 카드 안에 표시하며
**Category needs review**는 Choice만의 검토 표시입니다. Action 실행·Source·분류 기준·
청크 크기는 별도 라벨로 구분합니다. 티켓을 자동 생성하지 않습니다. 답변 누락·오류는 전체 판정 실패로 처리합니다.

| Criteria 프로필 | 판정 대상 |
| --- | --- |
| General system | 시스템·서비스 동작과 장애 |
| Authentication | 인증·세션 결과, 서비스 장애, 악용 증거 |
| HTTP access | 응답, 요청 실패, 의심 접근 |
| Application | 애플리케이션 작업, 예외, 의존 서비스 |
| Network / tcpdump text | 텍스트의 연결·패킷 증거; 바이너리 PCAP 미지원 |

프로필은 사이드바의 **Criteria**에서 추가·수정·삭제합니다.
결과 범주는 Normal·Warning·Error·Security·Other로 고정하며 `general`은 삭제할 수 없습니다.
**Save Changes** 후 다음 분석부터 적용하고, 실행 중인 작업은 기존 기준을 유지합니다.
저장 위치와 Task 참조에 따른 삭제 제한은 [Criteria 관리](criteria.ko.md)를 참고하세요.
기준에는 사건의 결과와 증거를 설명하고 특정 로그 문자열은 검증 샘플에서 다룹니다.

로그 청크는 요청의 `state` 문자열로 전달합니다. 이벤트 하나 또는 여러 이벤트를
줄바꿈으로 연결한 내용이며, 판정 지시문은 state가 아닌 `questions`에 둡니다.
[요청·결과 예시](results.ko.md)에서 세 질문과 답변을 확인할 수 있습니다.

서로 다른 파일의 이벤트는 섞지 않습니다. Batch는 EOF 잔여분을, Realtime은 설정한
이벤트 수가 차거나 새 이벤트가 1초 동안 없으면 제출하며 파일 회전 경계도 분리합니다.
빈 줄은 제외하고 이벤트 경계를 자동 인식하지는 않습니다. 겹치는 로컬 경로는 설정이
같으면 실제 경로 기준으로 중복 제거하고, 다르면 오류로 알립니다. 청크로 묶어도
모델 입력 예산은 그대로 적용됩니다. 원격 회전은 크기·앞부분 비교를 사용하므로
[SSH 제약](sources.ko.md#ssh-설정)도 확인하세요.

General system은 정상 동작(Normal), 복구 가능한 문제(Warning), 명시적 실패(Error),
악용·정책 위반의 증거(Security)를 구분합니다. 서비스명·IP·보안 관련 주제만으로
보안 사건을 판정하지 않습니다. 기준은 모델의 판단 지침이므로 실제 활용 전
대표 로그로 배포 모델의 판정 정확도를 검증하세요.

Authentication은 개별 시도 실패·중단(Warning), 서비스·지원 기능 장애(Error),
악용 증거(Security)를 구분합니다. Other는 관련 없는 사건이나 결과를 식별할 수
없는 경우이며, 원인을 모른다는 이유만으로 선택하지 않습니다. 인식 가능한
**단일 라인의 전통적 syslog**는 모델 입력에서 시간·호스트명·PID만 제외하고
서비스명·메시지의 사용자·IP·포트는 유지합니다. 원본은 보존하며 변경된
`decisionInput`을 JSON에서 확인할 수 있습니다. 여러 줄 청크와 미지원 형식은
그대로 전달합니다. 정규화는 동일 판정이나 정확도를 보장하지 않습니다.

### 결과와 조작

각 결과의 원본 입력 데이터는 굵게 표시합니다. JSON과 Action 코드는 각자의 서식을
유지합니다.

최근 **판정 완료** 청크부터 기본 페이지당 50건을 표시합니다(Settings → Results에서 10·30·50·100건 선택). 로그 타임스탬프 순서가
아닌 완료 순서입니다. Batch의 **File line(s)**는 실제 파일 라인 번호이고,
Realtime의 **Observed line(s)**는 감시 시작 또는 파일 회전 이후 읽은 라인 순번입니다.
`1 event (max 5)`는 최대 5이벤트 설정에서 실제 1이벤트를 제출했다는 뜻입니다.
JSON의 `chunkEvents`는 설정값, `eventCount`는 실제 이벤트 수입니다.
`line`·`lineEnd`·`lineCount`는 줄 위치·수를 유지합니다.
요청·결과에는 `chunkEvents`를 사용합니다.

#### 불확실성과 사람의 검토

**Uncertain은 DeciFlow 자체 기능**입니다. [`classifier.py`](../classifier.py)에서
엔진 응답을 바탕으로 계산하며, Laya 자체의 불확실성 표시가 아닙니다.
다음 중 하나라도 충족하면 `uncertain=true`로 설정합니다.

| 조건 | JSON `reviewReasons` 값 | 적용 엔진 |
| --- | --- | --- |
| 선택 범주 확률(`probabilities[choice]`)이 70% 미만 | `low_answer_probability` | Laya·Jev |
| 1위와 2위 범주 확률 차이가 10%p 미만 | `close_probabilities` | Laya·Jev |
| 렌더링된 선택지 구분 소실(`usage.options.category.distinct < total`) | `collapsed_options` | 해당 메타데이터가 있는 Laya 응답 |

정확히 70%이거나 차이가 정확히 10%p이면 해당 조건에는 걸리지 않습니다.
70%·10%p는 프로젝트 코드에 고정된 휴리스틱이며, 엔진 요구사항이나 DeciFlow 운영
데이터로 검증한 임계값이 아닙니다. `.env`로 변경할 수 없습니다. 범주 확률은 모델
출력값이지 측정된 정답률이 아닙니다. 엔진 고유 `confidence`는 별도로 보존하며
Uncertain 판단에 사용하지 않습니다.

앞의 두 검사는 **confidence thresholding(신뢰도 임계값 적용)**과
**margin-based uncertainty(마진 기반 불확실성)**에 대응합니다. 능동학습에서 관련
데이터 선택 방식은 least-confidence sampling과 margin sampling이라고 합니다.
Least confidence는 보통 최대 확률을 사용하므로, 엔진이 최대 확률 범주를 선택할 때만
현재 선택 범주 검사와 일치합니다.
[Settles의 능동학습 문헌 조사](https://burrsettles.com/pub/settles.activelearning.pdf)를 참고하세요.
DeciFlow는 예측을 유지하면서 검토 표시를 붙입니다. 정식 reject-option 분류기를
구현하거나 이 표시로 모델을 학습시키지는 않습니다. 세 번째 검사는 통계적 불확실성이
아닌 입력 무결성 문제를 탐지합니다.

예를 들어 Normal 42.1%, Error 21.9%인 **Uncertain · Normal**은 엔진이 Normal을
선택했지만 확률이 70% 미만이라는 뜻입니다. 확정된 정상 이벤트가 아닌 잠정 판정입니다.
원래 범주·확률은 유지하며, 화면에는 잠정 후보를, JSON에는 `candidates`,
`probabilityMargin`, `reviewReasons`를 기록합니다.

**Needs Review**는 판정에 성공한 청크 중 Uncertain 또는 Other인 결과입니다.
요청 실패·거절은 Failed에만 포함하고 검토 지표·필터에서는 제외합니다. Other라는 이유만으로 Uncertain이 되지는 않습니다.
**Certain**은 Uncertain 표시가 없다는 뜻이며 검증된 정확도를 뜻하지 않습니다.
임계값을 운영 정책으로 사용하기 전에 정답이 있는 로그로 오분류와 검토량을 평가하세요.

**All results / Needs Review / No review needed**로 필터링합니다.
Needs Review와 No review needed는 성공 판정만 표시합니다. 실패는 All results와
범주 필터 Request failed를 함께 선택해 확인하세요.
범주 필터와 원본 로그의 대소문자 구분 없는 문자열 검색을 함께 적용할 수 있습니다.
목록에만 적용하며 지표·차트·JSON 내보내기는 전체 결과 기준입니다.

**Source**는 Search data 다음에서 입력한 경로·패턴별 결과를 필터링하고 실패를 포함한
처리 건수를 표시합니다. 중복 매칭은 JSON의 `sourcePatterns`에 모두 남기며 파일은
한 번만 처리합니다. 필터는 목록에만 적용하고 지표·차트·내보내기에는 영향을 주지 않습니다.

**Host**는 선택한 실행에 저장된 호스트별로 필터링하며 Source·범주·검토·로그 검색과
함께 적용합니다. 지표·차트·내보내기는 바뀌지 않습니다. 호스트 수집 상태
(Pending·Reading·Completed·Failed·Stopped)는 판정 건수와 별개입니다. 수집 완료
후에도 판정이 진행 중일 수 있습니다. SSH 접속·읽기 실패는 호스트 정보와 함께
**Source failed**로 표시하고 AI 확률을 만들지 않습니다. All results / Request failed로
확인하며 다른 원격 수집은 계속합니다. [다중 호스트 실행](tasks.ko.md#여러-source-hosts)을 참고하세요.

Main의 Task 결과는 약 1초마다 현재 페이지의 새 결과만 조회하며 기존 카드를 재사용합니다.
다른 화면이나 숨겨진 탭에서는 조회를 멈추고 복귀 시 반영합니다. Task는 계속 실행합니다.
이전 페이지는 고정하며 Latest Results로 최신 결과에 복귀합니다.

| 조작 | 동작 |
| --- | --- |
| Pause Updates / Resume Updates | 첫 결과 전부터 목록을 고정·재개합니다. 분석·지표·차트는 계속 갱신합니다. 필터·페이지 이동은 고정된 목록에 적용하고 버튼에 새 결과 수를 표시합니다. |
| Stop (Tasks) | 파일 읽기·진행 중 요청을 취소하고 완료 결과는 보존합니다. 미제출 청크는 버리며 원격지의 추론은 완료될 수 있습니다. |
| View JSON | 실패 정보, 프로필·청크 정보, 수동 리뷰 값을 포함한 개별 JSON을 펼칩니다. 목록 갱신에도 펼친 상태를 유지합니다. JSON 영역 안의 Copy는 수동 리뷰 값을 포함한 현재 항목을 클립보드에 복사합니다. |
| Reviewer category | `reviewerCategory`를 기록합니다. AI 범주·검토 상태·차트를 바꾸거나 모델을 학습시키지 않습니다. |
| Export All JSON | 실행 중에도 내보내기 시작 시점까지의 Task 전체 결과를 스트리밍합니다. Pause·필터로 숨겨진 결과도 포함합니다. |
| Export Reviewed JSON | 현재 실행에서 reviewerCategory가 비어 있지 않고 AI 원래 Category와 다른 성공 결과만 내보냅니다. 원본 입력·AI 결과·리뷰 값을 포함하며 화면 필터와 무관합니다. 같은 값으로 검토한 항목과 Not reviewed는 제외합니다. |

**Classification Overview**는 불확실한 선택을 포함해 전체 소스의 AI 분류 개수를
합산합니다. 개수는 원본 라인이 아닌 **청크** 기준이며, 비율은 판정에 성공한 청크
기준입니다. 요청 실패는 별도 표시하고 필터·수동 정정은 집계에 영향을 주지 않습니다.
**All / Certain / Uncertain** 버튼으로 차트의 집계 그룹을 선택하며 비율은 선택 그룹
기준입니다. Certain은 Uncertain 표시가 없다는 뜻이며 정확도 보장이 아닙니다.
버튼은 항상 표시됩니다. All은 전체 건수만, Certain·Uncertain은 건수와 전체 판정 성공 청크 대비 비율을
표시합니다. 범주 막대의 비율은 선택 그룹 기준을 유지합니다.
실패 개수는 항상 전체 요청 실패를 표시하며 어느 확실성 그룹에도 포함하지 않습니다.
**Truncated**는 전체 그룹의 `usage.truncated=true` 응답 수입니다. 거절한 판정이므로
실패에 포함하고 범주 막대에서는 제외합니다. 메타데이터 누락·로컬 바이트 예산
초과는 이 수에 포함하지 않습니다. 로그 본문 잘림이며 질문 지시문 잘림 수는 아닙니다.

화면 표시·복사·내보내기 결과 JSON은 `requestedAt`, 엔진, 소스, 처리 시간 등
건별 메타정보를 먼저 표시합니다. 시각은 UTC(`+00:00`)의 ISO 8601 형식이며,
`requestedAt`은 요청 준비 시각으로 처리 완료 시각이 아닙니다.
결과 JSON에 `requestedModel`, UTC `requestedAt`, 요청 크기, 입력 예산과
질문·판정 기준을 남깁니다. `providerResponse`에는 응답 모델, 실제 체크포인트
`routing`, 토큰·잘림 정보 `usage`, 엔진별 confidence와 action·abstention 등
전체 응답을 보존합니다. 최상위 `answerProbability`는 선택 범주의 확률이며,
`confidence`는 엔진 원래 값입니다. `uncertaintyBasis`로 70% 임계값에 적용한
선택 범주 확률 척도를 명시합니다. HTTP 상태와 제공된 요청 ID·추론 시간 헤더도 남기며
인증 키·Authorization 헤더는 제외합니다. API 실패·판정 거절 시에도 확보한
진단 정보를 보존합니다. Laya의 `model`은 공통 이름일 수 있으므로 실제 모델은
`providerResponse.routing`에서 확인하세요.

[결과 JSON 예시와 필드 설명](results.ko.md)

### 새로고침과 재접속

사이드바 경로는 Main `/`, Source `/#sources`, Criteria `/#criteria`,
Actions `/#actions`, Tasks `/#tasks`, Settings `/#settings`입니다.
Source·Criteria·Actions·Tasks는 Main의 하위 메뉴입니다. Settings의 SSH Keys
`/#settings/ssh-keys`·SSH Hosts `/#settings/ssh-hosts`는 선택한 섹션만 표시하며
Settings 자체는 SSH Keys·SSH Hosts로 이동하는 목록을 표시합니다.
모든 화면은 제목·짧은 설명 아래에 본문 카드를 배치합니다. Main의 엔진 연결 상태는
오른쪽에 유지하며 SSH 화면에는 중복 섹션 제목을 표시하지 않습니다.
사이드바 메뉴를 선택하면 항상 목록으로 돌아가며 View·Edit·History 화면을 닫습니다.
미저장 편집 초안은 버리고 저장된 설정과 실행 중인 Task는 유지합니다.
연결이 끊기거나 브라우저를 닫아도 Task는 계속 실행합니다. 새로고침은 같은 실행에
재접속하며 History → View Results는 판정·Action을 반복하지 않고 저장된 결과를
재생합니다. Main은 선택한 Task의 새 실행을 따라가며 이력에서 특정 실행을 열면
해당 실행을 유지합니다.

Task 정의·실행 상태·설정 스냅샷·결과·Action 실행 결과를
`DECIFLOW_DATA_DIR`에 보존합니다(Task 메타데이터는 `tasks/`, 결과는 `results.sqlite3`). 재시작 시 중단된 실행은 Stopped로 표시합니다.
Batch는 자동 재시도하지 않으며 Realtime은 Resume on restart가 켜진 경우에만
새 실행을 시작합니다. [Tasks](tasks.ko.md)를 참고하세요.

데이터 경로마다 DeciFlow 서버 프로세스·인스턴스 하나를 사용합니다. 결과와 수동
정정은 SQLite에 저장하며 브라우저는 현재 페이지만 유지합니다. 필터·페이지 위치·
미저장 초안은 브라우저에만 남습니다. 자동 이력 정리는 없습니다.
[결과 저장](result-storage.ko.md)을 참고하세요.

저수준 `/api/classify` 텍스트 API와 `/api/file-source` 파일 API는 유지합니다.
`persist: true`는 HTTP 202로 브라우저와 독립된 **임시 SQLite 작업**을 생성하며
저장된 Task나 영속 실행을 만들지 않습니다. `/api/jobs/<jobId>`는 조회,
`/events`는 NDJSON 재생·수신, `/stop`은 실행 중지를 제공합니다(POST).
`persist: true`가 없으면 연결 단위 스트리밍입니다. 출처 검사는 동일하며
파일 접근에는 로컬·신뢰 UI Origin이 필요합니다.

### 시간 지표

| 지표 | 의미 |
| --- | --- |
| Success / Failed / Total | 유효한 판정 성공 청크 / 실패 청크 / 처리 완료 전체 청크(성공 + 실패). 연결 오류·시간 초과·입력 거절·응답 검증 실패를 실패에 포함 |
| Action Success / Failed / Total | 완료된 Action 성공 / 실패 / 전체 실행 수. Action 미할당·의사결정 실패 청크는 제외하며 의사결정 집계와 독립 |
| Needs Review | 성공 판정 중 Uncertain(낮은 확률·근접한 확률·선택지 구분 소실) 또는 Other. 실패·거절은 제외 |
| Throughput | 최근 5초의 성공 판정 청크/초; 유휴시간 포함, 시작 후 5초 미만은 경과시간 기준; 중지·완료 시 마지막 값 유지 |
| Total Elapsed Time | 실행 시작 이후 전체 경과시간; 유휴시간 포함 |
| Active Processing Time | 요청이 하나 이상 진행 중인 구간을 중복 없이 합산; 전체 경과시간 대비 비율 |
| Average Processing Time | 실패를 포함한 완료 요청의 평균 소요시간; 청크 기준 |

Total Elapsed Time·Active Processing Time·Average Processing Time은 값에 따라
ms·sec·min·hour·day로 표시합니다. JSON 시간값은 밀리초를 유지합니다.

Action 실행 실패는 판정 성공·실패 집계나 엔진 연결 상태에 영향을 주지 않습니다.

Active·Average에는 네트워크·서버 대기가 포함됩니다. Active는 유휴시간을 제외하며
전체 경과시간 대비 0~100%입니다. CPU·GPU 가동률이나 순수 추론시간이 아닙니다.
대기 중 시간 정보는 1초마다 갱신합니다. 연결이 끊기면 브라우저 표시만 멈추며
재접속 시 서버 진행 상태를 복원합니다. 중지 시 마지막 값을 보존하므로
약 1초의 차이가 있을 수 있습니다.


Task 처리량은 최근 5초를 100ms 버킷으로 집계하므로 경계에서 근사값입니다.

모든 목록 Delete는 공통 디자인의 확인창을 사용합니다. 취소·Esc·닫기는 변경하지 않습니다. Source·Criteria·Actions 삭제는 승인 후 Save Changes로 확정하며 Task·SSH Keys·SSH Hosts는 승인 즉시 서버에 적용합니다.

Delete를 누르면 서버에서 현재 의존성을 먼저 확인합니다. 사용 중인 항목은 Task·SSH Host·Source·실행 중 작업 이름을 최대 5개와 추가 건수로 표시하는 차단창만 제공하고 삭제 버튼을 숨깁니다. 참조가 없을 때만 삭제 확인창을 보여줍니다. 의존성 확인 실패 시에도 삭제하지 않으며 서버는 실제 삭제·저장 시 다시 검사합니다.

목록 View는 선택한 행 바로 아래에 상세를 펼칩니다. 같은 View를 다시 누르면 접고 다른 항목을 누르면 상세를 이동합니다. 목록 갱신 후에도 선택한 행 아래 위치를 유지합니다.

모든 View는 공통 라벨·값 형식으로 표시합니다. 짧은 값은 나란히 배치하고 긴 값만 필요한 만큼 줄바꿈합니다. 읽기 전용 입력칸은 사용하지 않으며 코드·공개키는 내용을 보존하는 제한 높이의 텍스트 블록으로 표시합니다. 좁은 화면에서는 세로로 배치하며 편집 폼에는 영향을 주지 않습니다.

Task Monitor는 모든 저장된 Task를 표시하며 실행 중·시작 중인 항목을 먼저 배치합니다.
카드는 이름·Enabled/실행 상태 배지, Source·중복을 뺀 Source Host 수,
Type / Mode / Action 순서로 표시하고 Action이 없으면 None을 표시합니다.
Running·Starting 배경은 연한 녹색, Stopped는 차분한 중간색이며 선택 항목은 왼쪽
강조선을 유지합니다. 항목 위에서 마우스를 1초간 움직이지 않거나 키보드 포커스를 두면 스크롤 가능한 말풍선에서 전체
Source 설정과 호스트 이름·SSH 주소를 확인합니다. 클릭하면 현재·최근 실행 결과를
열고 이력이 없으면 빈 결과를 표시합니다. 시작·중지는 Tasks에서 관리합니다.
예약과 기본 Task 복구는 [Tasks](tasks.ko.md)를 참고하세요.

말풍선이 열린 뒤에는 Task 카드나 말풍선 위에서 마우스를 움직여도 유지합니다.
말풍선으로 이동해 텍스트를 선택·복사할 수 있으며 양쪽에서 벗어나면 닫힙니다.
