# VOC 상담 처리 가이드

[English](voc.md) | [한국어](voc.ko.md) | [문서 안내](README.ko.md)

이 가이드는 고객과 상담원의 **전체 대화 한 건을 입력으로 받아**, 문의 유형과
상담 종료 시점의 처리 상태·후속 조치를 판단하는 흐름을 설명합니다. 서버 로그 Task도
계속 사용할 수 있으며, 입력 Source와 Criteria를 Task별로 구분합니다.

## 정부기관 QnA 샘플

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

## 지방자치단체 QnA 샘플

**Sample VOC Local Gov Consulting QnA** Source, Criteria, Task는 기존 설치에도 시작 시
자동 추가되며 저장된 사용자 수정은 유지합니다. Source는
`/host-logs/sample-logs/voc-local-gov-consulting-qna.jsonl`(3,280건)을
JSONL (Line), Content Field `상담내용`으로 읽습니다. 이 필드만 분류에 전달하고
`지방자치단체명`과 `상담담당부서`는 빈 부서명을 포함해 원본 메타데이터로 보존합니다.
한국어 Criteria는 지방행정 분야, 답변 유형, 후속 조치 담당, 긴급도, 후속 조치 필요성을
판단합니다. 일반적인 사업 일정이나 개선 계획만으로 개별 민원의 미완료 약속으로
판단하지 않습니다. Task는 Batch / Manual, Events/Chunk 1, Action None이며
Enabled와 Resume on Restart는 꺼져 있습니다. DeciFlow-UI를 시작하고
Task를 활성화한 뒤 Run으로 실행하세요. 네이티브 실행 시 Source 경로를 실제 로컬
샘플 파일 경로로 변경하세요.

## 1. 기본 샘플 실행

1. DeciFlow-UI를 시작합니다.
2. Source에서 **Sample VOC Asia Culture Center Consulting QnA**를 확인합니다.
3. Criteria에서 **Sample VOC Asia Culture Center Consulting QnA**를 확인합니다.
4. Tasks에서 기본 **Sample VOC Asia Culture Center Consulting QnA**를 View하여 아래 할당을 확인합니다.
5. Enabled를 켠 뒤 **Run**을 누릅니다. 활성화·저장만으로는 실행되지 않습니다.
6. Main의 Task Monitor에서 이 Task를 선택합니다.

| 설정 | 기본값 |
| --- | --- |
| Source Type | Local File |
| Source Path | `/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl` |
| Input Format | JSONL (Line) |
| Content Field | `consulting_content` |
| Task Mode | Batch / Manual |
| Criteria | Sample VOC Asia Culture Center Consulting QnA |
| Events/Chunk | 1 (JSONL에서 고정) |
| Action | None |
| Enabled / Resume on Restart | 최초 제공 시 모두 꺼짐 |

경로는 Docker Compose 마운트 기준입니다. 네이티브 실행에서는 Source 경로를 실제
파일 위치로 수정하세요. 파일은 한 줄에 JSON 객체 하나이며 `consulting_content`에
전체 대화 문자열을 넣습니다. 대화 안의 줄바꿈은 JSON 문자열의 `\n`으로 표현합니다.
제공 파일의 **841건을 각각 별도 상담으로 처리**하며 같은 내용도 합치지 않습니다.
빈 줄은 건너뛰고, 잘못된 JSON·누락되거나 비어 있는 본문 등은 실패로 표시합니다.

`voc-central-gov-consulting-qna.jsonl`은 다른 상담 자료이며 Content Field는
`consulting_content`입니다. 답변이나 처리 경과가 없는 입력에는 문의 유형 중심의
Criteria를 사용하고 해결 여부·미완료 약속을 추론하지 마세요.

Batch는 파일 처음부터 끝까지 읽습니다. 다시 Run하면 처음부터 새 실행을 만듭니다.
Realtime은 기존 파일 내용을 건너뛰고 새로 들어온 줄을 감시하므로 최초 파일 검증에는
Batch를 사용하세요. Jev를 선택했다면 유료 API를 사용합니다.

## 2. 결과에서 확인할 내용

- 판단 카드에는 후속 조치 담당·긴급도를 포함한 모든 항목을 설정된 순서대로 표시.
- **Input**: 이 판단의 근거가 된 전체 대화.
- **Probabilities and Criteria**: 항목별 확률·지시문·선택지 정의.
- **Review**: 사람이 확인한 정정값. AI 원본과 차트는 유지됩니다.
- **Source Hosts Detail**: 전체 실행의 호스트별 성공·실패·합계.

전체 완료 후 Success + Failed = 841인지 확인합니다. 일부를 Stop했다면 그때까지
완료한 건수만 집계됩니다. 실패는 Request Failed로 조회하고, 긴 대화가 입력 제한을
넘으면 엔진의 처리 결과·실패 사유·Truncated 표시를 확인하세요. JSONL 한 상담을
자동으로 여러 요청으로 분할하지 않습니다. 확률과 Certain은 실측 정확도가 아닙니다.

## 3. Criteria를 수정하는 순서

기본 샘플을 그대로 실행해 본 뒤, 변경하려면 **Clone**하여 별도 이름으로 저장하는
것을 권합니다. Task에서 새 프로필을 선택하고 저장한 뒤 새 실행을 시작하세요.
실행 중인 작업과 과거 결과는 당시의 Criteria 정의를 유지합니다.

각 입력란의 목적·타입 선택·중복 ID 오류 해결은 [Criteria 작성법](criteria.ko.md)을 참고하세요.
아래는 한국어 샘플의 실제 전체 입력값입니다. 기본 Criteria는 한국어로만 제공하며
기존 결과는 저장 당시의 선택지 이름을 유지합니다.


## Laya 질문 토큰 예산 확인

Criteria 편집기의 **Estimated Criteria Tokens**에서 전체·질문별 근사치와 예산 경고를
실시간 확인할 수 있습니다. 본문은 포함하지 않으며 정확한 토크나이저 계측을 대신하지 않습니다.

Laya는 상담 본문과 질문을 합친 `LAYA_MAX_TOKENS` 한도 외에, 각 질문의 지시문과
선택지에 `LAYA_HEAD_TOKENS` 예산을 적용합니다. 공통 Decision Instructions도
질문마다 반복됩니다. 본문의 Truncated 표시가 0이어도 지시문 뒤쪽은 잘릴 수 있습니다.

현재 VOC 전체 지시문은 질문 예산 256에서 완전히 보존되지 않습니다. 설치된
multilingual 토크나이저로 한국어 선택지를 적용한 샘플을 측정하면 질문별 head는
최대 471토큰이며, **`LAYA_HEAD_TOKENS=512`에서 모든 지시문이 보존**됩니다.
제공 상담 본문은 최대 1,600토큰으로, head를 더해도 현재 전체 한도 8,192 안에 들어갑니다.
이는 제공 파일·현재 샘플·해당 토크나이저의 측정값이며 다른 자료도 같다는 뜻은 아닙니다.

Laya로 이 샘플의 전체 지시문을 사용하려면 `.env`의 `LAYA_HEAD_TOKENS`를 512로
설정하고 DeciFlow-UI를 Restart한 뒤 새 실행을 시작하세요. 진행 중인 실행은 이전
설정을 유지합니다. 지시문·선택지·모델을 바꾸면 다시 측정해야 합니다. 각 선택지 설명은
Laya 내부의 별도 48토큰 제한도 적용받으므로 head만 늘린다고 모든 길이 제한이 사라지지는 않습니다.

Jev는 별도 한도와 토크나이저를 사용합니다. Laya의 토큰 수를 그대로 대입하지 마세요.
DeciFlow의 Jev 입력 바이트 검사는 정확한 토큰 계측이 아닙니다.

## 4. 전체 입력값

| Field | Value |
| --- | --- |
| Name | Sample VOC Asia Culture Center Consulting QnA |
| Default Chart Decision | 문의 유형 |

**Decision Instructions**

```text
고객과 상담원의 전체 대화를 읽고 대화가 종료된 시점의 상황을 판단한다.

대화에 명시된 사실만 사용하고, 생략되거나 마스킹된 정보는 추측하지 않는다.
안내가 끝난 것과 실제 업무 처리가 끝난 것을 구분한다.
콜백, 자료 발송, 부서 확인 등을 약속했더라도 완료 사실이 없으면 미완료로 판단한다.
고객이 나중에 예약하거나 방문할 예정이라는 사실만으로 회사 측 후속 조치가 필요하다고 판단하지 않는다.
판단에 필요한 근거가 부족하면 각 항목의 기타 또는 확인 불가에 해당하는 선택지를 사용한다.
```

### Decision 1: 문의 유형

| Field | Value |
| --- | --- |
| Decision ID | `inquiry_type` |
| Display Name | 문의 유형 |
| Type | Choice |

**Instructions**

```text
고객이 이 상담에서 문의한 주된 목적을 하나 선택한다.
여러 주제가 있으면 상담의 중심이 된 요청을 기준으로 판단한다.
기존 예약의 취소·변경·환불은 취소·변경·환불, 요금이나 할인 조건 문의는 요금·할인로 판단한다.
해당 범주가 없거나 주된 목적을 확인할 수 없으면 기타를 선택한다.
```

| Option ID | Option Definition |
| --- | --- |
| `예약` | 예약 가능 여부, 신규 예약, 단체 예약 등 예약 진행에 관한 문의 |
| `취소·변경·환불` | 기존 예약의 취소, 변경 또는 환불에 관한 문의 |
| `요금·할인` | 이용 요금, 할인 조건, 회원 혜택 또는 할인 적용에 관한 문의 |
| `시설·이용 안내` | 시설, 프로그램, 운영시간, 방문 방법 또는 교통·접근 방법에 관한 문의 |
| `기타` | 위 범주에 해당하지 않는 문의이거나 주된 문의 목적을 확인할 수 없음 |

### Decision 2: 처리 상태

| Field | Value |
| --- | --- |
| Decision ID | `handling_status` |
| Display Name | 처리 상태 |
| Type | Choice |

**Instructions**

```text
상담 종료 시점에 요청 처리가 어떤 상태인지 선택한다.
회사 측에서 해야 할 구체적인 조치가 남아 있으면 직원 조치 대기을 우선 선택한다.
회사 측 미완료 조치가 없고 고객의 특정 행동만 기다리고 있으면 고객 조치 대기을 선택한다.
필요한 안내나 처리가 끝나고 추가 조치가 없으면 처리 완료를 선택한다.
종료 시점의 상태를 판단할 수 없으면 확인 불가을 선택한다.
```

| Option ID | Option Definition |
| --- | --- |
| `처리 완료` | 필요한 안내나 처리가 끝났으며 구체적인 후속 조치가 남아 있지 않음 |
| `고객 조치 대기` | 회사 측 미완료 조치 없이 고객의 자료 제출, 확인 또는 신청 등 특정 행동을 기다리는 상태 |
| `직원 조치 대기` | 상담원이나 담당 부서가 수행할 콜백, 확인, 자료 발송 또는 처리 등이 남아 있는 상태 |
| `확인 불가` | 대화만으로 상담 종료 시점의 처리 상태를 확인할 수 없음 |

### Decision 3: 후속 조치 담당

| Field | Value |
| --- | --- |
| Decision ID | `follow_up_owner` |
| Display Name | 후속 조치 담당 |
| Type | Choice |

**Instructions**

```text
상담 종료 시점에 남은 다음 조치를 누가 수행해야 하는지 선택한다.
회사 측 조치가 남아 있으면 해당 조치를 수행할 상담원 또는 담당 부서를 선택한다.
회사 측 조치 없이 고객의 행동만 남아 있으면 고객를 선택한다.
남은 조치가 없으면 없음, 담당 주체가 불분명하면 확인 불가을 선택한다.
```

| Option ID | Option Definition |
| --- | --- |
| `고객` | 고객이 자료 제출, 확인 또는 신청 등 다음 조치를 해야 함 |
| `상담원` | 해당 상담원이 확인, 콜백 또는 자료 발송 등 다음 조치를 해야 함 |
| `담당 부서` | 상담원 외의 담당 부서가 확인, 연락 또는 처리 등 다음 조치를 해야 함 |
| `없음` | 추가로 수행해야 할 조치가 없음 |
| `확인 불가` | 후속 조치가 필요하지만 담당 주체를 확인할 수 없음 |

### Decision 4: 긴급도

| Field | Value |
| --- | --- |
| Decision ID | `urgency` |
| Display Name | 긴급도 |
| Type | Score |

**Instructions**

```text
대화에 명시된 피해와 시간 제약을 기준으로 개입 긴급도를 판단한다.
단순 불만이나 정보 부족만으로 긴급도를 높이지 않는다.
후속 조치가 필요하다는 사실만으로 높은 긴급도를 부여하지 않는다.
```

| Level | Definition |
| --- | --- |
| 0 | 낮음: 일상적인 안내이며 긴급한 피해나 임박한 기한이 드러나지 않음 |
| 1 | 보통: 후속 조치가 필요하지만 즉각적인 피해나 임박한 기한은 없음 |
| 2 | 높음: 임박한 기한이나 상당한 피해가 명시되어 빠른 개입이 필요함 |
| 3 | 매우 높음: 즉각적인 안전 위협이나 심각한 피해가 진행 중이어서 즉시 개입해야 함 |

### Decision 5: 후속 조치 필요

| Field | Value |
| --- | --- |
| Decision ID | `follow_up_required` |
| Display Name | 후속 조치 필요 |
| Type | Noul |

**Instructions**

```text
상담 종료 시점에 회사가 수행해야 할 미완료 후속 조치가 남아 있는가?

상담원이나 담당 부서가 수행하기로 한 콜백, 자료 발송, 사실 확인 또는 업무 처리가 남아 있으면 Yes에 해당한다.
대화에서 해당 조치가 완료되었다고 확인되면 미완료 조치로 보지 않는다.
고객의 예약, 방문, 자료 제출 등 고객 행동만 남아 있는 경우는 No에 해당한다.
회사 측 미완료 조치가 있다는 근거 없이 이를 추측하지 않는다.
```

선택지·단계는 입력하지 않습니다. 결과는 Yes 확률입니다.

## 5. 판단 기준 검증

아래는 실제 고객 데이터가 아닌 검증용 가상 사례입니다. 모델의 답을 보장하는 예시는 아닙니다.

| 상담 종료 상황 | 기대하는 판단 |
| --- | --- |
| 운영시간 안내를 마치고 추가 약속 없이 종료 | handling_status: 처리 완료 / owner: 없음 / 회사 후속 조치: No |
| 상담원이 “확인 후 전화드리겠습니다”라고 하고 완료 언급 없이 종료 | handling_status: 직원 조치 대기 / owner: 상담원 / 회사 후속 조치: Yes |
| 회사 측 남은 조치 없이 고객이 필요한 서류를 제출하기로 함 | handling_status: 고객 조치 대기 / owner: 고객 / 회사 후속 조치: No |
| 대화가 중간에 끝나 최종 상태를 알 수 없음 | handling_status: 확인 불가 / 남은 조치와 담당을 근거 없이 추측하지 않음 |

먼저 서로 다른 유형의 10–20건을 원문과 대조하세요. 틀린 사례에서 경계가 겹치거나
빠진 정의를 찾아 수정하고 새 실행으로 비교합니다. Inquiry Type의 정확성과
Handling Status·후속 조치 판단의 정확성은 각각 확인하세요. 예를 들어 문의 유형은
맞아도 약속한 콜백을 완료로 오인할 수 있습니다.
