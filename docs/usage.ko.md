# 사용법

[English](usage.md) | [한국어](usage.ko.md) | [README](../README.ko.md)

넓은 화면에서는 왼쪽 **40%**에 **Classification overview → Log input**, 오른쪽
**60%**에 **Classification results**를 배치합니다. 좁은 화면은 세로로 표시합니다.
사이드바에는 DeciFlow 로그 소스 노드의 hostname, 확인된 IP, OS·버전을 표시합니다.
WSL·컨테이너에서는 해당 환경의 정보이며 호스트 OS 정보가 아닙니다. IP는 전체
인터페이스 목록이 아닙니다. 엔진명 뒤 괄호의 상태는 마지막 실제 엔진 요청 결과입니다. 예: **Laya (Connected)**. 요청 전에는
Not checked, 이후에는 Connected·Disconnected·Timed out·API error를 표시합니다.
지속적인 상태 검사는 아니며 로컬 입력 거절은 연결 상태를 바꾸지 않습니다.

### 입력과 판정 기준

**Reset sources**는 Add source 옆에서 현재 Batch·Realtime의 기본 샘플 경로와
General system·Events/chunk 1·Action None을 복원합니다. 분석 중에는 비활성화합니다.

기본 모드는 **Batch**이며, 각 모드에 수정 가능한 예시가 입력되어 있습니다.

| 모드 | DeciFlow가 읽는 데이터 |
| --- | --- |
| Realtime | 기존 파일 끝 이후의 새 줄; 새 파일·교체 파일은 처음부터 |
| Batch | 매칭 파일의 처음부터 EOF까지 |
| Paste | 붙여 넣은 텍스트를 청크로 묶어 처리 |

UI·내보내기 JSON의 모드명은 `realtime`, `batch`, `paste`입니다.
파일 API는 기존 `follow` 요청도 받으며 응답에는 `realtime`을 사용합니다.

파일은 **Laya 호스트가 아닌 DeciFlow 실행 노드**에 있어야 합니다. 파일 입력에는
로컬 브라우저 접속(`localhost`·`127.0.0.1`)과 읽기 가능한 UTF-8 일반 파일이
필요합니다. 각 소스 항목의 입력폼에 경로·패턴을 입력합니다. 샘플 3개가 미리
입력되며 **Remove**로 제거하거나 **Add source**로 추가합니다. **Path** 라벨과
입력폼은 한 줄에 표시하며, 각 항목에 Criteria·Events/chunk·Action을 지정합니다.
수정한 경로는 페이지를 사용하는 동안 Batch·Realtime 모드별로 유지됩니다.
분석을 시작하기 전에 모든 소스 항목에 경로를 입력해야 합니다. 절대 경로, 여러 디렉터리, `*`, `?`,
`[abc]`, 재귀 `**`를 지원합니다. 상대 경로는 DeciFlow 실행 디렉터리 기준입니다.
Batch는 매칭 파일이 필요하고 Realtime은 새 매칭 파일을 기다릴 수 있습니다.
Batch는 선택한 파일을 동시에 읽고 준비된 청크를 교차 공급합니다. 파일별 라인 순서·
분류 기준·청크 크기는 유지합니다. 엔진 동시 요청 제한은 파일별이 아닌 전체 실행에
적용하며, 값을 1로 설정하면 판정 요청은 순차 처리됩니다.

각 경로·패턴 또는 Paste에 **Criteria**와 **Events/chunk**를 지정하세요.
기본값은 **General system**, **청크당 1이벤트**입니다. 현재 비어 있지 않은
한 줄이 1이벤트이며 멀티라인 경계는 아직 자동 인식하지 않습니다. 모든 프로필은
`choice`로 **Normal, Warning, Error, Security, Other** 중 하나를 선택하며 설명과
지시문만 다릅니다. Laya·Jev에 동일한 선택 기준을 적용합니다. 유형은 사용자가
선택하며 `score`·`noul`은 사용하지 않습니다.

| Criteria 프로필 | 판정 대상 |
| --- | --- |
| General system | 시스템·서비스 동작과 장애 |
| Authentication | 인증·세션 결과, 서비스 장애, 악용 증거 |
| HTTP access | 응답, 요청 실패, 의심 접근 |
| Application | 애플리케이션 작업, 예외, 의존 서비스 |
| Network / tcpdump text | 텍스트의 연결·패킷 증거; 바이너리 PCAP 미지원 |

프로필은 사이드바의 **Criteria**에서 추가·수정·삭제합니다.
결과 범주는 Normal·Warning·Error·Security·Other로 고정하며 `general`은 삭제할 수 없습니다.
**Save changes** 후 다음 분석부터 적용하고, 실행 중인 작업은 기존 기준을 유지합니다.
저장 위치와 삭제 후 소스 재선택은 [Criteria 관리](criteria.ko.md)를 참고하세요.
기준에는 사건의 결과와 증거를 설명하고 특정 로그 문자열은 검증 샘플에서 다룹니다.

서로 다른 파일의 이벤트는 섞지 않습니다. Batch는 EOF 잔여분을, Realtime은 설정한
이벤트 수가 차거나 새 이벤트가 1초 동안 없으면 제출하며 파일 회전 경계도 분리합니다.
빈 줄은 제외하고 이벤트 경계를 자동 인식하지는 않습니다. 겹치는 경로는 설정이
같으면 실제 경로 기준으로 중복 제거하고, 다르면 오류로 알립니다. 청크로 묶어도
모델 입력 예산은 그대로 적용됩니다.

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

최근 **판정 완료** 청크부터 페이지당 100건을 표시합니다. 로그 타임스탬프 순서가
아닌 완료 순서입니다. Batch의 **File line(s)**는 실제 파일 라인 번호이고,
Realtime의 **Observed line(s)**는 감시 시작 또는 파일 회전 이후 읽은 라인 순번입니다.
`1 event (max 5)`는 최대 5이벤트 설정에서 실제 1이벤트를 제출했다는 뜻입니다.
JSON의 `chunkEvents`는 설정값, `eventCount`는 실제 이벤트 수입니다.
`line`·`lineEnd`·`lineCount`는 줄 위치·수를 유지합니다. 기존 API 입력 `chunkLines`도
받지만 새 요청·결과에는 `chunkEvents`를 사용합니다.

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

**Needs review**는 판정에 성공한 청크 중 Uncertain 또는 Other인 결과입니다.
요청 실패·거절은 Failed에만 포함하고 검토 지표·필터에서는 제외합니다. Other라는 이유만으로 Uncertain이 되지는 않습니다.
**Certain**은 Uncertain 표시가 없다는 뜻이며 검증된 정확도를 뜻하지 않습니다.
임계값을 운영 정책으로 사용하기 전에 정답이 있는 로그로 오분류와 검토량을 평가하세요.

**All results / Needs review / No review needed**로 필터링합니다.
Needs review와 No review needed는 성공 판정만 표시합니다. 실패는 All results와
범주 필터 Request failed를 함께 선택해 확인하세요.
범주 필터와 원본 로그의 대소문자 구분 없는 문자열 검색을 함께 적용할 수 있습니다.
목록에만 적용하며 지표·차트·JSON 내보내기는 전체 결과 기준입니다.

**Source**는 Search logs 다음에서 입력한 경로·패턴별 결과를 필터링하고 실패를 포함한
처리 건수를 표시합니다. 중복 매칭은 JSON의 `sourcePatterns`에 모두 남기며 파일은
한 번만 처리합니다. 필터는 목록에만 적용하고 지표·차트·내보내기에는 영향을 주지 않습니다.

| 조작 | 동작 |
| --- | --- |
| Pause updates / Resume updates | 첫 결과 전부터 목록을 고정·재개합니다. 분석·지표·차트는 계속 갱신합니다. 필터·페이지 이동은 고정된 목록에 적용하고 버튼에 새 결과 수를 표시합니다. |
| Stop | 파일 읽기·진행 중 요청을 취소하고 완료 결과는 보존합니다. 미제출 청크는 버리며 원격지의 추론은 완료될 수 있습니다. |
| View JSON | 실패 정보, 프로필·청크 정보, 수동 리뷰 값을 포함한 개별 JSON을 펼칩니다. 목록 갱신에도 펼친 상태를 유지합니다. JSON 영역 안의 Copy는 수동 리뷰 값을 포함한 현재 항목을 클립보드에 복사합니다. |
| Reviewer category | `reviewerCategory`를 기록합니다. AI 범주·검토 상태·차트를 바꾸거나 모델을 학습시키지 않습니다. |
| Export JSON | 처리 완료 또는 중단 후 수신한 모든 결과를 내보냅니다. Pause 중 화면에 반영되지 않은 결과도 포함합니다. |

**Classification overview**는 불확실한 선택을 포함해 전체 소스의 AI 분류 개수를
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

사이드바는 Main `/`, Criteria `/#criteria`, Actions `/#actions`를 사용합니다.
새로고침하면 URL에 해당하는 화면을 열며 브라우저 뒤로가기·앞으로가기도 지원합니다.
저장하지 않은 편집 초안은 새로고침 시 보존하지 않습니다.

UI의 Batch·Realtime·Paste 작업은 새로고침하거나 연결이 끊겨도 **서버 메모리**에서
계속 실행합니다. 브라우저 탭별 session storage에 최근 작업 ID를 보관합니다.
같은 탭을 새로고침하면 소스 설정과 완료 결과를 복원하고 새 결과를 이어 받습니다.
판정이나 Action을 다시 실행하지 않습니다. 같은 서버 프로세스가 실행 중이면
완료·중지된 작업도 복원됩니다. **Stop**은 서버 작업을 명시적으로 취소하고 완료
결과를 유지합니다. 연결 오류 후 **Reconnect**는 새 작업 대신 같은 작업에
재접속합니다. 탭을 닫아도 작업은 중지되지 않으므로 계속 실행할 필요가 없다면
먼저 Stop을 누르세요. 닫힌 탭을 다시 여는 방식의 복구는 지원하지 않습니다.

DB나 디스크 이력은 사용하지 않습니다. 서버·컨테이너 재시작 시 모든 작업이
사라지며 UI에 이전 작업이 없다는 안내를 표시합니다. 서버 worker는 하나를
사용합니다. 모든 작업의 결과를 서버 종료까지 RAM에 보관하므로 큰 Batch나
장시간 Realtime은 메모리 사용량을 늘립니다. 시간 갱신 이벤트는 최신 값만 유지합니다.
수동 정정·필터·페이지 위치·저장하지 않은 코드 초안은 브라우저에만 남아 복원되지
않습니다. 서버 재시작 이후에도 결과를 보존하려면 내보내세요. 작업 이력 조회 화면과
JSON 가져오기는 제공하지 않습니다.

API에서 `/api/classify` 또는 `/api/file-source`에 `persist: true`를 보내면
HTTP 202로 `jobId`·`state`·검증된 `settings`를 받습니다.
`/api/jobs/<jobId>`에 POST하면 작업 정보, `/api/jobs/<jobId>/events`는 기존 결과와
새 결과의 NDJSON 스트림, `/api/jobs/<jobId>/stop`은 중지를 제공합니다.
분석과 동일한 출처 검사를 적용하고 파일 작업은 로컬·신뢰 UI 출처도 확인합니다.
`persist: true`가 없으면 기존 API의 연결 단위 스트리밍 동작을 유지합니다.

### 시간 지표

| 지표 | 의미 |
| --- | --- |
| Success / Failed / Total | 유효한 판정 성공 청크 / 실패 청크 / 처리 완료 전체 청크(성공 + 실패). 연결 오류·시간 초과·입력 거절·응답 검증 실패를 실패에 포함 |
| Action Success / Failed / Total | 완료된 Action 성공 / 실패 / 전체 실행 수. Action 미할당·의사결정 실패 청크는 제외하며 의사결정 집계와 독립 |
| Needs review | 성공 판정 중 Uncertain(낮은 확률·근접한 확률·선택지 구분 소실) 또는 Other. 실패·거절은 제외 |
| Throughput | 최근 5초의 성공 판정 청크/초; 유휴시간 포함, 시작 후 5초 미만은 경과시간 기준; 중지·완료 시 마지막 값 유지 |
| Total elapsed time | 실행 시작 이후 전체 경과시간; 유휴시간 포함 |
| Active processing time | 요청이 하나 이상 진행 중인 구간을 중복 없이 합산; 전체 경과시간 대비 비율 |
| Average processing time | 실패를 포함한 완료 요청의 평균 소요시간; 청크 기준 |

Total elapsed time·Active processing time·Average processing time은 값에 따라
ms·sec·min·hour·day로 표시합니다. JSON 시간값은 밀리초를 유지합니다.

Action 실행 실패는 판정 성공·실패 집계나 엔진 연결 상태에 영향을 주지 않습니다.

Active·Average에는 네트워크·서버 대기가 포함됩니다. Active는 유휴시간을 제외하며
전체 경과시간 대비 0~100%입니다. CPU·GPU 가동률이나 순수 추론시간이 아닙니다.
대기 중 시간 정보는 1초마다 갱신합니다. 연결이 끊기면 브라우저 표시만 멈추며
재접속 시 서버 진행 상태를 복원합니다. 중지 시 마지막 값을 보존하므로
약 1초의 차이가 있을 수 있습니다.

