<p align="center">
  <img src="images/DeciFlow-Logo.png" alt="DeciFlow" width="480">
</p>

# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**다양한 데이터를 AI로 빠르게 판단하고 결과에 따른 후속 처리까지 자유롭게 자동화하세요.**

## 아키텍처

[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/call518/DeciFlow)

![DeciFlow architecture](images/DeciFlow-Architecture.png)

DeciFlow는 TEXT 로그 청크 또는 JSONL 개별 레코드의 본문을 읽어 Laya나 Jev에
전달합니다. Criteria 프로필에서 `choice`·`score`·`noul` 판단 항목을 정의하며,
항목 수와 조합을 설정해 한 요청으로 판단합니다. 기존 시스템 프로필은
**Normal, Warning, Error, Security, Other**·긴급도·작업 티켓 필요 확률을
유지합니다. 상담 프로필은 문의 유형·처리 상태·후속 처리 주체·긴급도·후속 조치
필요성을 판단할 수 있습니다.

결과에는 프로필의 모든 판단 항목을 설정된 순서대로 표시합니다. **Result #**는
입력 순서와 무관한 실행 내 처리 완료 순번이며 필터나 페이지를 변경해도 유지됩니다.
필터 없는 최신 결과의 번호는 전체 완료 건수와 같습니다.
**Probabilities and Criteria**로 항목별 확률과 기준을 펼칩니다.
**Review**에서 AI 예측을 유지한 채 타입별 검토자 수정값을 기록합니다.
점수는 반올림한 등급이 아닌 확률 가중 값이며, 티켓을 자동 생성하지는 않습니다.

토큰 한도 초과·Criteria 축약 경고는 해당 결과에 표시합니다. 감지 범위는
[토큰 경고](docs/usage.ko.md#토큰-경고)를 참고하세요. Criteria 축약 메타데이터는 로컬 어댑터가
제공하며 외부 서버는 생략할 수 있습니다. 현재 제공자 계약에는 별도의 출력 잘림 신호가 없습니다.

**Processing Time** 박스에 Avg·Min·Max·P(50)·P(95)·P(99)를 함께 표시합니다. Throughput은 전체
경과시간당 성공 건수입니다. 모두 선택한 실행 전체 기준이며 필터·페이지 이동으로
집계 범위가 바뀌지 않습니다.

**DeciFlow**는 로그가 있는 노드에서 실행해 이벤트를 읽고 브라우저에 결과를 표시합니다.
**Laya 서버**는 같은 호스트 또는 별도 호스트에서 판정 모델을 실행하며, **Jev 서비스**는 대신 선택할 수
있는 외부 판정 API입니다. DeciFlow는 선택한 엔진에 이벤트를 보내고 판정 결과를 받습니다.

- **로그가 있는 곳에서 바로 시작합니다.** 로컬·SSH 원격 파일을 Sources에
  등록해 선택합니다. 와일드카드 패턴도 지원합니다.
- **일회성 분석과 실시간 감시를 함께 제공합니다.** Batch로 기존 로그를 읽거나
  Realtime으로 새 줄과 파일 회전을 감시합니다. 최근 판정 완료 결과부터 표시합니다.
- **최종 검토는 사람이 합니다.** 불확실한 판정을 필터링하고 검토자 수정값을 기록해
  JSON으로 내보내세요. 거절된 이벤트도 원문을 검토 대상으로 보존합니다.
- **여러 노드가 추론 서버를 공유합니다.** 각 로그 노드에서 DeciFlow를 실행하고
  공유 Laya 서버에 연결합니다. DeciFlow 실행 노드에는 GPU·PyTorch가 필요하지 않습니다.
- **엔진을 선택합니다.** 기본 Laya를 자체 운영하면 Jev API 호출료가 없습니다.
  `.env`에서 Jev로 전환해도 사용 흐름은 같으며 유료 엔진으로 자동 전환하지 않습니다.

access 로그, 애플리케이션 오류, 운영 이벤트에 활용하세요.
기존 로그 파일 하나로 시작해 브라우저에서 판정 결과를 검토할 수 있습니다.

결과 JSON은 원문을 한 번 보존하고 SQLite는 반복 Criteria 정의를 실행별로 공유 저장합니다. 사용자 Action은 [간결한 v2 계약](docs/actions.ko.md#간결한-결과-json-계약-버전-2)을 참고하세요.

메뉴·항목 상세/편집·Task History·실행 결과는 [공유 가능한 일반 URL](docs/usage.ko.md#공유-가능한-url)을 제공하며 결과 필터·커서 페이지도 유지합니다. 기존 해시 링크도 지원합니다.

## 빠른 시작 — Docker + Laya CPU

**전제:** 같은 Linux 호스트에 Git과 Docker(Compose 플러그인 포함)가 준비되어 있어야 합니다.
호환 NVIDIA GPU가 있으면 [GPU로 실행하기(CUDA)](#laya-gpu)를 참고해
Laya의 추론 성능을 높일 수 있습니다. 이 빠른 시작은
다양한 환경에서 DeciFlow를 테스트할 수 있도록 CPU 기준으로 안내합니다.
Laya는 판정 엔진 컨테이너, DeciFlow는 로그 분석·웹 UI 컨테이너입니다.

### 1. 저장소 준비

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
# 기존 .env가 없다면 / Only if .env does not exist
test -f .env || cp .env.example .env
```

### 2. CPU 실행 설정

`.env`에서 아래 값을 설정합니다. `laya` 호스트 이름은 CPU·CUDA 모두 Compose
네트워크 안에서 사용할 수 있습니다. 기존 API 키는 유지하세요. Compose가 두 컨테이너에
같은 키를 전달합니다.

```dotenv
COMPOSE_PROFILES=cpu
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya:8000/v1/systemone
PORT=4000
```

### 3. 컨테이너 실행

```bash
docker compose up -d
docker compose logs --follow laya-cpu
```

최초 모델 다운로드·로딩이 끝나면 로그 보기만 `Ctrl+C`로 종료합니다.
[준비 상태 확인](#laya-health) 후 다음 단계로 진행하세요.

### 4. 샘플 로그 분석

같은 호스트에서 **http://127.0.0.1:4000**을 엽니다. **Sources**에서
**Sample HTTP access** 경로를 `/host-logs/sample-logs/access-100.log`로 수정하고 저장합니다.
**Tasks**에서 이름을 지정한 **Batch / Manual** Task를 추가하고
**Sample HTTP access**, **Sample HTTP access** 기준, **Events/Chunk: 1**,
**Action: None**을 선택해 저장합니다. Tasks에서 **Run**을 누르면 Main으로 자동 이동해 결과를 표시합니다. Tasks의 **Pause / Resume**으로 같은 실행을 잠시 멈췄다가 이어갈 수 있습니다. 새 실행은 서버 재시작 후에도 복구하며 일시정지 상태도 유지합니다. [복구 제한](docs/tasks.ko.md#서버-재시작-후-복구)을 확인하세요.

선택 사항인 GPU 가속은 [Docker 배포 상세](#laya-docker),
유료 API를 사용하려면 [Jev](#jev)를 참고하세요.
기본 키 `changeme`는 체험용입니다. 운영 전 `.env`의 키를 변경하세요.

기본 **Sample DeciFlow Server Log** Task는 `DECIFLOW_LOG_DIR/server.log` / `DECIFLOW_LOG_DIR/access.log`를 감시하며 기본 Disable 상태입니다(Run 전에 Enable로 전환). Reset 후를 포함한 서버 시작 시 누락된 기본 설정을 복구합니다. [Tasks](docs/tasks.ko.md)를 참고하세요.

Classification Results의 **Export Reviewed JSON**으로 선택한 실행에서 사람의
Choice·Score·Noul 중 하나라도 사람이 정정한 결과만 내려받을 수 있습니다.

## 고객 상담 분석

로그 예시 대신 아래 흐름을 선택할 수 있으며 두 방식 모두 지원합니다.

1. **Sources**에서 읽을 수 있는 파일을 등록하고 **JSONL (Line)**과 **Content Field**를
   지정합니다. 제공된 두 샘플은 모두 `consulting_content`를 사용합니다. 호스트
   샘플과 Compose 마운트를 사용하면
   `/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl` 또는
   `/host-logs/sample-logs/voc-central-gov-consulting-qna.jsonl`을 지정합니다.
   상담 파일용 **Sample VOC Asia Culture Center Consulting QnA** Source는 시작 시 자동 제공됩니다.
2. **Criteria**에서 **Sample VOC Asia Culture Center Consulting QnA**를 사용하거나 Clone하여 수정합니다.
   샘플이 없으면 시작 시 자동 추가됩니다. 질문만 있는 자료에는
   문의 분류용 프로필을 사용하세요. 후속 처리 판단에는 대화 내용이 필요합니다.
3. 기본 **Sample VOC Asia Culture Center Consulting QnA** Batch Task를 활성화한 뒤 Run합니다.
   또는 원하는 Source와 Criteria, Action None으로 별도 Task를 만듭니다.
   JSONL은 한 줄의 객체를 한 건씩 처리하며 동일한 대화도 별도 레코드로 유지합니다.
   제공된 상담 파일은 입력 841건입니다.
4. **Main**에서 Task를 선택해 결과를 확인하고 수정합니다. 서로 다른 분류 체계는
   차트의 **Criteria**에서 별도로 선택합니다.

Overview의 **Decision**에서 `summary` 설정과 관계없이 모든 판단 항목을 집계할 수 있습니다.
Default Chart Decision은 모든 유형 중 하나를 지정하며 AI 답변·필터를 바꾸지 않고 변경합니다. Choice는 선택지별,
Score는 가중 점수를 가장 가까운 수준으로 반올림하여, Noul은 Yes 확률을 25% 구간으로
집계합니다. 확실성 그룹은 선택한 Choice 기준이며 Score·Noul에는 적용하지 않습니다.
Decision 필터는 전체 실행을 검색하며 어느 판단 항목이든 문제가 있으면 Needs Review가 됩니다. 차트 전환은 재분석하지 않습니다.

Content Field는 비어 있지 않은 문자열을 담은 최상위 필드의 정확한 이름입니다.
잘못된 JSONL 레코드는 실패로 보존하고 이후 레코드를 계속 처리합니다. 파일은 DeciFlow
컨테이너 안에서 접근 가능해야 하며 이 흐름은 파일 업로드 기능이 아닙니다.
기존 Source는 **TEXT (Chunk)**로 처리합니다. 설정과 제한은
[Sources](docs/sources.ko.md)·[Criteria](docs/criteria.ko.md)를 참고하세요.

[VOC 실습 가이드·전체 샘플 입력값](docs/voc.ko.md)과
[Criteria 필드별 작성 가이드](docs/criteria.ko.md)를 참고하여 수정하세요.

Add Profile의 **Generate With AI**로 Criteria 전체 초안을 작성할 수도 있습니다.
DeciFlow의 `.env`에 `OPENAI_API_KEY`와 `OPENAI_CRITERIA_MODEL`(기본 `gpt-5.6-terra`)을
설정하고 DeciFlow를 재시작하세요. Source(원격 파일은 SSH Host 하나 포함)를 선택하고
샘플을 확인·수정하세요. Sample Count는 10개(기본값)·20개·30개·50개·100개 중 선택합니다.
전체 Source를 훑어 완전한 샘플을 무작위로 추출하며, 빈 입력과 개별 용량 초과 입력은
제외합니다. 총 150,000 UTF-8 바이트 제한과 Source 크기에 따라 실제 개수는 적을 수
있습니다. 전체 읽기가 20초를 넘으면 일부 샘플을 반환하지 않고 시간 초과로 처리합니다.
다시 미리보기 하면 새로 무작위 추출합니다. 샘플이 많을수록 토큰 소비와 API 비용이 늘어날 수 있으며,
생성할 때 남아 있는 수정된 샘플만 전달합니다. Analysis Purpose Mode의 기본값은
Automatic (ChatGPT)이며 목적을 직접 지정하려면 Manual을 선택합니다.
저장 전에 제안한 목적과 생성된 Criteria를 확인하세요.
Events Per Sample은 미리보기 샘플 하나에 묶을 TEXT 이벤트 수입니다.
JSONL은 입력칸 대신 레코드 하나가 샘플 하나라는 안내를 표시합니다. 목적 작성 안내에서 판단 항목, 판단 시점, 규칙과 예시를 확인할 수 있습니다.
수정한 샘플, 목적, 작성 규칙이 OpenAI에 전송되며 API 요금이 발생합니다.
검증된 전체 초안을 검토하고 **Save Changes**로 저장하세요.
실제 분류는 계속 Laya 또는 Jev가 수행하며 Task에 자동 할당하지 않습니다.
[AI Criteria 생성](docs/criteria.ko.md#ai로-criteria-생성)을 참고하세요.

### 정부기관 QnA 샘플

**Sample VOC Central Gov Consulting QnA**는 기존 설치를 포함해 시작 시 자동 추가됩니다.
Source는 `/host-logs/sample-logs/voc-central-gov-consulting-qna.jsonl`,
JSONL (Line), Content Field `consulting_content`를 사용합니다(3,965건).
**Sample VOC Central Gov Consulting QnA** Criteria는 행정·정책 분야,
답변 유형, 후속 처리 주체, 긴급도, 기관 후속 처리 필요성을 판단합니다.
법령 설명·신청 안내·관할 기관 문의 안내·개별 처리 완료·기관의 명시적 미완료 조치를
구분합니다. 문의 안내나 말미 연락처만으로 기관의 후속 처리 의무를 추정하지 않으며
법령의 현행성을 검증하지 않습니다.
기본 **Sample VOC Central Gov Consulting QnA** Task는 한국어 Criteria,
Batch / Manual, Events/Chunk 1, Action None으로 연결되며 Enable과 Resume on Restart는
꺼져 있습니다. 활성화 후 Run으로 실행하세요. 저장된 사용자 수정은 유지합니다.

### 지방자치단체 QnA 샘플

**Sample VOC Local Gov Consulting QnA** Source, Criteria, Task는 기존 설치에도 시작 시
자동 추가되며 저장된 사용자 수정은 유지합니다. Source는
`/host-logs/sample-logs/voc-local-gov-consulting-qna.jsonl`(3,280건)을
JSONL (Line), Content Field `상담내용`으로 읽습니다. 이 필드만 분류에 전달하고
`지방자치단체명`과 `상담담당부서`는 빈 부서명을 포함해 원본 메타데이터로 보존합니다.
한국어 Criteria는 지방행정 분야, 답변 유형, 후속 조치 담당, 긴급도, 후속 조치 필요성을
판단합니다. 일반적인 사업 일정이나 개선 계획만으로 개별 민원의 미완료 약속으로
판단하지 않습니다. Task는 Batch / Manual, Events/Chunk 1, Action None이며
Enabled와 Resume on Restart는 꺼져 있습니다. Reset 없이 DeciFlow-UI를 재시작하고
Task를 활성화한 뒤 Run으로 실행하세요. 네이티브 실행 시 Source 경로를 실제 로컬
샘플 파일 경로로 변경하세요.

모든 기본 VOC Criteria는 한국어만 제공하며 이름에 언어 접미사를 붙이지 않습니다.
시작 시 이전 기본 영문 Criteria를 제거하고 해당 Task 할당을 한국어 버전으로 연결합니다.
사용자가 복제한 영문 Criteria와 과거 결과는 유지합니다. 기존 Source 경로와 사용자 수정도
보존하므로 이전 샘플 경로는 Sources에서 직접 변경하세요.

기본 Source·Criteria·Task·Action 이름은 **Sample**로 시작합니다.
기존 기본 이름도 ID와 할당을 유지한 채 변경하며 사용자 지정 이름과 설정은 보존합니다.
Reset 후에도 같은 샘플 이름으로 다시 생성됩니다.

Task History와 다시 연 결과에는 실행 시작 당시 저장된 엔진과 요청 모델을 표시합니다.
과거 정보가 없으면 **Not Recorded**로 표시하며 현재 서버 설정으로 대체하지 않습니다.

Classification Results 우측 아래의 **▲ / ▼** 플로팅 버튼으로 결과 영역의
최상단·최하단으로 이동합니다. 결과 페이지를 바꾸거나 분석을 실행하지 않습니다.

결과별 Action·Source/Host·Criteria/Chunk 정보는 **Details**에 접어 표시하고,
Action 실패는 카드에 바로 표시합니다. 전체 정보는 **View Result JSON**에도 보존합니다.

모든 결과에 **Review**와 같은 접기·펼치기 형식의 **Response**를 제공합니다.
응답 본문은 읽기 전용 패널로 표시하며 Copy로 복사할 수 있습니다.
Laya·Jev의 응답과 구체적인 형식 검증 사유를 확인할 수 있으며 JSON이 아닌 오류 본문도
보존합니다. 본문이 저장되지 않은 과거 기록과 응답을 받지 못한 요청은 따로 안내합니다.

## 사용법과 설정

전체 사용·설정 문서, 배포 참고 자료, 요청·결과 예시는
[문서 안내](docs/README.ko.md)에서 찾아보세요.

| 문서 | 내용 |
| --- | --- |
| [Tasks](docs/tasks.ko.md) | 재사용 실행 설정·Cron 예약·연속 감시·영속 실행 이력 |
| [결과 저장](docs/result-storage.ko.md) | SQLite·페이지 조회·설정·결과 통합 저장·백업·DB 확장 |
| [Sources](docs/sources.ko.md) | 로컬·SSH 파일 소스 등록, Settings의 SSH 키 관리, 정렬된 풀다운 선택 |
| [사용법](docs/usage.ko.md) | 입력 모드·판정 기준·필터·수동 검토·재접속·시간 지표 |
| [설정](docs/configuration.ko.md) | 환경변수·모델·입력 예산 |
| [Criteria](docs/criteria.ko.md) | 내부 UUID 기반 타입별 판단 프로필을 한 목록에서 관리하고 선택적으로 AI 생성 |
| [Python Actions](docs/actions.ko.md) | 구성 보기·환경 Status·pip 포함 환경·Reset venv·삭제·소스 할당 |
| [결과 JSON](docs/results.ko.md) | 현재 요청·결과 예시와 필드 설명 |

준비 흐름은 Sources → Criteria → 선택적 Actions → Tasks이며 Main에서 실행 결과를 확인합니다.
Source에는 경로·패턴을 한 줄에 하나씩 여러 개 등록할 수 있습니다. 원격 Source는 재사용할 경로를 정의하고 Task에서 Source별 SSH Host를 하나 이상
선택합니다. 호스트별로 독립 수집하고 판정 차례를 공정하게 배분하며, 실행별 통합
결과에 Host 필터·호스트 수집 상태를 제공합니다.

Sources·Criteria·Actions·Tasks 목록은 이름의 ABC/가나다 순으로 정렬합니다.
모든 Criteria는 동일한 View·Edit·Clone·Delete 기능을 제공합니다. Source는 타입·형식 배지와 줄별 경로로 표시합니다. 모든 Task의 결과 카드는
공통 테두리와 굵은 구분선을 사용합니다. 작은 필터 컨트롤에서 종류와 값을 선택하며 조건은
함께 적용되고 종류를 전환해도 유지합니다. 개별 조건이나 **Clear All**로 해제할 수 있습니다.
**Results per Page**는 기본 30건이며 10/30/50/100건을 선택합니다. 기존 저장값은 유지합니다.

브라우저는 새 결과만 집계하고 기존 카드를 재사용합니다. Main이나 탭이 숨겨지면
그리기를 미루며 Task는 계속 실행하고 전체 결과는 유지합니다.

Main 아래에 Source·Criteria·Actions·Tasks, Settings 아래에 SSH Keys·SSH Hosts·Configurations(엔진·모델·예산·동시 요청 수, AI 작성 모델, 페이지 크기 및 유지 관리)를
배치합니다. 사이드바로 재진입하면 목록을 열고 미저장 초안은 버립니다.
화면 경로·결과 조작·재접속은 [사용법](docs/usage.ko.md)을 참고하세요.
설정과 실행 결과는 `DECIFLOW_DATA_DIR/deciflow.sqlite3`에서 통합 관리하며 SSH 키·known_hosts·Action 실행 파일은 파일로 유지합니다. 테스트 단계의 저장 구조 변경으로 이전 JSON·DB를 이관하지 않습니다. 사용 전 앱 데이터를 초기화하세요.

최초 초기화·Reset 후 **Sample Elasticsearch** 샘플 Action(Python 3.12, 모듈 `elasticsearch`)을 자동 등록합니다. Task 시작 전에 스크립트·venv·Python·모듈을 자동 준비합니다(다운로드 연결 필요). 실패 원인은 Actions에 표시되며 저장 또는 재시작으로 재시도합니다. Task에는 자동 할당하지 않습니다.

Action 실행 파일은 `actions/<Action UUID>/`에 저장하며 이름 변경으로 venv가 추가 생성되지 않습니다. Action·SSH Key 이름을 수정할 수 있습니다. Task의 Action 선택과 SSH Host의 키 선택은 UUID를 사용하므로 이름을 바꿔도 할당·키 파일·Action 실행 환경은 유지됩니다.

**Settings → Configurations**에서 비밀값 없는 운영 설정을 서버 재시작 없이 저장할 수 있습니다. 새 실행부터 적용하고 실행 중이거나 복구한 작업은 원래 설정을 유지합니다. UI 저장값은 `.env`보다 우선하며 Use UI Override를 해제하면 환경 설정으로 복원합니다. API 키와 배포 설정은 `.env`에 남습니다. [설정 안내](docs/configuration.ko.md)를 참고하세요.
Reset 아래의 **Restart DeciFlow**는 데이터를 보존하고 작업을 일시 중단·복구하면서 UI 프로세스만 교체합니다. Docker·Laya 배포 변경은 별도 재시작/재생성이 필요합니다.

**Settings → Configurations → Reset DeciFlow**는 명시적 확인 후 앱 데이터를 영구
삭제하고 UI 서버를 재시작합니다. 먼저 백업하고 [초기화 범위와 동작](docs/configuration.ko.md#deciflow-초기화)을 확인하세요.

Settings는 개인키를 **Upload·Path·Paste**로 받아 관리 경로에 복사하고 공개키를
추출합니다. SSH Hosts에는 접속 정보와 키를 저장합니다. **Test Connection**은 SSH
인증·SFTP를 확인하며, 호스트 목록 진입 시 순서대로 한 번 자동 확인합니다.
View·목록 재출력으로 반복 확인하지 않습니다. 미등록 fingerprint는 사이트 확인창에서 승인합니다. 승인 키는 사용자
SSH와 별개인 `DECIFLOW_DATA_DIR/ssh-hosts/known_hosts`에만 보존합니다.
설정·신뢰 관리는 [Sources와 SSH 설정](docs/sources.ko.md)을 참고하세요.

- **Tasks:** Source·Criteria·청크·Action 설정을 저장합니다. Batch는 수동·Cron, Realtime은 연속 실행합니다. Disable은 현재 실행과 이후 시작을 막습니다. Main은 실행 중인 Task를 우선 표시하고 Source 요약·전체 설정 말풍선을 제공합니다. [Tasks](docs/tasks.ko.md)를 참고하세요.
- **Batch:** 등록한 로컬·SSH 파일을 분석합니다. Docker에서 호스트 `/var/log`는 `/host-logs/var/log`입니다.
- **Realtime:** 새 로그를 감시합니다. 소스별 판정 기준과 청크 크기를 선택합니다.
- **처리 지표:** Success / Failed / Total로 성공·실패·처리 완료 전체 청크를 표시합니다. Action Success / Failed / Total은 후속 작업을 별도 집계합니다. Needs Review는 성공 판정만 집계합니다.
  페이지 로드 시 HTTP 점검에서 엔진이 응답하면 Reachable을 표시합니다. 이후 새 분류 요청 결과에 따라 Operational 또는 오류 상태로 갱신하며, 과거 결과 조회는 상태를 바꾸지 않습니다.
- **검토:** Needs Review로 결과를 추리고 수동 정정을 기록합니다. **Export All JSON**은 선택한 실행 전체, **Export Reviewed JSON**은 Choice·Score·Noul 중 하나라도 사람이 정정한 결과만 내보냅니다.
  Certain은 정확도 보장이 아닙니다. Task 정의·실행 이력은 데이터 볼륨에 보존하며 수동 정정은 SQLite에 보존합니다.

## Docker 배포 상세

<a id="laya-docker"></a>

### Laya 엔진 사용

기존 공용 Laya 서버에 연결하거나 아래 절차로 원격 노드에 서버를 구성하세요.
이미 서버가 있다면 구성 절차를 건너뛰고 DeciFlow 연결 설정만 적용합니다.

Laya 호스트의 복제한 저장소에서 [docker-compose.yml](docker-compose.yml)을 사용합니다.
`.env.example`의 기본값은 CPU이며, 호환 NVIDIA GPU가 있으면 추론 성능을 높일 수 있습니다.
실제 성능은 하드웨어와 작업량에 따라 달라집니다.

#### CPU 실행

`.env`에서 `COMPOSE_PROFILES=cpu`를 설정한 뒤 실행하세요:

```bash
docker compose up -d laya-cpu
```

Laya와 DeciFlow를 함께 실행하려면 대신 `docker compose up -d`를 사용합니다.
두 Laya 방식 모두 호스트 포트 **8000**, `deciflow-laya-model-cache` 공유 볼륨,
`english`·`multilingual`·`typed-decisions` 사전 적재를 사용합니다.
프로필은 하나만 선택하세요. 이 구성에서 CPU·CUDA를 동시에 실행할 수 없습니다.
`.env`의 `LAYA_API_KEY`를 Laya와 DeciFlow가 함께 사용하며, 빈 키는 인증을 비활성화합니다.

<a id="laya-gpu"></a>

#### 선택 사항: GPU 가속(CUDA)

CUDA 실행에는 호환 NVIDIA GPU·드라이버와
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)이 필요합니다.
`nvidia-smi`로 GPU·드라이버를 확인하세요. `CUDA Version`은 드라이버의 지원 버전이며
설치된 Toolkit 버전이 아닙니다. 이 컨테이너에는 로컬 CUDA Toolkit이 필요하지 않습니다.
CUDA 13.0 이미지에는 [580 이상 드라이버](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)가 필요합니다.
CUDA 서비스는 모든 GPU를 사용하도록 요청하며 CPU 서비스는 GPU를 요청하지 않습니다.

기존 배포를 전환하려면 필요한 결과를 내보낸 뒤 **프로필을 수정하기 전에** 현재 구성을 종료하세요:

```bash
docker compose down
```

`.env`에서 `COMPOSE_PROFILES=cuda`로 변경하고 실행하세요:

```bash
docker compose up -d
docker compose logs --follow laya-cuda
```

CPU로 돌아가려면 같은 절차에서 `COMPOSE_PROFILES=cpu`를 사용합니다.
내부 URL `http://laya:8000/v1/systemone`은 그대로 유지합니다.

<a id="laya-health"></a>

#### 상태 확인과 관리

아래 명령은 선택한 컨테이너 안에서 서버 키를 출력 없이 읽어 상태를 확인합니다.
CUDA를 사용하면 `laya-cpu`를 `laya-cuda`로 바꾸세요:

```bash
docker compose exec laya-cpu python -c 'import os, urllib.request; r = urllib.request.Request("http://127.0.0.1:8000/health", headers={"Authorization": "Bearer " + os.environ["LAYA_API_KEY"]}); print(urllib.request.urlopen(r).read().decode())'
```

CUDA 사용 시 `checkpoint_devices`·`device`와 `cpu_fallbacks`로 실제 GPU 사용을 확인합니다.
신뢰할 수 있는 DeciFlow 노드만 Laya에 접근하도록 제한하고 외부 네트워크에는 TLS를 사용하세요.
잘림 메타데이터를 위해 `LAYA_JEV_STRICT=0`을 유지합니다. 최초 모델 적재에는 수 분이
걸릴 수 있으며 시작 오류는 컨테이너 로그에서 확인하세요.

| 작업 | 명령 |
| --- | --- |
| 상태 | `docker compose ps` |
| 로그 | `docker compose logs --tail=100` |
| 중지 | `docker compose stop` |
| 재개 | `docker compose start` |
| 컨테이너 제거 | `docker compose down` |

`down`은 이름 있는 볼륨을 유지합니다. 데이터를 보존하려면 `--volumes`를 추가하지 마세요.
네이티브 실행과 Docker 중 하나를 선택하세요.

#### DeciFlow 연결 설정

같은 Compose 구성에서는 `LAYA_API_URL=http://laya:8000/v1/systemone`을 사용합니다.
외부 Laya 서버에 연결하려면 `.env`에 접근 가능한 URL과 서버와 동일한 API 키를 설정하세요:

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

`docker compose up -d ui`로 UI만 실행하면 로컬 Laya는 시작하지 않습니다.
Laya 호스트에서 DeciFlow를 네이티브로 실행하면 대신 `http://127.0.0.1:8000/v1/systemone`을 사용하세요.

<a id="jev"></a>

### Jev 엔진 사용

[Jev 설정 안내](https://docs.typesafe.ai/introduction/quickstart)에서 TypeSafe API 키를
발급받아 `.env`에 설정하세요. Jev는 유료이며 Laya 서버는 필요하지 않습니다.

```dotenv
DECISION_ENGINE=jev
JEV_MODEL=jev-1.13.0
JEV_API_KEY=your-typesafe-api-key
PORT=4000
```

### DeciFlow Docker

부록의 **Python 직접 실행 대신 이 방식을 선택**합니다. DeciFlow 호스트에는
Compose가 포함된 Docker가 필요하며 로컬 Python·uv·CUDA는 필요하지 않습니다.
먼저 `.env`에 Laya 또는 Jev를 설정하세요. 외부 Laya 또는 Jev를 사용하면
`COMPOSE_PROFILES=`로 두고 UI만 실행합니다:

```bash
docker compose up -d ui
```

Compose는 Docker Hub에 공개된 `call518/deciflow-ui:0.0.1` 이미지를 사용합니다.
이미지는 Python·uv와 운영 유틸리티를 제공합니다. 저장소는 `/app`에 읽기 전용으로
마운트하며, 시작할 때 `uv sync --frozen`으로 `deciflow-venv` 볼륨에 의존성을 설치합니다.
최초 실행에는 네트워크 연결이 필요합니다. Compose가 `.env`를 UI에 전달하며
`PORT`로 호스트·컨테이너 포트를 함께 지정합니다(기본값: 4000).
`pull_policy: always`로 `up` 실행 시마다 이미지 업데이트를 확인합니다.
모든 Compose 서비스는 `extra_hosts`로 `host.docker.internal`을 Docker 호스트 게이트웨이에 연결합니다. 기존 컨테이너에는 재생성 후 적용됩니다.

#### Dockerfile과 Compose의 역할

[`Dockerfile`](Dockerfile)은 `python:3.12-slim`을 기반으로 uv `0.7.20`과 운영 도구를
설치하고 작업 디렉터리를 `/app`으로 지정합니다. 앱 소스나 프로젝트 의존성은 이미지에
미리 포함하지 않습니다. 시작 명령은 `uv sync --frozen --no-dev --no-install-project --no-cache`
이후 `server.main(host='0.0.0.0')`을 실행합니다. 따라서 공개된 UI 이미지에도 복제한
저장소를 `/app`에 마운트해야 합니다. 추론은 UI 이미지가 아닌 Laya 또는 Jev가 처리합니다.
SSH 키 관리와 원격 파일 요구사항은 [Sources](docs/sources.ko.md)를 참고하세요.

[`docker-compose.yml`](docker-compose.yml)은 실행 구성을 제공합니다:

| 항목 | 동작 |
| --- | --- |
| `name: deciflow` | 소문자 Compose 프로젝트·그룹 이름. 개별 컨테이너 이름은 DeciFlow 표기 유지. |
| `ui` | 항상 활성화. 공개 UI 이미지가 없으면 다운로드하고 .env·PORT·소스·로그·데이터 마운트를 적용. 빌드 단계 없음. |
| `laya-cpu` / `laya-cuda` | COMPOSE_PROFILES=cpu 또는 cuda로 선택. laya 네트워크 별칭·8000 포트 공유. CUDA만 GPU 요청. |
| `x-laya` | Laya 공통 설정을 재사용하는 YAML 앵커이며 별도 컨테이너가 아님. |
| 이름 있는 볼륨 | deciflow-venv·deciflow-data·deciflow-logs·deciflow-laya-model-cache의 기존 이름 유지. |

Compose는 `.env`를 변수 치환에 사용하고 `env_file`로 UI에 전달합니다.
Laya에는 명시한 서버 변수만 전달하며 `LAYA_API_KEY`는 같은 설정을 공유합니다.
변수 치환 시 프로세스 환경변수가 `.env`보다 우선합니다. `COMPOSE_PROFILES`는
`DECISION_ENGINE`과 독립적이므로 Jev·외부 Laya 사용 시 프로필을 비우거나 `ui`만
시작하세요. UI가 Laya 준비 전에 시작할 수 있으므로 로그 분석 전 준비 상태를
확인하세요. 유료 엔진으로 자동 전환하지 않습니다.

UI는 호스트의 모든 인터페이스에 공개합니다. 로컬 접속만 허용하려면 Compose의
UI 포트 매핑을 `127.0.0.1:${PORT:-4000}:${PORT:-4000}`으로 변경하세요.
기본 포트에서는 **http://127.0.0.1:4000**, 원격에서는 DeciFlow 호스트 IP로 접속합니다.
`deciflow-data` 볼륨은 `DECIFLOW_DATA_DIR`(기본값: `/var/lib/deciflow-data`)에
Sources·Tasks와 실행 이력·Actions·Criteria·SSH 키 쌍·SSH Host를 저장하고, `deciflow-logs`는 서버 로그를 저장합니다.
사용자 지정 데이터·로그 디렉터리는 컨테이너 안의 절대 경로로 설정하세요.

#### 호스트 로그 디렉터리 연결

호스트 `/var/log`와 저장소의 `sample-logs`를 `/host-logs/var/log`,
`/host-logs/sample-logs`에 읽기 전용으로 연결합니다. 다른 로그를 읽으려면
`docker-compose.yml`의 `services.ui.volumes`에 추가하세요:

```yaml
      - /your/logs:/host-logs/custom:ro
```

`docker compose up -d ui`로 마운트 변경을 적용합니다. UI 재생성은 진행 중 실행을
중단하며 Task 이력은 데이터 볼륨에 보존합니다. UI에서는 컨테이너 경로
`/host-logs/custom/app.log`를 사용합니다. 프로세스에는 호스트 파일을 읽을 권한이 필요합니다.

#### 연결 설정과 재시작

UI 저장값은 `.env`보다 우선합니다. 변경한 환경값을 사용하려면 해당 Use UI Override를 해제하세요.

Compose Laya 주소는 `http://laya:8000/v1/systemone`입니다. 외부 서버는 컨테이너에서
접근 가능한 주소를 사용하세요. `127.0.0.1`은 UI 컨테이너 자신입니다.
사이드바의 호스트·OS·IP 정보도 컨테이너를 나타냅니다.
`.env`의 엔진 설정(`DECISION_ENGINE`·`LAYA_*`·`JEV_*`)은 Docker Desktop에서
Configurations의 **Restart DeciFlow**, DeciFlow-UI Restart 또는 `docker compose restart ui`를 실행한 뒤 브라우저를
새로고침하면 적용됩니다. UI가 시작할 때 마운트된 파일의 엔진 설정을 다시 읽습니다.
포트·마운트·Compose 프로필·Laya 서비스 설정은 `docker compose up -d`로
해당 컨테이너를 재생성해야 합니다.
소스 변경은 `docker compose restart ui`로 적용하고 UI 변경 후 브라우저를 새로고침하세요.
Dockerfile을 수정한 경우에만 `docker build --tag call518/deciflow-ui:0.0.1 .`로
UI 이미지를 직접 빌드한 뒤 `docker compose up -d --force-recreate ui`로 적용합니다.
소스 버전 전환 전에는 DeciFlow를 중지하세요.

ngrok·리버스 프록시로 파일을 처리하려면 `DECIFLOW_CSRF_TRUSTED_ORIGINS`에
정확한 UI 출처(예: `https://your-domain.ngrok-free.app`) 또는 랜덤 ngrok 주소용 `https://*.ngrok-free.app`을 지정하고
`docker compose up -d ui`로 적용하세요(끝에 `/` 제외). 빈 값은 localhost 파일 접근만 허용합니다.
이 설정은 CSRF Origin 검사에 사용하며 CORS·로그인 인증·CSRF 토큰 검증은 아닙니다.
와일드카드는 다른 사용자의 하위 도메인도 신뢰하므로 공개 접속에는 프록시 인증을 적용하세요.

## 제약

- 앱의 파일 크기·줄 수 제한은 없습니다. 누적 결과는 SQLite에 저장하며 메모리는 활성 파일·호스트·개별 이벤트 크기에 영향을 받습니다. 디스크 자동 정리는 없습니다. [결과 저장](docs/result-storage.ko.md)을 참고하세요.
  파일은 점진적으로 읽습니다. 청크는 이벤트 수로 묶으며 현재 비어 있지 않은 한 줄이 1이벤트입니다.
  멀티라인 이벤트 경계는 자동 인식하지 않습니다.
- **Laya:** 선택한 체크포인트를 사용하며 요청 윈도·질문 예산은 [설정 상세](docs/configuration.ko.md)을 따릅니다.
  [공식 HTTP 서버](https://nandhakishorm.github.io/laya/http-api/#limits)는 state
  50,000자, 요청 2 MiB 제한도 적용합니다. 배포한 버전의 제한을 확인하세요.
  잘린 응답이나 잘림 메타데이터가 없는 응답은 거절합니다.
- **Jev:** `jev-1.13.0`, [state + 가장 긴 질문 32k, 전체 요청 64k 토큰](https://docs.typesafe.ai/models).
  바이트 예산은 보수적 검사이며 정확한 토큰 수나 수용 보장이 아닙니다.
- 거절 이벤트는 원문을 검토 대상으로 남기고 다른 이벤트는 계속 처리합니다.
  로컬 파일 읽기·UTF-8 오류는 실행을 중단합니다. SSH 읽기 실패는 Source/Host별로
  기록하고 다른 수집은 계속하며, 완료된 결과는 보존합니다.
- 청크마다 한 번 요청하며 엔진별 동시 요청 수는 실행당 기본 4개입니다.
  제한 시간은 Laya 120초, Jev 30초입니다. 동시 요청을 늘려도 병렬 추론이나 처리량
  증가를 보장하지 않으며 서버 처리 여력과 수용 제한이 적용됩니다.
- Realtime은 탐색 회차 종료 후 250ms 간격으로 확인하고 완성된 줄을 기다립니다.
  SSH 입력은 탐색 속성을 재사용하고 변경 없는 파일도 1초마다 교체 여부를 확인합니다.
  회전 시 남은 줄은
  `incomplete`로 표시하며 줄 번호를 초기화합니다. 빠른 회전이나 축소·재증가로
  누락될 수 있습니다. 파일 중복 제거는 내용 중복을 제거하지 않으므로 활성 로그와
  회전 복사본을 함께 매칭하지 않도록 주의하세요.
- Laya는 설정한 서버로, Jev는 TypeSafe로 로그를 전송하며 Jev API 비용이 발생합니다.
  Task 이력은 원본 로그·결과·Action 실행 결과를 데이터 볼륨에 저장합니다.
  볼륨과 백업의 접근 권한을 관리하고 전송 전 민감 정보를 제거하며 `.env`를 커밋하지 마세요. 공개 배포에는 인증과 사용량 제한이 필요합니다.

`Ctrl+C`로 종료하면 실행을 일시 중단하고 이력을 보존합니다. 재시작 시 체크포인트가 있는
Batch·Realtime 실행은 기존 ID로 복구하며 일시정지 상태도 유지합니다.
명시적으로 중지한 실행과 체크포인트가 없는 이전 실행은 자동 재시작하지 않습니다.
[복구 조건과 제한](docs/tasks.ko.md#서버-재시작-후-복구)을 확인하세요.

## Appendix — 추가 활용 가능성

로그 분석은 출발점입니다. 입력 처리와 판정 기준을 확장하면 `tcpdump` 기반 실시간
네트워크 트래픽 감시나 센서·검사 데이터를 활용한 제조 공정의 양품·불량 판정에도
같은 흐름을 적용할 수 있습니다. 이들 활용에는 추가 연동과 분야별 검증이 필요하며,
이미지 검사에는 비전 모델 연동도 필요합니다.

## Appendix — 호스트 직접 실행

Docker 실행 대신 선택합니다. DeciFlow 호스트에 Python 3.11+와 uv가 필요합니다.
Laya Docker 서버 또는 Jev 연결 설정은 동일하며, 별도 Laya 서버를 사용하면 DeciFlow에 GPU가 필요하지 않습니다.
저장소에서 `.env`를 준비하고 선택한 엔진을 설정한 뒤 실행하세요.

```bash
uv sync
uv run python server.py
```

네이티브 DeciFlow에서는 실행 전에 `.env`의 `LAYA_API_URL`을 접근 가능한 Laya 서버
주소로 설정하세요(같은 호스트: `http://127.0.0.1:8000/v1/systemone`).
Compose 전용 호스트 이름 `laya`는 Docker 네트워크 밖에서는 사용할 수 없습니다.

**http://127.0.0.1:4000**을 엽니다. 시작 시 `DECIFLOW_DATA_DIR/deciflow.sqlite3`에 설정과 기본 Criteria를
초기화하므로 데이터 디렉터리에 쓰기 권한이 필요합니다. 기본 `/var/lib/deciflow-data`에 쓸 수 없다면 `.env`에서
`DECIFLOW_DATA_DIR=./data`를 설정하세요. 설정 변경 후 DeciFlow를 재시작합니다.

## Appendix — Docker 커스텀 이미지(선택)

직접 만든 이미지가 필요한 경우에만 Laya **v0.4.1**에서 대상에 맞는
CPU **또는** CUDA 빌드 명령을 실행합니다:

```bash
git clone --branch v0.4.1 --depth 1 https://github.com/NandhaKishorM/laya.git
cd laya

docker build \
  --build-arg TORCH_INDEX=cpu \
  --tag my-laya:cpu .

docker build \
  --build-arg TORCH_INDEX=cu130 \
  --tag my-laya:cuda .
```

`docker-compose.yml`에서 선택한 Laya 서비스의 이미지를 커스텀 태그로 바꾸세요.
`cpu`는 CPU 전용 PyTorch, `cu130`은 CUDA **13.0**을 뜻합니다. GPU·드라이버와
Dockerfile의 `TORCH_VERSION`에 맞는 CUDA 빌드를
[PyTorch 설치 목록](https://pytorch.org/get-started/previous-versions/)에서 선택하세요.
Laya 업그레이드 시 API 호환성을 검증합니다.

## 개발

모델 평가 명령과 보고서 필드는 [Laya 로그 검증](docs/laya-validation.ko.md)을 확인하세요.
선택한 Laya 모델로 5개 프로필의 정답 사례 36개를 평가하려면:

```bash
uv run python -m scripts.evaluate_laya \
  --output /tmp/laya-validation.json
```

`scripts/evaluate_laya.py`는 선택적 평가 도구이며 UI·Compose 실행에는 필요하지 않습니다.
Laya 서버만 호출하고 유료 Jev는 거부합니다. 작은 표본이므로 정확도 보장이 아닙니다.

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

UI 회귀 테스트(Node.js는 테스트에만 필요):

```bash
node --test tests/test_ui.mjs
```

테스트는 유료 호출 없이 두 제공자, 입력 예산, 스트리밍, 취소, 파일 탐색·회전을
확인합니다. 두 README와 실제·예제 `.env`를 함께 관리하며 환경변수 주석은
영어와 한국어를 병기합니다.

선택적 로컬 Laya 개발 환경(`laya` 추가 의존성은 v0.4.1 지정):

```bash
uv sync --extra laya
uv run --extra laya python laya_server.py
```

DeciFlow의 `LAYA_API_URL`을 루프백으로 설정하고 다른 터미널에서 DeciFlow를 시작하세요.
이 로컬 어댑터는 추론 전에 설정된 토큰 예산을 초과한 이벤트를 거절하고
잘림 메타데이터를 제공합니다. 로컬 서버 옵션은 프로세스 환경변수로 지정합니다.
별도 Laya 서버를 사용하는 DeciFlow 실행 노드에는 `laya` 추가 의존성이 필요하지 않습니다.

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)

### DeciFlow HTTP 로그

`.env`에 `DECIFLOW_LOG_DIR=/var/log/deciflow`를 설정하고 DeciFlow를 재시작하면 시간 정보가 포함된
`server.log`(시작·서버 오류)와 `access.log`(클라이언트·요청·HTTP 상태)를 기록하며
콘솔 로그도 유지합니다. 기본값은 `/var/log/deciflow`이며, 없는 디렉터리는 상위
경로까지 자동 생성합니다. 생성·기록하려면 쓰기 권한이 필요합니다. 상대 경로는 프로젝트 디렉터리 기준입니다. 각 파일은
10 MiB마다 회전하고 백업 5개를 유지합니다. 빈 값이면 파일 기록을 끕니다.
브라우저 조작이나 분류 결과는 기록하지 않습니다. Docker Compose는 `deciflow-logs` 볼륨에 로그를 보존합니다.
호스트 디렉터리에서 직접 접근하려면 해당 볼륨 마운트를 쓰기 가능한 바인드 마운트로 바꾸세요.
