# 문서 안내

[English](README.md) | [한국어](README.ko.md) | [프로젝트 README](../README.ko.md)

DeciFlow와 Laya 실행은 [빠른 시작](../README.ko.md#빠른-시작--docker--laya-cpu)부터
확인하세요. 기본 Docker 배포를 시작하기 전에 [Google 로그인·HTTPS 설정](authentication.ko.md)을
완료해야 합니다. 필요한 작업에 따라 아래 문서를 선택하면 됩니다.
Docker 없이 로컬에서 실행하려면 [네이티브 안내](native.ko.md)부터 따르세요.

Remote File은 Settings에서 SSH Keys·SSH Hosts를 먼저 등록합니다. 이후
Source → Criteria → 선택적 Actions → Tasks 순으로 구성하고 Main에서 Task의 현재·최근 실행 결과를 확인합니다.

## DeciFlow 사용과 설정

| 문서 | 용도 |
| --- | --- |
| [Sources](sources.ko.md) | 로컬·SSH 파일 소스 등록과 Tasks에서 선택 |
| [사용법](usage.ko.md) | 로그 분석·결과 필터·판정 검토·재접속·지표 확인 |
| [설정](configuration.ko.md) | 환경변수·Laya/Jev 모델·요청 예산 설정 |
| [Sample VOC Asia Culture Center Consulting QnA](voc.ko.md) | 기본 샘플 실행·전체 Criteria 입력값·판단 기준 검증 |
| [Sample VOC Central Gov Consulting QnA](voc.ko.md#정부기관-qna-샘플) | 정부기관 QnA 샘플의 Source·한국어 Criteria·Task 실행 |
| [Sample VOC Local Gov Consulting QnA](voc.ko.md#지방자치단체-qna-샘플) | 지방자치단체 QnA 샘플의 Source·한국어 Criteria·Task 실행 |
| [Criteria](criteria.ko.md) | 필드별 작성법·타입별 예시·저장 오류 해결 |
| [Python Actions](actions.ko.md) | 판정 후 Python 코드 실행과 실행 환경 관리 |
| [Tasks](tasks.ko.md) | 재사용 실행 설정·Cron 예약·연속 감시·영속 실행 이력 |
| [결과 저장](result-storage.ko.md) | SQLite 저장·페이지 크기·설정·결과 통합 저장·백업·DB 확장 |

## 배포와 연동

| 참고 자료 | 내용 |
| --- | --- |
| [DNS·TLS 인증서](dns-tls.ko.md) | 공개 DNS·Certbot DNS-01/RFC2136·인증서 배포·자동 갱신·WSL 점검 |
| [네이티브 설치](native.ko.md) | Docker 없는 로컬 데모·엔진 선택·시작과 종료·선택적 OAuth2-Proxy 자동 실행 |
| [Google 로그인](authentication.ko.md) | 선택적 OAuth2-Proxy 배포·이메일 허용 목록·HTTPS·검증 |
| [Docker 배포](../README.ko.md#docker-배포-상세) | 공개 이미지·CPU/CUDA 프로필·포트·마운트·볼륨·운영 명령 |
| [Dockerfile과 Compose](../README.ko.md#dockerfile과-compose의-역할) | UI 실행 이미지와 Compose 서비스 구성 방식 |
| [Laya 연동](laya-integration.ko.md) | 요청 구성·응답 검증·서버 설정·제약 |
| [요청·결과 JSON](results.ko.md) | Laya/Jev 공통 스키마·state·타입별 판단·답변·필드 설명 |

## Laya 평가

[Laya 로그 검증](laya-validation.ko.md)은 정답 로그로 분류 결과를 평가하고 생성한
보고서를 읽는 방법을 안내합니다. 평가 스크립트는 선택적 개발 도구이며
DeciFlow 실행에는 필요하지 않습니다.

## JSON 예시

- [Laya 요청](examples/laya-request.json)
- [Laya 결과](examples/laya-result.json)

분류 코드와 일치 여부를 검사한 설명용 예시이며 실제 추론 측정값은 아닙니다.
Jev와의 차이는 [요청·결과 JSON](results.ko.md)에서 설명합니다.
