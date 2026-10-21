# Google 로그인과 이메일 허용 목록

[English](authentication.md) | [프로젝트 README](../README.ko.md)

**DeciFlow**는 소스를 읽고 **Laya 서버**(직접 운영하는 추론 엔진) 또는
**Jev 서비스**(유료 호스팅 추론 API)를 호출하며 웹 UI·API를 제공합니다.
**OAuth2-Proxy**는 Google 로그인과 관리자가 작성한 이메일 허용 목록으로
브라우저·API의 접근을 제한합니다. HTTPS를 직접 처리하고 승인된 요청을
DeciFlow로 중계하므로 Nginx는 필요하지 않습니다.
소스 접근·Laya/Jev 호출·Action 전송의 인증 방식은 그대로 유지합니다.
허용된 사용자는 DeciFlow의 데이터와 관리 기능을 공유합니다.
사용자별 저장 공간이나 역할 구분을 추가하는 기능은 아닙니다.

이 안내를 적용하려면 `.env`에 `OAUTH2_PROXY_ENABLED=true`를 지정하세요. 기본값
`false`는 OAuth·인증서 없이 `http://localhost:4000`에서 HTTP 데모를 제공합니다.
OAuth2-Proxy 활성 시 HTTPS 4443 포트만 공개하며 UI 호스트 포트는 공개하지 않습니다.
모드 변경 후 `docker compose up -d --remove-orphans`를 실행하세요. UI 포트 구성을
재생성하고 불필요한 OAuth2-Proxy 컨테이너를 제거하며 데이터는 삭제하지 않습니다. 모드 전환에
`restart`만 사용하지 마세요. 활성 모드의 설정 오류 시 실행을 중단하며 HTTP로 자동 전환하지 않습니다.

진입점은 계속 `docker-compose.yml`입니다. 설정값에 따라 `compose/`의 파일을 자동
선택하므로 해당 파일을 `-f`로 직접 지정하지 마세요. include 기능을 위해
Docker Compose 2.20.0+가 필요합니다.

Docker 없는 설치와 OAuth2-Proxy 자동 실행은 [네이티브 안내](native.ko.md)를 따르세요.

## 준비 사항

- Compose 플러그인이 포함된 Docker와 DeciFlow `.env`.
- DeciFlow 호스트를 가리키는 도메인, 해당 도메인의 신뢰할 수 있는 TLS 인증서,
  호스트의 TCP 4443 접근 허용. DNS 등록만으로 HTTPS가 활성화되지는 않습니다.
- OAuth **웹 애플리케이션**을 등록할 수 있는 Google Cloud 프로젝트.

예시의 `https://deciflow.example.com:4443`을 실제 HTTPS 출처로 바꾸세요.
인증서 발급·갱신과 Google 계정 설정은 운영자가 수행해야 하며
Compose가 자동으로 생성하지 않습니다.
도메인 레코드·인증서 발급·갱신·OAuth2-Proxy 반영은 [DNS·TLS 준비 안내](dns-tls.ko.md)에
따라 준비한 뒤 아래 Google 설정을 진행하세요.

## 1. Google 로그인 등록

[Google Cloud 콘솔](https://console.cloud.google.com/)에서 OAuth 동의 화면을
설정하고 **웹 애플리케이션** 유형의 OAuth 클라이언트를 생성합니다.

- 승인된 JavaScript 원본: `https://deciflow.example.com:4443`
- 승인된 리디렉션 URI: `https://deciflow.example.com:4443/oauth2/callback`

동의 화면이 테스트 모드라면 사용할 계정을 Google 테스트 사용자에도 추가하세요.
Google 테스트 사용자 목록과 DeciFlow 이메일 허용 목록은 별도의 검사입니다.
다음 단계에 사용할 클라이언트 ID와 클라이언트 보안 비밀번호를 보관하세요.
비밀값을 채팅에 보내지 마세요.
[OAuth2-Proxy Google 안내](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/google/)도 참고하세요.

## 2. 로컬 설정 준비

Docker 호스트의 DeciFlow 저장소 루트에서 실행합니다.

```bash
test -f .env || cp .env.example .env
test -f oauth2-proxy/allowed-emails.txt || cp oauth2-proxy/allowed-emails.example.txt oauth2-proxy/allowed-emails.txt
mkdir -p oauth2-proxy/tls
chmod 600 .env
openssl rand -base64 32
```

`.env`에 `OAUTH2_PROXY_ENABLED=true`를 지정하고 `OAUTH2_PROXY_PUBLIC_URL`에 경로·끝의 / 없는 HTTPS 출처를 지정하고,
`OAUTH2_PROXY_CLIENT_ID`와 `OAUTH2_PROXY_CLIENT_SECRET`에 Google 등록 값을 넣습니다.
생성한 무작위 값은 `OAUTH2_PROXY_COOKIE_SECRET`에 넣으세요.

`oauth2-proxy/allowed-emails.txt`에는 **승인할 Google 계정 이메일만 한 줄에
하나씩** 작성하고 예시 주소는 제거하세요. 도메인 와일드카드를 쓰거나 프록시
설정에 `email_domains`를 추가하지 마세요.

이메일 파일은 정확한 주소만 비교하며 정규식이나 `*@domain` 패턴을 지원하지 않습니다.
줄 맨 앞의 `#`는 주석입니다. `#` 앞 공백이나 이메일 뒤 인라인 주석은 사용하지 마세요.
Google 로그인에는 Gmail·Workspace 등 Google 계정을 사용할 수 있습니다.
`email_domains`는 파일이 아니라 `oauth2-proxy/oauth2-proxy.cfg`의 설정입니다.
도메인을 추가하면 파일의 개별 계정에 더해 그 도메인의 Google 계정 전체를 허용합니다.
기본 빈 목록은 파일에 등록된 이메일만 허용합니다.

`oauth2-proxy/tls/fullchain.pem`과 `oauth2-proxy/tls/privkey.pem`에 인증서 실제
파일을 배치하세요. 마운트 디렉터리 밖을 가리키는 심볼릭 링크는 사용하지 마세요.
고정한 이미지의 실행 UID는 65532입니다. 개인 키의 소유권과 권한을 지정하세요.

```bash
sudo chown 65532 oauth2-proxy/tls/privkey.pem
sudo chmod 600 oauth2-proxy/tls/privkey.pem
```

공개 인증서와 허용 목록은 컨테이너가 읽을 수 있게 유지하세요. 인증서 갱신 후 파일을
교체하고 개인 키 권한을 다시 적용한 뒤 프록시 컨테이너를 재생성합니다.
로컬 설정·허용 목록·TLS 디렉터리는 Git과 이미지 빌드에서 제외됩니다.

## 3. 검증과 실행

비밀값이 포함된 전체 설정을 출력하지 않고 검증합니다.

```bash
docker compose config --quiet
```

`.env`의 `COMPOSE_PROFILES`로 CPU·CUDA 또는 외부 추론을 선택한 뒤 시작합니다.

```bash
docker compose up -d
```

설정한 **HTTPS** 출처로 접속하세요. OAuth2-Proxy는 4443 포트를 공개하며
기존 DeciFlow UI 포트는 호스트의 공개 포트에서 제거됩니다.
외부에서 접근할 수 있는 별도의 네이티브 DeciFlow 프로세스나 인증 없는 UI
컨테이너를 함께 실행하지 마세요. Laya의 기존 포트·API 키 설정은 바뀌지 않습니다.

OAuth2-Proxy는 v7.15.5로 고정합니다. Secure·HttpOnly 호스트 쿠키를 사용하고,
Google 세션은 매시간 갱신하며 세션 수명은 8시간입니다.
유효한 세션 없는 API 요청에는 **401**을 반환하며 페이지를 새로고침해 다시 로그인합니다.
스트리밍 전달 간격은 100ms이며 upstream 응답 타임아웃을 두지 않아 장시간
결과 스트리밍을 허용합니다. 세션이 만료되어도 백그라운드 Task는 취소하지 않으며,
이미 열린 스트림의 인증을 지속적으로 재검사하지는 않습니다.

## 4. 접근 검증

사용자에게 서비스를 공개하기 전에 확인하세요.

1. 시크릿 브라우저에서 Main·저장된 실행 URL을 열면 로그인이 필요해야 합니다.
2. 승인된 계정으로 소스·설정을 읽고 Task를 실행할 수 있어야 하며,
   미등록 계정은 차단되어야 합니다. Google 테스트 사용자라는 이유만으로 허용되면 안 됩니다.
3. 쿠키 없는 `curl -i https://deciflow.example.com:4443/api/status` 요청에는 401을
   반환해야 하며, 사용자·이메일 헤더를 위조해도 접근할 수 없어야 합니다.
4. 다른 컴퓨터에서 기존 DeciFlow UI 포트로 직접 접근할 수 없어야 합니다.
5. 30초를 넘는 실행에서도 완료 전부터 결과가 전달되어야 합니다.
   Laya·Jev를 모두 사용한다면 각각 확인하세요. Jev 호출은 과금됩니다.
6. `https://deciflow.example.com:4443/oauth2/sign_out`에서 로그아웃하고 Main을
   새로고침하면 API 접근에 다시 로그인이 필요해야 합니다.
   프록시 세션을 지우는 동작이며 Google 계정 자체에서 로그아웃하지는 않습니다.

로컬 자동 스모크 테스트는 동일한 버전의 공식 OAuth2-Proxy 바이너리를 내려받고
절대 경로를 지정해 실행합니다.

```bash
OAUTH2_PROXY_BINARY=/path/to/oauth2-proxy uv run pytest -q tests/test_oauth2_proxy.py
```

이 테스트는 일회용 로컬 설정·자체 서명 테스트 인증서를 사용하며 Google에 접속하거나
실제 자격 증명을 사용하지 않습니다. 테스트 전용 공개 경로로 스트림 중계도 확인합니다.
실제 Google 계정 허용·거부와 운영 HTTPS는 위 수동 검증을 별도로 수행해야 합니다.

## 운영

허용 목록은 변경을 감지해 다시 읽지만 편집기가 마운트된 파일을 교체하면 컨테이너가
기존 파일을 계속 읽을 수 있습니다. 확실히 반영하려면 프록시만 재생성하세요.
`oauth2-proxy/oauth2-proxy.cfg`·Google 인증정보·쿠키 키·TLS 파일 변경에도 같은 명령을 사용합니다.

```bash
docker compose up -d --no-deps --force-recreate oauth2-proxy
```

`OAUTH2_PROXY_PUBLIC_URL`을 변경하면 포트를 포함해 Google의 승인 원본·리디렉션 URI를
함께 수정하고 `docker compose up -d ui oauth2-proxy`로 콜백·신뢰 UI 출처를 갱신하세요.
`redirect_uri_mismatch`는 요청한 콜백이 해당 Google 클라이언트의 등록 URI와
정확히 일치하지 않는다는 뜻입니다.

`.env`는 값을 보존하면서 `.env.example`과 같은 항목 순서·주석 배치를 유지하세요.
`docker compose config`는 비밀값을 출력하므로 `--quiet` 없이 출력하지 마세요.

긴급하게 세션을 취소하려면 쿠키 암호화 키도 변경하고 프록시를 재생성하세요.
기존 프록시 쿠키를 모두 무효화합니다. 즉시 접속을 끊어야 한다면 기존 연결도 종료하세요.
프록시 재시작은 스트림을 끊지만 Task를 중지하지는 않습니다.

백그라운드 Task를 유지하면서 웹 접근만 중지하려면:

```bash
docker compose stop oauth2-proxy
```

UI는 내부 연결 상태를 유지하며 프록시를 중지해도 인증 없는 접근을 허용하지 않습니다.
