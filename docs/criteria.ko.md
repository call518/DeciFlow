# Criteria 관리

[English](criteria.md) | [한국어](criteria.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

**Criteria**에서 판정 프로필을 관리합니다. Laya와 Jev에 같은 정의와 응답 검증을
적용합니다. 프로필에는 이름·공통 지시문·순서가 있는 판단 항목과 기본 차트용
**Default Chart Decision**을 모든 유형 중 하나 지정합니다. 항목 수는 3개로 고정하지 않으며
제공자의 입력·실행 제한은 적용됩니다.

기본 샘플을 포함한 모든 Criteria 프로필은 UUID를 사용합니다. View·Edit의 읽기 전용
**Criteria ID**와 **Copy** 버튼으로 확인·복사하고 Task 할당 및 결과의 `profile`·`profileId`와
대조할 수 있습니다. 이름 변경 시 ID는 유지하고 Add·Clone은 새 UUID를 발급합니다.
프로필 전체의 식별자이며 개별 질문을 식별하는 **Decision ID**와는 별개입니다.
샘플 UUID는 번들 JSON 파일에 고정값으로 저장합니다.

Default Chart Decision은 존재하는 판단 항목 중 정확히 하나를 지정하는 표시 설정입니다.
AI 답변·불확실성·필터는 바꾸지 않습니다. 모든 항목을 Overview에서
선택할 수 있습니다. Overview의 **Set as Default**나 Criteria 편집에서 변경합니다.
Score는 가중 점수를 가장 가까운 수준으로 반올림하며 중간값은 올립니다. Noul은 Yes 확률 구간입니다.

Choice 선택지의 **Needs Review**를 체크하면 Unknown/Other처럼 사람이 검토해야 하는
선택을 명시적으로 지정합니다. 저장된 `reviewOptions`는 해당 선택지 ID 목록입니다.
빈 목록은 선택값에 따른 검토만 끄며 불확실성 검사는 유지합니다. ChatGPT 자동 작성도 같은
`defaultDecision`과 `reviewOptions` 검증을 사용합니다.

## AI로 Criteria 생성

**Add Profile**에서 **Generate With AI**를 펼칩니다. DeciFlow의 `.env`에
`OPENAI_API_KEY`와 `OPENAI_CRITERIA_MODEL`(기본 `gpt-5.6-terra`, Responses API의
Structured Outputs 지원 필요)을 설정하고 DeciFlow를 재시작하세요.
키는 백엔드에서만 사용합니다.


AI 생성은 분류 품질을 좌우하는 핵심 규칙 작성을 돕는 선택적 기능입니다.
OpenAI 키 없이도 이 가이드를 따라 Criteria를 직접 작성·수정·저장할 수 있습니다.
기본 모델은 지능과 비용의 균형을 고려한 선택이며, 생성한 기준은 대표 샘플로
검토하세요. `.env.example`의 모델명 예시와 공식 목록에서 사용 가능 여부를 확인하세요.

1. 등록된 Source를 선택합니다. Remote File Source는 SSH Host 하나도 선택합니다.
2. **Sample Count**(10개 기본값, 20개·30개·50개·100개)를 지정하고, TEXT 입력은 Events Per Sample도
   지정한 뒤 **Preview Source Samples**를 누릅니다. Sample Count는 입력 샘플 개수,
   Events Per Sample는 각 샘플에 묶는 TEXT 이벤트 개수입니다. 샘플이 많을수록
   토큰 소비와 API 비용이 늘어날 수 있습니다.
   JSONL은 입력칸 대신 레코드 하나가 샘플 하나이며 설정된 본문 필드를 사용한다는 안내를 표시합니다.
3. 샘플을 확인·수정·제거합니다. 전체 Source를 훑어 지정한 개수만큼 무작위로
   추출하며, 빈 입력과 개별 150,000 UTF-8 바이트 초과 입력은 제외합니다. 선택된
   샘플은 총 150,000 UTF-8 바이트까지 허용하므로 Source 크기나 용량 제한에 따라
   실제 개수는 적을 수 있습니다. 전체 읽기가 20초를 넘으면 일부 샘플을 반환하지
   않고 실패합니다. 다시 미리보기 하면 새로 추출합니다. 미리보기는 OpenAI에
   전송하지 않으며, 생성할 때는 다시 추출하지 않고 화면에서 수정한 샘플을 보냅니다. Sample Count를
   변경하면 미리보기가 초기화되므로 생성 전에 다시 미리보기 하세요.
4. **Analysis Purpose Mode**의 기본값 **Automatic (ChatGPT)**를 유지하면 샘플에서
   목적을 추론합니다. 직접 지정하려면 **Manual**을 선택해 **Analysis Purpose**를
   입력하세요. **Generate Criteria**를 누르면 화면의 샘플, 모드, 수동 목적(입력한 경우),
   앱의 작성 규칙을 OpenAI에 전달합니다.
   민감한 내용은 먼저 제거하세요. OpenAI API 요금이 발생합니다.
5. 자동 모드의 **Suggested Analysis Purpose** 또는 수동 모드의 **Analysis Purpose**와
   자동 입력된 이름, 공통 지침, 순서대로 구성된 Decisions, 선택지·단계,
   Default Chart Decision과 토큰 추정치를 검토합니다.
6. **Save Changes**로 전체 프로필을 저장합니다. Task에는 별도로 할당하고
   대표 입력에 대한 실제 분류 결과를 확인하세요.

**Events Per Sample**는 TEXT 이벤트 몇 개를 미리보기 샘플 하나로 묶을지 정합니다.
예를 들어 5이면 이벤트 다섯 개가 샘플 하나가 됩니다. 실제 Task에서 사용할 묶음과
맞추세요. 이 값은 Task 설정을 변경하지 않습니다. JSONL은 이 입력칸을 숨기며, 레코드 하나를
샘플 하나로 읽고 Source의 본문 필드를 사용합니다.
로컬·원격 모두 파일 위치가 아니라 입력 형식에 따라 같은 규칙을 적용합니다.

**Analysis Purpose Mode**의 기본값은 **Automatic (ChatGPT)**입니다. 목적을 입력하지
않아도 AI가 샘플에 근거한 목적을 제안하고 같은 요청에서 Criteria 전체를 작성합니다.
샘플만으로 실제 업무 요구를 확정할 수는 없으므로 저장 전에 제안한 목적을 확인하세요.
분석 목적은 저장 후에도 유지되도록 프로필의 공통 지침에 포함합니다.

목적이 정해져 있으면 **Manual**을 선택하세요. 이때 **Analysis Purpose**는
AI가 어떤 판단 기준을 구성해야 하는지 알려주는 수동 분석 목적입니다. 입력의 성격,
판단할 질문·분류, 판단 시점, 우선순위, 제외 조건, 근거 부족 시 처리 방법을 자연어로
적으세요. 필요하면 이름과 지침에 사용할 언어도 명시하세요.
JSON이나 Criteria의 개별 필드를 직접 작성할 필요는 없습니다.

예: “고객 상담에서 문의 유형, 긴급도, 상담 종료 시 직원의 후속 조치 필요 여부를
판단하고 싶다. 약속한 콜백은 미처리 업무로 보고 고객만 해야 할 일은 제외한다.
근거가 부족하면 Unknown으로 분류한다. 이름과 지침은 한국어로 작성한다.”

생성하면 작성 중인 새 프로필 초안을 대체합니다. 누락·중복·거절·미완료 응답은
편집기에 반영하지 않으며 저장된 Criteria도 변경하지 않습니다.
생성 실패 시 기존 초안과 수정한 샘플을 유지하므로 재시도할 수 있습니다.
검증은 구조와 필수 항목을 확인하며 업무 기준의 정확성까지 보장하지는 않습니다.
일치하는 입력의 앞부분을 샘플로 사용하므로 드문 사례가 빠질 수 있습니다.
OpenAI는 Criteria 작성에만 사용하며 실제 분류는 자동 대체 없이 Laya 또는 Jev가
수행합니다. 기존 프로필은 Clone하여 새 초안에서 생성할 수 있습니다.

## 먼저 이해할 세 가지

- **Source**: 어떤 자료를 읽는가. JSONL의 본문 필드는 Source에서 지정합니다.
- **Criteria 프로필**: 그 자료에서 무엇을 판단하고 어떤 기준으로 답하는가.
- **Task**: Source와 Criteria를 연결해 언제 실행할지 정하는 작업입니다.

프로필 하나에 여러 **Decision**을 넣습니다. 예를 들어 상담 한 건을 한 번 요청하여
문의 유형(Choice), 처리 상태(Choice), 긴급도(Score), 후속 조치 필요(Noul)를 함께
판단할 수 있습니다. 항목을 추가할 때마다 Source나 별도의 UI 코드를 만들 필요는 없습니다.

처음에는 기본 샘플을 **Clone**하여 이름을 바꾸고 필요한 항목만 수정하세요.
[VOC 실습 가이드와 전체 입력값](voc.ko.md)에서 기본 Source·Task로 실행해 볼 수 있습니다.

## Profile Settings: 전체 판단의 공통 설정

| 화면 입력란 | 목적 | 무엇을 입력하나 |
| --- | --- | --- |
| Start From Template | 신규 초안의 출발점 | VOC 전체 대화는 상담용 템플릿을 선택합니다. Custom Decisions는 빈 사용자 구성에서 시작합니다. 템플릿을 다시 고르면 현재 초안 내용을 대체합니다. |
| Criteria ID | 프로필을 식별하는 UUID | 읽기 전용이며 Copy로 복사해 결과나 외부 연동에서 참조합니다. |
| Name | Task에서 고를 프로필 이름 | `VOC 상담 후속 조치 테스트`. 기존 프로필과 다른 이름을 사용합니다. |
| Default Chart Decision | Overview의 기본 차트 항목 | Choice·Score·Noul 중 정확히 하나. 모든 항목은 계속 실행하며 필터·AI 답변은 바꾸지 않습니다. |
| Decision Instructions | 모든 Decision에 적용할 공통 원칙 | 판단 시점, 사용할 근거, 추측 금지, 정보 부족 시 대응. 특정 항목의 선택지는 아래 Decision에서 정의합니다. |

**공통 지시문 예시**

```text
상담 전체 대화를 읽고 대화가 종료된 시점의 상황을 판단한다.
대화에 명시된 사실만 사용하고 마스킹된 내용을 추측하지 않는다.
약속한 업무와 실제 완료된 업무를 구분한다.
근거가 부족하면 각 항목의 기타 또는 확인 불가 선택지를 사용한다.
```

## Decision: 한 가지 질문과 답변 방식

진한 헤더의 `Decision 2 · 처리 상태 · Choice`는 두 번째 판단 항목이라는 뜻입니다.
번호는 표시 순서이며 항목의 고유 ID가 아닙니다. 이름·타입·순서를 변경하면 헤더도 갱신됩니다.

| 화면 입력란 | 목적 | 예시·주의점 |
| --- | --- | --- |
| Decision ID | 저장 결과에서 항목을 식별하는 키 | `handling_status`. 프로필 안에서 고유해야 합니다. 소문자 영문으로 시작하며 소문자·숫자·밑줄만 사용하고 64자 이내입니다. |
| Display Name | 사람이 읽는 결과 카드 제목 | `처리 상태`. 한국어 사용 가능. ID를 이름 칸에 반복할 필요는 없습니다. |
| Type | 어떤 형태의 답을 받을지 선택 | 유형 분류는 Choice, 순서 있는 수준은 Score, 예·아니요 확률은 Noul. |
| Instructions | 이 항목만의 질문과 판정 규칙 | `대화 종료 시 회사 측 미완료 조치가 남아 있는지 구분한다.` 공통 원칙은 상단에 둡니다. |

**세 가지 이름을 구분하세요:** Profile Name은 Task가 선택하는 전체 묶음의 이름,
Decision ID는 결과 필드 키, Display Name은 그 필드의 화면 제목입니다.
Choice의 Option ID는 그 질문에 대한 답의 코드입니다.

| 판단 타입 | 설정 | 결과 |
| --- | --- | --- |
| Choice | 고유한 선택지 ID와 정의 2–255개 | 선택값과 선택지별 확률 |
| Score | 0부터 번호를 붙이는 순서 있는 단계 정의 2–10개 | 확률 가중 점수와 단계별 확률 |
| Noul | 예·아니요 질문 | 0–1 범위의 Yes 확률 |

### Choice: 하나의 선택지로 분류

선택지 행의 왼쪽은 **Option ID**, 오른쪽은 **Option Definition**입니다.
선택지 ID는 같은 Decision 안에서만 고유하면 됩니다. 다른 Decision에서 `unknown`을
다시 써도 됩니다. `all`·`failed`는 예약어이므로 사용하지 마세요.

예를 들어 Decision ID를 `handling_status`, Display Name을 `처리 상태`, Type을
Choice로 지정하고 다음처럼 작성합니다.

**Instructions**

```text
대화 종료 시점의 처리 상태를 선택한다.
회사 측 조치가 남아 있으면 staff_pending을 선택한다.
완료되었고 남은 조치가 없으면 complete, 근거가 부족하면 unknown을 선택한다.
```

| Option ID | Option Definition |
| --- | --- |
| `complete` | 필요한 안내나 처리가 완료되었고 남은 조치가 없음 |
| `staff_pending` | 상담원 또는 담당 부서의 확인·콜백·발송 등 구체적인 조치가 남아 있음 |
| `unknown` | 대화만으로 종료 시점의 상태를 확인할 수 없음 |

결과와 차트의 선택지 이름은 `booking` → Booking처럼 Option ID를 바탕으로 표시합니다.
오른쪽 정의는 판단 기준이며 별도의 선택지 표시 이름 칸이 아닙니다. Choice Option ID에는 한국어도 사용할 수 있습니다. 기본 샘플은 예약·고객 조치 대기처럼
선택지 코드도 한국어입니다. Decision ID는 유지합니다.

정의에는 단어 하나보다 **언제 그 답을 선택하는지**를 씁니다. 서로 겹치는 정의에는
우선순위를 명시하세요. `기타`라는 뜻의 코드로 `other`, 정보 부족은 `unknown`을
사용하면 검토 대상으로도 표시됩니다.

### Score: 순서 있는 수준으로 평가

점수 단계의 설명만 작성합니다. 위에서부터 **0, 1, 2, ...**가 되므로 낮은 수준에서
높은 수준 순서로 입력하세요. 2–10개 단계가 필요합니다.

| 단계 | 정의 예시 |
| --- | --- |
| 0 | 낮음: 일상 안내이며 임박한 기한이나 피해가 없음 |
| 1 | 보통: 후속 처리가 필요하지만 임박한 기한이나 피해는 없음 |
| 2 | 높음: 명시된 임박한 기한이나 피해로 빠른 처리가 필요함 |

출력은 단계별 확률을 가중한 점수입니다. `1.4 / 2`는 가능한 정상 결과이며 반드시
정수 단계 하나를 선택하는 방식이 아닙니다. 단계의 근거·경계는 Instructions에 적으세요.

### Noul: Yes가 참일 확률

선택지·단계는 작성하지 않습니다. Instructions에 **Yes/No로 답할 수 있는 질문**과
Yes에 해당하는 조건을 씁니다.

```text
상담 종료 시 회사가 수행해야 할 미완료 후속 조치가 남아 있는가?
상담원이나 담당 부서의 콜백·확인·발송 약속이 미완료로 남아 있으면 Yes이다.
고객 행동만 남아 있으면 No이다. 약속을 완료로 간주하지 않는다.
```

85%는 Yes 확률이며 업무가 85% 완료되었다는 뜻이 아닙니다. Action을 자동 실행하라는
지시도 아닙니다. 실제 외부 동작은 Task의 Action 할당과 스크립트가 결정합니다.


## 작성 중 실시간 토큰 추정

Add Profile·Edit Profile 제목 아래의 **Estimated Criteria Tokens**는 입력할 때마다
현재 초안의 예상 토큰을 계산합니다. 저장하지 않아도 지시문·선택지·타입·항목 추가와
삭제를 반영하며 외부 API나 토크나이저 서버를 호출하지 않습니다.

- **Total**: 공통 지시문을 각 질문에 반복한 비용을 포함한 Criteria 전체 추정치.
- **Largest Question**: 지시문과 선택지를 합친 가장 큰 질문의 추정치.
- **Per-Decision Estimates**: 펼치면 항목별 추정치를 확인합니다.
- **Laya**: 현재 서버의 질문 head 예산·본문 포함 질문별 전체 한도를 표시합니다.
  질문이 head 예산을 넘을 가능성이나 선택지 설명이 48토큰을 넘을 가능성을 경고합니다.
- **Jev**: 현재 서버의 전체 요청·질문별 한도와 비교합니다. 본문을 추가하면 두 한도
  모두 추가로 소비합니다.

Name·Display Name는 판단 지시문 비용에 포함하지 않습니다.

이 값은 문자 기반 **근사치**이며 정확한 모델 토크나이저 결과나 과금량이 아닙니다.
질문별 서식·선택지·앱의 공통 안전 지시문을 반영하지만 실제 토크나이저에 따라 달라집니다.
특히 **상담 본문은 제외**합니다. 따라서 표시값이 한도 아래라고 전체 요청이 반드시
들어가거나 지시문이 잘리지 않는다고 보장하지 않습니다. 엔진 예산을 아직 읽지 못하면
N/A로 표시합니다. 경고만으로 저장을 차단하지는 않습니다.

## 작성·저장·Task 연결 순서

1. Clone 또는 Add Profile로 시작합니다. 템플릿을 쓸 경우 먼저 선택합니다.
2. Name과 공통 Decision Instructions를 입력합니다.
3. 각 Decision의 고유 ID·표시 이름·타입·지시문을 작성합니다.
4. Choice 선택지 또는 Score 단계를 작성합니다.
5. 모든 유형 중 항목 하나를 Default Chart Decision으로 선택합니다.
6. Save Changes로 저장합니다. Cancel Edit는 미저장 초안을 버립니다.
7. Task를 Edit하여 해당 Source 행의 Criteria에 새 프로필을 선택하고 저장합니다.
8. 새 실행에서 원문과 답을 비교합니다. Criteria만 저장해도 Task에 자동 할당되지는 않습니다.

Add Decision은 질문을 하나 추가합니다. Add Option / Level은 **현재 Decision 안에**
답의 선택지·단계를 추가합니다. Remove는 해당 선택지·단계만, Remove Decision은
질문 전체를 지웁니다. Move Up / Down은 판단 항목의 표시 순서를 바꿉니다.

## 저장 오류를 해결하는 방법

| 메시지·증상 | 확인할 내용 |
| --- | --- |
| Name is required. | 상단 프로필 Name을 입력합니다. |
| Decision IDs must be unique. | 서로 다른 Decision에 같은 ID를 쓰지 않았는지 확인합니다. 예: `inquiry_type`과 `handling_status`를 구분합니다. |
| Option IDs must be unique. | 같은 Choice 내부의 왼쪽 ID를 구분합니다. 오른쪽 정의만 바꿔도 ID 중복은 해소되지 않습니다. |
| Choice requires 2–255… | 선택지 수, 빈 ID, 예약어 all·failed를 확인합니다. |
| Score requires 2–10… | 단계 정의가 2–10개인지 확인합니다. |
| Default Chart Decision을 고를 수 없음 | 판단 항목을 추가하고 기본 항목으로 지정합니다. |
| 빈 이름·지시문·정의 관련 오류 | 프로필과 각 Decision의 필수 항목, 선택지·단계 정의를 모두 채웁니다. |

Decision ID와 Display Name을 혼동하지 마세요. 예를 들어 두 항목의 표시 이름이
달라도 Decision ID가 모두 `category`라면 저장되지 않습니다.

**View**는 선택 행 바로 아래에서 저장된 정의를 읽기 전용으로 표시합니다. Criteria에
재진입하면 미저장 초안은 버려집니다. 프로필 삭제는 Save Changes 시 적용하며
Task가 참조 중이면 차단합니다.

## 기존 시스템 프로필

모든 프로필은 검색 가능한 **Criteria** 목록 하나에서 View·Edit·Clone·Delete로 관리합니다.
**Sample General System**도 선택적인 일반 프로필입니다. 직접 편집하거나
Task 할당을 변경한 후 삭제할 수 있으며 재시작해도 복구하지 않습니다. 템플릿은
**Start From Template**에서 계속 사용할 수 있습니다. 저장된 프로필이 없어도 직접
작성하거나 AI로 새 프로필을 생성할 수 있습니다. 모든 템플릿·수동 작성·AI 생성
프로필은 같은 타입별 판단 정의를 사용하며 공통 지침은 모든 Decision에 적용합니다.

최초 초기화 시 시스템 예시와 **Sample VOC Asia Culture Center Consulting QnA**을 제공합니다.
기존 설치도 시작할 때 상담 샘플의 ID와 이름이 모두 없으면 자동 추가합니다. 저장된
프로필은 덮어쓰지 않으며, 이 필수 샘플을 삭제하면 다음 시작 시 다시 추가됩니다.
다른 예시는 데이터 초기화 없이 **Start From Template**으로 불러옵니다. 상담 상태는 대화 종료 시점의 상태이며 이후 업무 완료 사실은 아닙니다.
질문만 있는 입력에는 문의 분류 기준을 사용하고 해결 여부·후속 약속을 추측하지 마세요.

## 결과·검토·저장

각 결과에 모든 판단 항목을 설정된 순서대로 표시합니다.
**Probabilities and Criteria**는 항목별 확률과 기준을 표시합니다. **Review**에서
Choice 선택지·범위 내 Score 값·Noul 확률을 수정합니다. 수정값을 비우면 Not Reviewed로
돌아갑니다. AI 원래 답변과 차트는 바꾸지 않습니다. Export Reviewed JSON은 어떤 항목이든
AI와 다른 수정값이 있는 결과를 내보냅니다.

모든 Choice에서 선택값 확률 70% 미만·상위 두 확률 차이 10%p 미만·Laya가 보고한
선택지 구분 소실을 검사합니다. `reviewOptions`로 지정한 Other·Unknown 선택도 검토 대상으로 표시합니다.
차트의 확실성은 선택한 Choice 기준이고 어느 판단 항목이나 기록 전체의 문제도 Needs Review가 됩니다.
이는 실측 정확도가 아닌 휴리스틱이며 Score·Noul의 신뢰도를 평가하지 않습니다.

실행 중인 작업은 고정한 프로필을 사용합니다. 결과에 `decisionDefinitions`·`decisions`를
보존하므로 이후 수정으로 과거 결과의 표시가 바뀌지 않습니다.
현재 저장된 기본 항목은 초기 차트 선택에만 적용합니다. 새 차트 식별자는 기본 항목을 제외하며 서로 다른 판단
정의는 구분합니다. Choice 없이 Score·Noul만 있는 프로필도 지원합니다.

프로필은 `DECIFLOW_DATA_DIR/deciflow.sqlite3`에 저장합니다. 번들 JSON은 초기값·템플릿이며
Criteria 관리는 신뢰한 UI Origin에서만 허용합니다.

VOC 샘플은 한국어로만 제공하며 누락된 샘플은 시작 시 추가합니다.

Laya는 본문 한도와 별도로 질문 지시문·선택지의 head 예산을 적용합니다.
본문이 잘리지 않아도 지시문이 잘릴 수 있습니다. [VOC 토큰 예산 안내](voc.ko.md#laya-질문-토큰-예산-확인)를 확인하세요.

정부기관 샘플의 Source·한국어 Criteria·비활성 Batch Task도 시작 시 자동 제공됩니다.
[Sample VOC Central Gov Consulting QnA 설정](voc.ko.md#정부기관-qna-샘플)을 참고하세요.

## 프로필 메타데이터

모든 템플릿·수동 작성·AI 생성 프로필은 `questions`와 `defaultDecision`을 사용하며
Choice 정의는 `reviewOptions`를 명시적으로 저장합니다. 공통 지침은 모든 Decision에 적용합니다.
결과와 Action은 AI 답변에 `decisions`, 항목별 불확실성과 검토 사유에
`decisionAssessments`를 사용합니다.
