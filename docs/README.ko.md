# 문서 안내

[English](README.md) | [한국어](README.ko.md) | [프로젝트 README](../README.ko.md)

**[전체 설치·설정 절차: INSTALL.ko.md](../INSTALL.ko.md)**

환경에 맞는 설치 방식 하나를 선택하세요.

- [PyPI / pip 또는 uv tool](../INSTALL.ko.md#pypi) **(권장)**: 저장소를 복제하지 않고 pip 또는 uv tool로 설치합니다.
- [Git clone + Docker Compose](../INSTALL.ko.md#docker-compose): 선택적 로컬 Laya를 포함한 컨테이너 배포입니다.
- [Git clone + 네이티브 Python](../INSTALL.ko.md#direct-processes): 복제한 소스 저장소에서 CLI를 실행합니다.

`.env`를 수정하기 전에 [환경 파일 위치](configuration.ko.md#환경-파일-위치)를
확인하세요. 세 방식은 이 파일을 자동 공유하지 않습니다.
INSTALL은 HTTP로 빠르게 기동하고 `.env`를 설정하는 절차입니다.
Laya는 Docker를 사용하며, 선택적인 [Docker Google 로그인](authentication.ko.md)은 별도로 구성합니다.

Remote File을 사용하려면 Settings에서 SSH Keys·SSH Hosts를 먼저 등록합니다.
일반적인 구성 순서는 Source → Criteria → 선택적 Actions → Tasks입니다.

## DeciFlow 사용과 설정

| 문서 | 용도 |
| --- | --- |
| [Sources](sources.ko.md) | 로컬·SSH 파일 소스 등록과 Tasks에서 선택 |
| [사용법](usage.ko.md) | 로그 분석·결과 필터·판정 검토·재접속·지표 확인 |
| [설정](configuration.ko.md) | 환경변수·엔진·저장·백업·로그·유지 관리 |
| [Sample VOC Asia Culture Center Consulting QnA](voc.ko.md) | 기본 샘플 실행·전체 Criteria 입력값·판단 기준 검증 |
| [Sample VOC Central Gov Consulting QnA](voc.ko.md#정부기관-qna-샘플) | 정부기관 QnA 샘플의 Source·한국어 Criteria·Task 실행 |
| [Sample VOC Local Gov Consulting QnA](voc.ko.md#지방자치단체-qna-샘플) | 지방자치단체 QnA 샘플의 Source·한국어 Criteria·Task 실행 |
| [Criteria](criteria.ko.md) | 필드별 작성법·타입별 예시·저장 오류 해결 |
| [Python Actions](actions.ko.md) | 판정 후 Python 코드 실행과 실행 환경 관리 |
| [Tasks](tasks.ko.md) | 재사용 실행 설정·Cron 예약·연속 감시·영속 실행 이력 |

## 배포와 연동

| 참고 자료 | 내용 |
| --- | --- |
| [PyPI / pip 또는 uv tool 설치](../INSTALL.ko.md#pypi) | 권장 명령 설치·init/config 명령·Docker Laya 연결·HTTP 데모 |
| [Docker 배포](../INSTALL.ko.md#docker-compose) | 공개 이미지·CPU/CUDA 프로필·포트·마운트·볼륨·운영 명령 |
| [Git 복제 기반 네이티브 설치](../INSTALL.ko.md#direct-processes) | 소스 기반 로컬 데모·엔진 선택·시작과 종료·Docker Laya |
| [DNS·TLS 인증서](dns-tls.ko.md) | 공개 DNS·Certbot DNS-01/RFC2136·인증서 배포·자동 갱신·WSL 점검 |
| [Google 로그인](authentication.ko.md) | 선택적 OAuth2-Proxy 배포·이메일 허용 목록·HTTPS·검증 |
| [Dockerfile과 Compose](development.ko.md#docker-runtime) | UI 실행 이미지와 Compose 서비스 구성 방식 |
| [Laya 연동·검증](laya.ko.md) | 요청 구성·응답 검증·서버 설정·모델 평가·제약 |
| [요청·결과 JSON](results.ko.md) | Laya/Jev 공통 스키마·state·타입별 판단·답변·필드 설명 |

[개발·테스트·릴리즈 가이드](development.ko.md)에서 검증 환경과 게시 절차를 확인하세요.

## Laya 평가

[Laya 로그 검증](laya.ko.md#evaluation)은 정답 로그로 분류 결과를 평가하고 생성한
보고서를 읽는 방법을 안내합니다. 평가 스크립트는 선택적 개발 도구이며
DeciFlow 실행에는 필요하지 않습니다.

## JSON 예시

- [Laya 요청](examples/laya-request.json)
- [Laya 결과](examples/laya-result.json)

분류 코드와 일치 여부를 검사한 설명용 예시이며 실제 추론 측정값은 아닙니다.
Jev와의 차이는 [요청·결과 JSON](results.ko.md)에서 설명합니다.
