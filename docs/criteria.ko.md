# Criteria 관리

[English](criteria.md) | [한국어](criteria.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

사이드바 **Criteria**에서 판정 프로필을 관리합니다. Laya와 Jev에 동일하게 적용합니다.

**Registered Criteria**에는 편집 가능한 프로필을 표시합니다. 최초 실행·초기화 시
**Sample Application**·**Sample Authentication**·**Sample HTTP access**·
**Sample Network / tcpdump text**를 제공합니다. Sample은 기본 제공 예시라는 뜻이며
Profile ID와 판정 정의는 그대로입니다. Default Criteria는 별도로 유지합니다.

| 작업 | 방법 |
| --- | --- |
| 목록·검색 | 이름을 확인하고 Search by Name으로 검색 |
| 보기 | View로 현재 구성·지시문·5개 범주 정의를 선택한 행 아래에서 읽기 전용으로 확인; View를 다시 누르면 접기 |
| 추가 | Add Profile → 이름·지시문·5개 범주 정의 입력 → Save Changes |
| 복제 | Clone으로 Add Profile을 열면 원본 지시문·범주 정의·정규화 설정을 복사합니다. 이름은 `원본 이름 (Clone)`이며 내부 UUID가 자동 생성되며 Save Changes로 저장합니다. 취소해도 원본은 유지됩니다 |
| 수정 | Edit → 기준 변경 → Save Changes. 내부 ID는 유지 |
| 취소 | Cancel Edit로 현재 편집 초안 폐기 |
| 삭제 | Delete → Save Changes. 저장 전에는 삭제되지 않음 |

- 결과 범주는 **Normal, Warning, Error, Security, Other**로 고정합니다.
  프로필은 `choice` 기준만 편집하며 긴급도(`score`)·작업 티켓 필요성(`noul`)은
  공통 고정 질문을 사용합니다. 임의 범주는 지원하지 않습니다.
- 이름·지시문·모든 범주 정의는 비워둘 수 없습니다.
- `general`은 API 기본 프로필입니다. 목록 상단 **Default Criteria**에 별도로 표시하며
  **View**와 **Clone**을 제공합니다. Edit·Delete 버튼은 표시하지 않습니다.
- 저장한 변경은 다음 분석부터 적용합니다. 실행 중인 작업은 수정 전 기준을
  유지하며 결과 JSON의 `questions.category`에 실제 사용한 기준을 남깁니다.
- 저장된 Task가 참조하는 프로필은 삭제할 수 없으므로 먼저 해당 Task를 변경하세요.
  새로고침하면 다른 브라우저의 저장 내용도 읽습니다. 사이드바에서 Criteria로
  재진입하면 목록을 열고 미저장 초안은 버립니다.
- 기준에는 관찰된 사건의 결과와 증거를 설명하세요. 특정 로그 문자열은 검증 샘플에서
  다루고 모델의 정확도는 별도로 검증하세요.

View와 Edit는 동시에 표시하지 않습니다. Edit·Add는 View를 닫고, View 중에는
편집 영역과 취소 버튼을 숨기고 저장을 막습니다. Cancel로 기존 편집 초안을 복원합니다.

Add·Edit에서는 목록을 숨기고 입력폼만 표시합니다. 저장 또는 Cancel Edit 후 목록으로 돌아옵니다.

## 저장과 접근

기동 시 DB에 Criteria가 처음 생성되면 [`profiles/`](../profiles/)의 번들 초기값을 저장합니다.
저장된 수정·삭제 내역은 보존합니다. 설정은 별도 JSON이 아닌
`DECIFLOW_DATA_DIR/deciflow.sqlite3`에서 관리합니다. 번들 JSON은 초기값으로만 사용하며
이를 수정해도 저장된 프로필을 덮어쓰지 않습니다.

Docker Compose의 `deciflow-data` 볼륨을 Actions와 함께 사용하므로 추가 마운트가
필요하지 않습니다. 호스트 직접 실행에서는 공통 경로에 쓰기 권한이 있어야 하며,
필요하면 `.env`의 `DECIFLOW_DATA_DIR`을 쓰기 가능한 디렉터리로 설정하세요.
경로 변경은 기존 데이터를 자동으로 이전하지 않습니다.

관리 API는 `POST /api/criteria`로 목록을 읽고 `PUT /api/criteria`로 전체 목록을
저장합니다. Actions와 동일한 로컬·신뢰 UI 출처 검사를 적용합니다. 원격 UI는
`DECIFLOW_CSRF_TRUSTED_ORIGINS`를 설정하고 프록시 인증으로 접근을 보호하세요.

새 프로필과 Clone은 Name과 무관한 내부 UUID를 자동 생성합니다. ID는 목록·View·입력 폼에 표시하지 않습니다. 기존 ID는 Task·이력 참조를 보존하도록 유지합니다. 이름 중복은 대소문자와 앞뒤 공백을 무시하여 실시간으로 붉은색 안내를 표시하고, 초안을 유지한 채 저장을 차단합니다. 한글 등 비영문 이름도 사용할 수 있습니다. 서버에서도 같은 이름 중복 규칙을 검사합니다.
