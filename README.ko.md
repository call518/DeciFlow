<p align="center">
  <a href="https://youtu.be/bXuBJs4Hf70" target="_blank" rel="noopener noreferrer"><img src="images/DeciFlow-Logo.png" alt="DeciFlow" width="480"></a>
</p>

# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**다양한 데이터를 AI로 빠르게 판단하고 결과에 따른 후속 처리까지 자유롭게 자동화하세요.**

<p align="left">
  <a href="https://youtu.be/bXuBJs4Hf70" target="_blank" rel="noopener noreferrer">Demo Video - YouTube</a>
</p>

**[설치와 설정 → INSTALL.ko.md](INSTALL.ko.md)**

[PyPI: pip 또는 uv tool](INSTALL.ko.md#pypi),
[Docker Compose + Git Clone](INSTALL.ko.md#docker-compose),
[소스 프로세스 직접 실행 + Git Clone](INSTALL.ko.md#direct-processes) 중 하나를 선택하세요.
설치 가이드는 방식별 요구사항·엔진 연결·저장 경로·인증·기동·검증·유지 관리를 설명합니다.

## 소개

**DeciFlow**는 텍스트 로그와 구조화된 상담 기록을 타입이 있는 AI 판정으로 변환하고,
사람이 근거를 검토할 수 있도록 보존하며, 분류 후 Python Action을 실행할 수 있습니다.
로컬·SSH·HDFS Source를 읽고 브라우저에서 결과를 제공합니다. Batch 모드로 기존 파일을
조사하고 Realtime 모드로 새 로그 이벤트를 감시합니다.

**Laya 서버**는 같은 호스트 또는 별도 호스트에서 판정 모델을 실행합니다.
**Jev**는 대안으로 사용할 수 있는 유료 호스팅 추론 API입니다. DeciFlow가 데이터를
읽고 선택한 엔진으로 이벤트를 보냅니다. 기본 엔진은 Laya이며 유료 Jev로 자동 전환하지
않습니다. 공용 Laya 서버에 연결하는 DeciFlow 노드에는 로컬 GPU나 PyTorch가 필요하지
않습니다. **OAuth2-Proxy**는 선택적으로 Google 로그인과 HTTPS를 제공합니다.

## 핵심 개념

| 구성 요소 | 역할 |
| --- | --- |
| Source | 재사용 가능한 로컬·SSH·HDFS 입력 정의. TEXT는 이벤트 청크를, JSONL은 줄마다 객체 하나를 처리합니다. |
| Criteria | 이벤트의 판정·선택지·지시사항·검토 규칙을 정의한 이름 있는 프로필입니다. |
| Decision | `choice`·`score`·`noul` 판정. 프로필 하나에서 여러 이름의 판정을 요청 하나로 조합합니다. |
| Action | 분류 후 실행하는 선택적 Python 코드이며 결과를 별도로 기록합니다. |
| Task | 함께 사용할 Source·Criteria·청크 설정·선택적 Action·실행 일정을 지정합니다. |
| Run | 고정된 설정·진행 상태·결과·이력을 갖는 Task 실행 한 번입니다. |
| Review | 원래 AI 예측과 함께 저장하는 타입별 사람의 정정입니다. |

작업 흐름은 **Source → Criteria → 선택적 Actions → Task → Results → Review**입니다.
Batch Task는 수동 또는 일정에 따라 실행하고 Realtime Task는 중지할 때까지 새 이벤트를
감시합니다. 정의를 편집해도 기존 실행은 시작 당시 설정을 유지합니다.
DeciFlow가 티켓을 자동 생성하지는 않으며 후속 동작은 Action이 담당합니다.

## 아키텍처

[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/call518/DeciFlow)

![DeciFlow 아키텍처](images/DeciFlow-Architecture.png)

DeciFlow는 이벤트를 읽고 Laya 또는 Jev에 Task의 Criteria를 적용한 뒤 응답을 검증하고
판정·Action 결과를 SQLite에 저장합니다. Source 리더와 추론에는 동시 실행 한도가
적용됩니다. 여러 SSH Host의 결과를 통합하면서 호스트별 수집 상태도 보존합니다.
브라우저는 분류를 반복하지 않고 실행에 다시 연결하며, 브라우저가 닫혀도 Task는 계속됩니다.

정의·실행 이력·원본 입력·판정·검토 내용을 데이터 저장소에 보존합니다. 체크포인트가 있는
Batch·Realtime 실행은 서버 재시작 후 재개할 수 있고 일시정지한 실행은 그대로 유지합니다.
복구 시 원본 파일이 동일한지 검증합니다. 요구사항과 한계는
[Task 복구](docs/tasks.ko.md#서버-재시작-후-복구)와 [결과 저장](docs/configuration.ko.md#storage)을 참고하세요.

## 주요 기능

- **유연한 판정:** 분류 선택지·확률 가중 점수·Yes/No 확률을 조합합니다. 시스템 프로필은
  Normal·Warning·Error·Security·Other, 긴급도와 작업 티켓 확률을 제공합니다.
- **근거와 검토:** 확률·Criteria·원본 공급자 응답·형식 검증 실패·사람의 정정을 확인하고,
  전체 또는 검토된 결과를 JSON으로 내보냅니다. Certain이 정확성을 보장하지는 않습니다.
- **조사와 감시:** Batch·Realtime Task, cron 일정, 일시정지·재개, 다중 호스트 입력과
  영구 이력을 제공합니다.
- **결과 탐색:** 차트·실행 전체 필터·커서 페이지·공유 URL을 제공합니다. Decision 필터는
  결과 카드에 적용하고 다른 필터는 Overview도 갱신합니다. 표시 변경으로 추론하지 않습니다.
- **처리 측정:** 실행별 경과 시간·처리량·지연 백분위수를 제공합니다. 필터·페이지 변경은
  실행 지표를 변경하지 않습니다.
- **제어 가능한 자동화:** Python Action, 실행 오류 기록, 재사용 설정, 참조 확인과
  파괴적 유지 관리의 확인 절차를 제공합니다.
- **AI Criteria 작성:** 샘플 데이터를 검토한 뒤 OpenAI로 프로필 초안·수정을 작성합니다.
  작성 기능은 분류와 별개이며 API 비용이 발생합니다.
  [Criteria](docs/criteria.ko.md#ai로-criteria-생성)를 참고하세요.

## 활용 예시

접근 로그·애플리케이션 오류·시스템 이벤트 같은 운영 로그에서 시작할 수 있습니다.
내장 상담 예제는 문의 유형·처리 상태·후속 담당·긴급도·후속 조치 필요성도 보여 줍니다.

| 내장 예제 | 목적 |
| --- | --- |
| [Sample VOC Asia Culture Center Consulting QnA](docs/voc.ko.md) | 고객과 상담사의 전체 대화를 분류하고 남은 후속 조치를 검토합니다. |
| [Sample VOC Central Gov Consulting QnA](docs/voc.ko.md#정부기관-qna-샘플) | 정책 설명·신청 안내·기관 이관·미완료 기관 조치를 구분합니다. |
| [Sample VOC Local Gov Consulting QnA](docs/voc.ko.md#지방자치단체-qna-샘플) | 대화 근거로 지자체 문의와 약속된 조치를 분류합니다. |

내장 샘플 이름은 **Sample**로 시작합니다. 상담 Criteria는 한국어이며 현행 법률을
검증하지 않습니다. 샘플은 작업 흐름을 보여 주며 정확도를 측정·보장하는 자료가 아닙니다.
트래픽 분석·제조 판정·이미지 검사는 추가 통합과 도메인 검증이 필요하고, 이미지 검사에는
비전 모델도 필요합니다.

## 한계와 데이터 처리

- 파일을 점진적으로 읽지만 메모리는 활성 파일 수와 이벤트 크기에 영향을 받습니다.
  여러 줄 이벤트의 경계를 자동 감지하지는 않습니다.
- Laya·Jev에는 요청 예산과 공급자별 한계가 있습니다. 잘리거나 유효하지 않은 응답은
  거부하며 결과 경고와 응답 상세에서 확인합니다.
- 와일드카드는 텍스트 로그만이 아니라 일치하는 파일을 선택합니다. 바이너리·압축 파일이나
  현재 파일과 회전본의 동시 선택은 실패·중복 분석을 유발할 수 있습니다. 로컬 읽기·UTF-8
  오류는 실행을 중지하고 SSH 리더 실패는 Source/Host별로 기록합니다.
- Realtime은 완성된 줄을 기다립니다. 회전 시 남은 조각은 `incomplete`로 표시하며,
  빠른 회전과 copy-truncate 후 재증가는 이벤트 손실을 일으킬 수 있습니다.
- 클라이언트 동시성을 높여도 추론 처리량 증가를 보장하지 않습니다. 엔진의 처리 용량과
  요청 수락 한계가 적용됩니다.
- Laya는 선택한 서버로, Jev는 TypeSafe로 입력을 전송하며 Jev는 비용이 발생합니다.
  선택적 AI 작성은 검토한 샘플을 OpenAI로 전송합니다. 결과 저장소는 원본 입력과 Action
  결과를 포함합니다. 데이터와 백업을 보호해야 하며 디스크 이력은 자동 정리하지 않습니다.

상세 동작과 한계는 [Sources](docs/sources.ko.md), [사용법](docs/usage.ko.md),
[설정](docs/configuration.ko.md)을 참고하세요.

## 문서 안내

| 가이드 | 내용 |
| --- | --- |
| **[설치와 설정](INSTALL.ko.md)** | 세 가지 전체 설치 절차·배포 설정·프로세스 관리 명령 |
| [문서 색인](docs/README.ko.md) | 전체 사용 가이드와 기술 참조 |
| [Tasks](docs/tasks.ko.md) | 실행 모드·일정·이력·복구 |
| [Sources](docs/sources.ko.md) | 입력 형식·경로·SSH 신뢰·HDFS |
| [Criteria](docs/criteria.ko.md) | 타입별 판정 프로필·AI 작성 |
| [Python Actions](docs/actions.ko.md) | 후속 코드·환경·실행 결과 |
| [사용법](docs/usage.ko.md) | 탐색·차트·필터·검토·내보내기·시간 지표 |
| [결과 JSON](docs/results.ko.md) | 요청·결과 예제와 필드 참조 |
| [설정](docs/configuration.ko.md) | 환경변수 참조·운영 재정의·로그·유지 관리 |
| [개발과 릴리즈](docs/development.ko.md) | 테스트·모델 평가·패키지 검증·게시 |

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)
