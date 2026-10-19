# 사용법

[English](usage.md) | [한국어](usage.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

넓은 화면에서는 왼쪽 **40%**에 **Classification Overview → Task Monitor**, 오른쪽
**60%**에 **Classification Results**를 배치하고 좌우 패널을 독립적으로 스크롤합니다.
좁은 화면은 세로 배치와 일반 페이지 스크롤을 사용합니다.
사이드바에는 로그를 읽는 DeciFlow 노드의 hostname, 확인된 IP, OS·버전을 표시합니다.
WSL·컨테이너에서는 해당 환경의 정보이며 호스트 OS 정보가 아닙니다. IP는 전체
인터페이스 목록이 아닙니다. 대상 SSH 로그 호스트는 Tasks의 Source별로 지정합니다. 엔진 상태는 페이지를 열거나 새로고침하면 Checking…으로 시작합니다. DeciFlow 백엔드에서 추론 없이 Laya `GET /health` 또는 Jev `GET /v1/models`를 한 번 호출합니다. HTTP 점검 성공은 Reachable로 표시하며 모델 준비나 공개 health 엔드포인트를 쓰는 Laya 버전의 인증까지 보장하지 않습니다. 이후 새 분류 요청 결과에 따라 Operational·Unreachable·Timed Out·Auth Error·API Error를 표시합니다. 툴팁에는 확인 근거와 시각을 표시합니다. 과거 결과와 로컬 입력 거절은 상태를 바꾸지 않고, 화면 전환은 HTTP 점검을 반복하지 않습니다. 늦게 끝난 HTTP 점검은 실제 요청 결과를 덮어쓰지 않습니다. 지속적인 상태 감시는 아닙니다. DeciFlow 점검 경로가 없으면 Check Unavailable(UI 서버 재시작 필요), 점검 요청 자체가 실패하면 Check Failed를 표시해 엔진 API Error와 구분합니다.

### Tasks와 판정 기준

**Sources**에 입력을 등록한 후 **Tasks**에 소스별 Criteria·Events/Chunk·Action을
저장합니다. Main은 활성화된 Task 중 실행 중·시작 중인 Task를 먼저, 각 그룹 안에서는 이름순으로 표시하며 현재 또는 최근 실행 결과를 보여줍니다. 처음에는 선택하지 않은 상태입니다.
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

Criteria는 Choice·Score·Noul 판단 항목의 개수·선택지·단계를 설정합니다.
기존 시스템 프로필은 Category·Urgency·Work Ticket을 유지하고 사용자 프로필은
자신의 판단 항목을 지정합니다. TEXT는 비어 있지 않은 줄을 묶으며 JSONL은 설정한
본문 필드를 추출해 한 줄의 객체를 한 건씩 처리합니다. [Criteria](criteria.ko.md)를 참고하세요.

모든 판단 항목을 설정된 순서대로 작은 카드로 표시합니다.
**Probabilities and Criteria**에서 항목별 확률과 기준을 펼칩니다. **Review**로
타입별 수정값을 기록합니다. Choice 불확실성은 항목별로 표시하며 어느 Choice든 검토가
필요하면 Needs Review가 됩니다. 차트의 확실성은 선택한 Choice 기준입니다. 각 판단은
별개이며 확률을 하나로 합치지 않습니다. 티켓을 자동 생성하지 않고 답변 누락·오류는
전체 요청 실패로 처리합니다.

| Criteria 프로필 | 판정 대상 |
| --- | --- |
| Sample General System | 시스템·서비스 동작과 장애 |
| Sample Authentication | 인증·세션 결과, 서비스 장애, 악용 증거 |
| Sample HTTP access | 응답, 요청 실패, 의심 접근 |
| Sample Application | 애플리케이션 작업, 예외, 의존 서비스 |
| Sample Network / tcpdump text | 텍스트의 연결·패킷 증거; 바이너리 PCAP 미지원 |

프로필은 사이드바의 **Criteria**에서 추가·수정·삭제합니다.
시스템 프로필은 Normal·Warning·Error·Security·Other를 유지하고 사용자 프로필은
선택지를 지정합니다. **Sample General System**도 다른 프로필과 동일한 편집·삭제 규칙을 따릅니다.
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

Sample General System은 정상 동작(Normal), 복구 가능한 문제(Warning), 명시적 실패(Error),
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

Show Decisions와 검토·호스트 컨트롤은 위에, 가로 공간을 활용하는 결과 필터는 아래에 배치합니다.
필터 종류는 Search Text, Processing Status, Source, Host, Review Status 순서이며 처음에는 Search Text를 선택합니다.

왼쪽 **Filter Type**에서 종류를 선택하고 오른쪽에서 값을 지정합니다. Review Status,
Processing Status, Host, Source는 풀다운이며 Search Text는 검색창입니다. 종류만 바꾸면 결과를
새로 조회하지 않으며 기존 조건도 유지합니다. 여러 조건은 AND로 적용하며 도구 아래의
작은 버튼으로 표시합니다. 버튼을 누르면 해당 조건을 해제하고 **Clear All**로 전체를
초기화합니다. 긴 Source 값은 버튼에서 줄여 표시하며 툴팁에 전체 경로를 제공합니다.

각 결과의 원본 입력 데이터는 굵게 표시합니다. JSON과 Action 코드는 각자의 서식을
유지합니다.

최근 **판정 완료** 청크부터 기본 페이지당 30건을 표시합니다(Settings → Configurations에서 10·30·50·100건 선택). 로그 타임스탬프 순서가
아닌 완료 순서입니다. Batch의 **File line(s)**는 실제 파일 라인 번호이고,
Realtime의 **Observed line(s)**는 감시 시작 또는 파일 회전 이후 읽은 라인 순번입니다.
`1 event (max 5)`는 최대 5이벤트 설정에서 실제 1이벤트를 제출했다는 뜻입니다.
JSON의 `chunkEvents`는 설정값, `eventCount`는 실제 이벤트 수입니다.
`line`·`lineEnd`·`lineCount`는 줄 위치·수를 유지합니다.
요청·결과에는 `chunkEvents`를 사용합니다.

결과 필터는 어떤 카드를 볼지 정합니다. **Processing Status**, **Source**,
**Host**, **Review Status**, **Search Text**를 제공하며, Processing Status는
**All Statuses**, **Successful**, **Failed**를 선택합니다. Failed는 Source·입력 처리·
엔진 요청·응답 검증 실패를 포함하고 Action 실행 상태는 별도입니다.
조건은 저장된 전체 실행에 AND로 적용합니다. Clear All은 결과 필터만 지웁니다.

**Show Decisions**는 별도의 표시 설정입니다. 메뉴의 체크박스로 여러 판단 항목을
고르면 카드에 해당 판단만 표시하고 **Show All**은 모든 판단을 복원합니다.
메뉴 바깥을 클릭하거나 Escape를 누르면 닫힙니다. 여러 Criteria는 그룹 제목으로
구분합니다. 표시 변경은 카드를 걸러내거나 건수·페이지를
바꾸지 않으며 결과 조회·재분석도 하지 않습니다. 실패 카드는 유지하고 선택한 판단이
없는 카드에는 안내 문구를 표시합니다. Review·Response·Result JSON과 내보내기는
전체 결과를 유지하며 차트 선택도 독립적입니다. 실행을 새로 열면 모든 판단을 표시합니다.

#### 불확실성과 사람의 검토

**Uncertain은 DeciFlow 자체 기능**입니다. [`classifier.py`](../classifier.py)에서
엔진 응답을 바탕으로 계산하며, Laya 자체의 불확실성 표시가 아닙니다.
각 Choice에서 다음 중 하나라도 충족하면 `decisionAssessments[id].uncertain=true`로
설정합니다. 항목별 불확실성은 `decisionAssessments`에 저장합니다.

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

**Needs Review**는 어느 판단 항목이든 Uncertain이거나 `reviewOptions`로 지정한 선택,
지시문 축약 등의 검토 사유가 있는 성공 청크를 한 번씩 집계합니다.
요청 실패·거절은 Failed에만 포함하고 검토 지표·필터에서는 제외합니다. Other라는 이유만으로 Uncertain이 되지는 않습니다.
**Certain**은 Uncertain 표시가 없다는 뜻이며 검증된 정확도를 뜻하지 않습니다.
임계값을 운영 정책으로 사용하기 전에 정답이 있는 로그로 오분류와 검토량을 평가하세요.

**All Results / Needs Review / No Review Needed**로 필터링합니다.
Needs Review와 No Review Needed는 성공 판정만 표시합니다. 실패는 All Results와
Processing Status → Failed를 함께 선택해 확인하세요.
처리 상태 필터와 원본 로그의 대소문자 구분 없는 문자열 검색을 함께 적용할 수 있습니다.
목록에만 적용하며 지표·차트·JSON 내보내기는 전체 결과 기준입니다.

**Source**는 Search data 다음에서 입력한 경로·패턴별 결과를 필터링하고 실패를 포함한
처리 건수를 표시합니다. 중복 매칭은 JSON의 `sourcePatterns`에 모두 남기며 파일은
한 번만 처리합니다. 필터는 목록에만 적용하고 지표·차트·내보내기에는 영향을 주지 않습니다.

**Host**는 선택한 실행에 저장된 호스트별로 필터링하며 Source·범주·검토·로그 검색과
함께 적용합니다. 지표·차트·내보내기는 바뀌지 않습니다.
**Source Hosts Detail**을 누르면 스크롤 가능한 모달에서 완료 건이 없는 호스트까지
전체 실행의 호스트별 수집 상태와 Success / Failed / Total을 확인합니다.
모달을 열 때 호스트에 다시 접속하지 않습니다. 호스트 수집 상태
(Pending·Reading·Completed·Failed·Stopped)는 판정 건수와 별개입니다. 수집 완료
후에도 판정이 진행 중일 수 있습니다. SSH 접속·읽기 실패는 호스트 정보와 함께
**Source failed**로 표시하고 AI 확률을 만들지 않습니다. Processing Status → Failed로
확인하며 다른 원격 수집은 계속합니다. [다중 호스트 실행](tasks.ko.md#여러-source-hosts)을 참고하세요.

Main의 Task 결과는 약 1초마다 현재 페이지의 새 결과만 조회하며 기존 카드를 재사용합니다.
다른 화면이나 숨겨진 탭에서는 조회를 멈추고 복귀 시 반영합니다. Task는 계속 실행합니다.
이전 페이지는 고정하며 Latest Results로 최신 결과에 복귀합니다.

| 조작 | 동작 |
| --- | --- |
| Pause Display Updates / Resume Display Updates | 첫 결과 전부터 목록을 고정·재개합니다. 분석·지표·차트는 계속 갱신합니다. 필터·페이지 이동은 고정된 목록에 적용하고 버튼에 새 결과 수를 표시합니다. |
| Stop (Tasks) | 파일 읽기·진행 중 요청을 취소하고 완료 결과는 보존합니다. 미제출 청크는 버리며 원격지의 추론은 완료될 수 있습니다. |
| ▲ / ▼ | Classification Results 우측 아래 플로팅 버튼으로 현재 결과 영역의 최상단·최하단으로 이동합니다. 페이지를 바꾸거나 분석을 실행하지 않습니다. 좁은 화면에서는 결과 영역의 시작·끝으로 페이지를 스크롤합니다. |
| Details | Action 실행, Source·Host·레코드 위치, Criteria·Chunk 정보를 펼칩니다. 처음에는 접혀 있으며 Action 실패는 카드에 바로 표시합니다. 목록 갱신·페이지 이동에도 펼침 상태를 유지하고 전체 정보는 View Result JSON에도 남습니다. |
| Response | Review와 같은 접기·펼치기 형식으로 Laya·Jev 응답, HTTP 상태, 검증 사유를 확인합니다. Copy로 응답 상세 정보를 복사하며 JSON이 아닌 응답과 응답 없음도 구분합니다. |
| View Result JSON | 실패 정보, 프로필·청크 정보, 수동 리뷰 값을 포함한 개별 JSON을 펼칩니다. 목록 갱신에도 펼친 상태를 유지합니다. JSON 영역 안의 Copy는 수동 리뷰 값을 포함한 현재 항목을 클립보드에 복사합니다. |
| Review | 판단 항목별 타입에 맞는 수정값을 기록합니다. AI 예측·검토 표시·차트·모델 가중치는 바꾸지 않습니다. |
| Export All JSON | 실행 중에도 내보내기 시작 시점까지의 Task 전체 결과를 스트리밍합니다. Pause·필터로 숨겨진 결과도 포함합니다. |
| Export Reviewed JSON | 어떤 항목이든 AI와 다른 수정값이 있는 성공 결과를 원래 답변·reviewerDecisions와 함께 내보냅니다. 비우거나 원래 값과 같은 수정은 제외하며 화면 필터는 무시합니다. |

여러 분류 체계가 있으면 **Criteria**로 선택한 뒤 **Decision**에서 모든 판단 항목의 집계를 볼 수 있습니다. Criteria나 판단
항목이 하나면 텍스트로 표시합니다. 기본 선택은 Default Chart Decision이며 **Set as Default**로 재분석 없이 변경합니다. Choice는 선택지별 건수, Score는 가중 점수를 가장 가까운 수준으로 반올림한
분포(중간값 올림), Noul은 Yes 확률의 [0%, 25%), [25%, 50%), [50%, 75%), [75%, 100%] 구간을 표시합니다. 누락
답변과 실패는 제외합니다. All / Certain / Uncertain은 선택한 Choice 기준입니다. 근거가 없으면 Certain이 아닌
**Not Assessed**로 표시합니다. Score·Noul에는 확실성 그룹을 적용하지 않습니다. 항목 전환은 저장된 결과만 사용하며
재분석하지 않습니다.

**Classification Overview**는 불확실한 선택을 포함해 전체 소스의 AI 분류 개수를
합산합니다. 개수는 원본 라인이 아닌 **청크** 기준이며, 비율은 판정에 성공한 청크
기준입니다. 요청 실패는 별도 표시하고 필터·수동 정정은 집계에 영향을 주지 않습니다.
**All / Certain / Uncertain** 버튼으로 차트의 집계 그룹을 선택하며 비율은 선택 그룹
기준입니다. Certain은 Uncertain 표시가 없다는 뜻이며 정확도 보장이 아닙니다.
Choice 버튼은 건수를 표시하고 Not Assessed는 해당 건이 있을 때 표시합니다. All은 전체 건수만, Certain·Uncertain은 건수와 전체 판정 성공 청크 대비 비율을
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
`DECIFLOW_DATA_DIR`에 보존합니다(설정과 결과 모두 `deciflow.sqlite3`). 체크포인트가
있는 Running 실행은 재시작 후 같은 실행 ID로 복구하고 Paused·Pausing은 Paused로
복구합니다. 체크포인트가 없는 구버전 실행은 Stopped로 정리합니다. 선택적 Realtime
시작 옵션은 복구할 실행이 없을 때만 새 실행을 만듭니다. [Tasks](tasks.ko.md)를 참고하세요.

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
| Needs Review | 항목별·기록 전체 검토 사유가 있는 성공 청크를 중복 없이 집계. 실패·거절 제외 |
| Throughput | 선택한 실행의 전체 성공 결과 수 ÷ 전체 경과 초; 유휴시간·Action 전달 대기 포함, 중지·완료 시 마지막 값 유지 |
| Total Elapsed Time | 실행 시작 이후 전체 경과시간; 유휴시간 포함 |
| Active Processing Time | 요청이 하나 이상 진행 중인 구간을 중복 없이 합산; 전체 경과시간 대비 비율 |
| Processing Time | 다른 지표와 같은 크기의 작은 박스 안에 Avg·Min·Max·P(50)·P(95)·P(99) 라벨과 값을 나란히 표시합니다. 실패를 포함한 전체 완료 레코드 기준이며 Action 시간은 제외합니다. Avg는 산술평균, P(50)은 가운데 값의 평균, P(95)·P(99)는 nearest-rank 방식입니다. |

Total Elapsed Time·Active Processing Time·Processing Time의 값은 크기에 따라
ms·sec·min·hour·day로 표시합니다. JSON 시간값은 밀리초를 유지합니다.

Action 실행 실패는 판정 성공·실패 집계나 엔진 연결 상태에 영향을 주지 않습니다.

Active·Average에는 네트워크·서버 대기가 포함됩니다. Active는 유휴시간을 제외하며
전체 경과시간 대비 0~100%입니다. CPU·GPU 가동률이나 순수 추론시간이 아닙니다.
대기 중 시간 정보는 1초마다 갱신합니다. 연결이 끊기면 브라우저 표시만 멈추며
재접속 시 서버 진행 상태를 복원합니다. 중지 시 마지막 값을 보존하므로
약 1초의 차이가 있을 수 있습니다.

시간 지표는 필터·페이지·목록 일시정지와 무관하게 선택한 실행 전체를 집계합니다.
Throughput은 소수 셋째 자리까지 표시하며 양수이지만 0.001 미만이면 `<0.001 chunks/s>`로
표시합니다. 실제 결과 전달 속도이며 엔진의 최대 성능은 아닙니다. 완료 건이 없으면
P(50)·P(95)·P(99)는 N/A입니다. 표본이 작으면 P(95)·P(99)가 최댓값과 같을 수 있습니다.

SQLite에 처리 시간별 건수를 증분 갱신합니다. 분위수는 원문 결과를 다시 읽거나 정렬하지
않고 시간별 건수를 순서대로 집계합니다. 기존 실행은 처음 조회할 때 과거 건수에 비례하는
한 번의 히스토그램 생성을 수행하고 이후 재사용합니다. 근사 샘플링이나 추가 의존성은 없습니다.

모든 목록 Delete는 공통 디자인의 확인창을 사용합니다. 취소·Esc·닫기는 변경하지 않습니다. Source·Criteria·Actions 삭제는 승인 후 Save Changes로 확정하며 Task·SSH Keys·SSH Hosts는 승인 즉시 서버에 적용합니다.

Delete를 누르면 서버에서 현재 의존성을 먼저 확인합니다. 사용 중인 항목은 Task·SSH Host·Source·실행 중 작업 이름을 최대 5개와 추가 건수로 표시하는 차단창만 제공하고 삭제 버튼을 숨깁니다. 참조가 없을 때만 삭제 확인창을 보여줍니다. 의존성 확인 실패 시에도 삭제하지 않으며 서버는 실제 삭제·저장 시 다시 검사합니다.

목록 View는 선택한 행 바로 아래에 상세를 펼칩니다. 같은 View를 다시 누르면 접고 다른 항목을 누르면 상세를 이동합니다. 목록 갱신 후에도 선택한 행 아래 위치를 유지합니다.

모든 View는 공통 라벨·값 형식으로 표시합니다. 짧은 값은 나란히 배치하고 긴 값만 필요한 만큼 줄바꿈합니다. 읽기 전용 입력칸은 사용하지 않으며 코드·공개키는 내용을 보존하는 제한 높이의 텍스트 블록으로 표시합니다. 좁은 화면에서는 세로로 배치하며 편집 폼에는 영향을 주지 않습니다.

Task Monitor는 활성화된 Task를 표시하며 실행 중·시작 중인 항목을 먼저 배치합니다.
카드는 이름·Enabled/실행 상태 배지, Source·중복을 뺀 Source Host 수,
Type / Mode / Action 순서로 표시하고 Action이 없으면 None을 표시합니다.
Running·Starting 배경은 연한 녹색, Stopped는 차분한 중간색이며 선택 항목은 왼쪽
강조선을 유지합니다. 항목 위에서 마우스를 1초간 움직이지 않거나 키보드 포커스를 두면 스크롤 가능한 말풍선에서 전체
Source 설정과 호스트 이름·SSH 주소를 확인합니다. 클릭하면 현재·최근 실행 결과를
열고 이력이 없으면 빈 결과를 표시합니다. 시작·중지는 Tasks에서 관리합니다.
예약과 기본 Task 복구는 [Tasks](tasks.ko.md)를 참고하세요.

말풍선이 열린 뒤에는 Task 카드나 말풍선 위에서 마우스를 움직여도 유지합니다.
말풍선으로 이동해 텍스트를 선택·복사할 수 있으며 양쪽에서 벗어나면 닫힙니다.

Settings의 **Configurations**은 유지보수 항목을 제공합니다. **Reset DeciFlow**는
삭제 경고창에서 **Yes, Reset DeciFlow**를 눌러야 실행하며 취소하면 변경하지 않습니다.
사용 전 [초기화 범위와 재시작](configuration.ko.md#deciflow-초기화)을 확인하세요.

불확실한 Choice 결과는 판단 항목 제목 옆에 작은 Uncertain 상태 배지를 따로 표시합니다.
판단값은 분류 색상을 유지하며 요약·상세 카드 모두 긴 값을 줄바꿈하여 표시합니다.


## 토큰 경고

저장된 실행을 포함해 해당 결과의 내용 위에 주황색 경고를 표시합니다.

- **Input Token Limit**: 엔진이 `usage.truncated=true`를 보고한 경우입니다. 새 부분 판정은 거절하며 원본 입력은 보존합니다. Laya·Jev가 보고한 경우 모두 적용합니다.
- **Criteria Shortened**: 엔진이 항목 ID별 `usage.criteria_tokens_dropped`를 보고한 경우입니다. 판정을 유지하면서 Needs Review로 표시합니다. 로컬 `laya_server.py` 어댑터는 실제 토크나이저로 지시문·선택지의 누락 토큰을 계산하며 선택지 설명의 개별 상한도 포함합니다. 모델 한도 내에서 `LAYA_HEAD_TOKENS`를 늘리거나 Criteria를 줄이세요. 질문이 길어지면 본문 공간은 줄어듭니다.
- **Request Size Limit**: Jev의 로컬 바이트 예산을 초과하여 전송 전에 거절한 경우입니다. 토큰 잘림이 아니므로 Truncated 수에 포함하지 않습니다.

기본 Compose Laya 서버와 외부 제공자는 Criteria 축약을 보고하지 않을 수 있습니다.
경고가 없다고 전체 보존이 확인된 것은 아닙니다. 현재 응답 계약에는 별도의 출력 잘림
신호가 없어 토큰 수나 잘못된 답변만으로 출력 잘림을 추측하지 않습니다. 유효하지 않은
답변은 기존 검증으로 거절합니다.

## 공유 가능한 URL

해시만 사용하는 주소 대신 일반 경로를 사용합니다. 브라우저 주소를 복사하거나 조회
링크를 새 탭으로 열 수 있고, 새로고침·뒤로/앞으로 이동으로 같은 대상을 복원합니다.
기존 `/#tasks`, `/#settings/...` 링크는 자동으로 변환합니다.

| 대상 | 경로 |
| --- | --- |
| Tasks 목록 | `/tasks` |
| Task 상세 / 이력 / 편집 | `/tasks/{id}`, `/tasks/{id}/history`, `/tasks/{id}/edit` |
| Source·Criteria·Action | `/sources/{id}`, `/criteria/{id}`, `/actions/{id}` |
| SSH Key / Host | `/settings/ssh-keys/{id}`, `/settings/ssh-hosts/{id}` |
| 등록 항목 추가 / 편집 | 목록 경로에 `/new`, 항목 경로에 `/edit` 추가 |
| Configurations | `/settings/configuration` |
| 특정 실행 | `/runs/{run-id}` |

실행 URL에는 결과 필터·커서 페이지·특정 결과의 펼친 영역을 쿼리 매개변수
(`review`, `processing`, `host`, `source`, `search`, `cursors`, `through`, `result`,
`detail`)로 유지합니다. Source Hosts Detail은 `dialog=hosts`를 사용합니다.
자동 갱신은 현재 주소를 교체하며 갱신마다 방문 기록을 쌓지 않습니다.
Run·Stop·Pause/Resume·Delete·Save·Export는 명시적 명령으로 유지하여 링크를 여는
것만으로 실행되지 않습니다. 미저장 입력값·인증 정보는 URL에 넣지 않습니다.
삭제된 항목이나 실행은 사용할 수 없다고 표시합니다.

일반 경로로 직접 접속하려면 DeciFlow UI 서버/컨테이너를 한 번 재시작해야 합니다.
모든 경로가 DeciFlow로 전달된다면 별도 프록시 rewrite는 필요 없습니다. 공유 링크에도
기존 접근·Origin 규칙이 적용됩니다. 미저장 초안이나 삭제된 Task를 별도 보관하는
기능은 아닙니다.
