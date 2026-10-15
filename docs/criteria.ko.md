# Criteria 관리

[English](criteria.md) | [한국어](criteria.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

사이드바 **Criteria**에서 판정 프로필을 관리합니다. Laya와 Jev에 동일하게 적용합니다.

| 작업 | 방법 |
| --- | --- |
| 목록·검색 | 이름과 프로필 ID를 확인하고 Search by Name으로 검색 |
| 보기 | View로 현재 구성·지시문·5개 범주 정의를 읽기 전용으로 확인; Cancel로 닫기 |
| 추가 | Add profile → ID·이름·지시문·5개 범주 정의 입력 → Save changes |
| 수정 | Edit → 기준 변경 → Save changes. 기존 ID는 유지 |
| 취소 | Cancel edit로 현재 편집 초안 폐기 |
| 삭제 | Delete → Save changes. 저장 전에는 삭제되지 않음 |

- 결과 범주는 **Normal, Warning, Error, Security, Other**로 고정합니다.
  프로필은 `choice` 기준만 편집하며 긴급도(`score`)·작업 티켓 필요성(`noul`)은
  공통 고정 질문을 사용합니다. 임의 범주는 지원하지 않습니다.
- ID는 소문자로 시작하며 소문자·숫자·`_`·`-`로 최대 64자입니다.
  이름·지시문·모든 범주 정의는 비워둘 수 없습니다.
- `general`은 API 기본 프로필입니다. 목록 상단 **Default Criteria**에 별도로 표시하며
  **View**만 제공합니다. Edit·Delete 버튼은 표시하지 않습니다.
- 저장한 변경은 다음 분석부터 적용합니다. 실행 중인 작업은 수정·삭제 전 기준을
  유지하며 결과 JSON의 `questions.category`에 실제 사용한 기준을 남깁니다.
- 삭제한 프로필이 선택된 소스에는 대체 프로필을 직접 선택하세요. 페이지를 새로고침하면
  다른 브라우저에서 저장한 변경도 읽습니다. 화면 전환은 편집 초안을 유지합니다.
- 기준에는 관찰된 사건의 결과와 증거를 설명하세요. 특정 로그 문자열은 검증 샘플에서
  다루고 모델의 정확도는 별도로 검증하세요.

View와 Edit는 동시에 표시하지 않습니다. Edit·Add는 View를 닫고, View 중에는
편집 영역과 취소 버튼을 숨기고 저장을 막습니다. Cancel로 기존 편집 초안을 복원합니다.

Add·Edit에서는 목록을 숨기고 입력폼만 표시합니다. 저장 또는 Cancel edit 후 목록으로 돌아옵니다.

## 저장과 접근

기동 시 `DECIFLOW_DATA_DIR/criteria/criteria.json`이 없으면 [`profiles/`](../profiles/)에서
읽은 기본 프로필을 파일로 저장합니다. UI에서 Save changes를 누를 필요가 없습니다.
파일이 있으면 해당 전체 목록을 읽으며 기존 수정·삭제 내역을 덮어쓰지 않습니다.
기본 경로는 `/var/lib/deciflow-data/criteria/criteria.json`입니다.
저장 파일이 있으면 번들 JSON을 수정해도 운영 기준이 바뀌지 않습니다.

Docker Compose의 `deciflow-data` 볼륨을 Actions와 함께 사용하므로 추가 마운트가
필요하지 않습니다. 호스트 직접 실행에서는 공통 경로에 쓰기 권한이 있어야 하며,
필요하면 `.env`의 `DECIFLOW_DATA_DIR`을 쓰기 가능한 디렉터리로 설정하세요.
경로 변경은 기존 데이터를 자동으로 이전하지 않습니다.

관리 API는 `POST /api/criteria`로 목록을 읽고 `PUT /api/criteria`로 전체 목록을
저장합니다. Actions와 동일한 로컬·신뢰 UI 출처 검사를 적용합니다. 원격 UI는
`DECIFLOW_CSRF_TRUSTED_ORIGINS`를 설정하고 프록시 인증으로 접근을 보호하세요.
