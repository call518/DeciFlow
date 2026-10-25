# 선택적 Google 로그인: Docker 구성

[English](authentication.md) | [설치](../INSTALL.ko.md) | [문서 안내](README.ko.md)

먼저 [INSTALL](../INSTALL.ko.md)로 DeciFlow를 기동하세요. HTTPS·Google 로그인이
필요할 때만 **OAuth2-Proxy를 Docker로 추가**합니다. 승인 사용자는 DeciFlow 데이터와
관리 기능을 공유하며 Laya는 별도로 운영합니다.

공통 준비 후 DeciFlow 설치 방식에 맞는 절차 하나를 선택합니다.
[PyPI](#pypi) · [Docker Compose](#docker) · [프로세스 직접 실행](#source).

| 방식 | `.env`·프록시 디렉터리의 루트 |
| --- | --- |
| PyPI | `~/.config/deciflow` |
| Docker Compose / 직접 실행 | `<checkout>` |

CLI 설치는 `OAUTH2_PROXY_MANAGED=false`로 프록시를 Docker에서 운영하면서
로그인 계정 UI를 유지합니다.

<a id="certificates"></a>

## 공통 준비

브라우저에서 접근 가능한 도메인과 TCP 4443 허용을 전제로 합니다.
이 설정 셸에서 도메인을 한 번 지정하세요. `example.com`은 문서용이므로 실제 도메인으로 바꿉니다.

```bash
export DECIFLOW_DOMAIN="deciflow.example.com"
export DECIFLOW_HTTPS_URL="https://${DECIFLOW_DOMAIN}:4443"
export DECIFLOW_CERT_DIR="$HOME/.config/deciflow-certificates/${DECIFLOW_DOMAIN}"
```

### 인증서: 하나만 선택

**선택 1 또는 선택 2 중 하나만 실행합니다. 둘 다 실행하지 않습니다.**

---

#### 선택 1: Let's Encrypt 인증서 (권장)

 공개 DNS가 호스트로 연결되고 HTTP-01 발급·갱신 시
TCP 80을 사용할 수 있어야 합니다. Python 3.12·sudo 사용을 전제로 합니다.
Certbot의 이메일·약관 안내를 완료하세요.

```bash
sudo python3.12 -m venv /opt/deciflow-certbot
sudo /opt/deciflow-certbot/bin/python -m pip install certbot
sudo /opt/deciflow-certbot/bin/certbot certonly --standalone \
  --cert-name "$DECIFLOW_DOMAIN" -d "$DECIFLOW_DOMAIN"
```

<a id="certificate-files"></a>

실제 파일 내용을 복사합니다. [DNS-01](dns-tls.ko.md#dns01) 발급 후에도 이 단계부터 진행합니다.

```bash
install -d -m 700 "$DECIFLOW_CERT_DIR"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 644 \
  "/etc/letsencrypt/live/$DECIFLOW_DOMAIN/fullchain.pem" "$DECIFLOW_CERT_DIR/fullchain.pem"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 600 \
  "/etc/letsencrypt/live/$DECIFLOW_DOMAIN/privkey.pem" "$DECIFLOW_CERT_DIR/privkey.pem"
```

→ **[인증서 준비 완료: 다른 선택지는 생략하고 Google 설정으로 이동](#google-settings)**

---

#### 선택 2: 자체 서명 인증서

 1안이 어렵다면 Certbot을 생략하고 아래처럼 같은 파일을 만듭니다.
브라우저에 인증서 경고가 표시되며 경고 화면에서 계속 진행합니다.

```bash
(
  set -eu
  umask 077
  install -d -m 700 "$DECIFLOW_CERT_DIR"
  openssl req -x509 -nodes -newkey rsa:2048 -sha256 -days 365 \
    -subj "/CN=$DECIFLOW_DOMAIN" -addext "subjectAltName=DNS:$DECIFLOW_DOMAIN" \
    -keyout "$DECIFLOW_CERT_DIR/privkey.pem" -out "$DECIFLOW_CERT_DIR/fullchain.pem"
)
```

→ **[인증서 준비 완료: 다른 선택지는 생략하고 Google 설정으로 이동](#google-settings)**

---

<a id="google-settings"></a>

### Google과 `.env`

[Google Cloud](https://console.cloud.google.com/)에서 동의 화면과 OAuth **웹 애플리케이션**
클라이언트를 만들고 아래 출력값을 등록합니다. 테스트 상태라면 사용할 계정을
테스트 사용자에도 추가하세요.

```bash
printf 'JavaScript origin: %s\n' "$DECIFLOW_HTTPS_URL"
printf 'Redirect URI: %s/oauth2/callback\n' "$DECIFLOW_HTTPS_URL"
openssl rand -base64 32
```

인증을 우회하는 HTTP 직접 접속을 막도록 `DECIFLOW_BIND_HOST`를 `127.0.0.1`로
변경합니다. Compose는 UI의 호스트 공개 포트를 제거하고 컨테이너 내부 통신은 유지합니다.

마지막 출력은 쿠키 키로 사용합니다. 선택한 방식의 **기존 `.env`**에 아래 출력값을
적용하고 자리표시자 3개를 바꾸세요. URL은 셸 변수 참조가 아닌 실제 값으로 저장합니다.

```bash
cat <<EOF
DECIFLOW_BIND_HOST=127.0.0.1
OAUTH2_PROXY_ENABLED=true
OAUTH2_PROXY_MANAGED=false
OAUTH2_PROXY_PUBLIC_URL=${DECIFLOW_HTTPS_URL}
OAUTH2_PROXY_CLIENT_ID=REPLACE_WITH_GOOGLE_CLIENT_ID
OAUTH2_PROXY_CLIENT_SECRET=REPLACE_WITH_GOOGLE_CLIENT_SECRET
OAUTH2_PROXY_COOKIE_SECRET=REPLACE_WITH_GENERATED_COOKIE_KEY
EOF
```

<a id="pypi"></a>

## PyPI: uv tool 또는 pip

초기화된 패키지 설정에 위 공통 `.env` 값을 적용합니다. pip 방식은 가상환경을 활성화하세요.

```bash
proxy_config_dir="$HOME/.config/deciflow"
```

```bash
test -f "$proxy_config_dir/oauth2-proxy/allowed-emails.txt" || \
  cp "$proxy_config_dir/oauth2-proxy/allowed-emails.example.txt" \
     "$proxy_config_dir/oauth2-proxy/allowed-emails.txt"
install -d -m 755 "$proxy_config_dir/oauth2-proxy/tls"
install -m 644 "$DECIFLOW_CERT_DIR/fullchain.pem" "$proxy_config_dir/oauth2-proxy/tls/fullchain.pem"
install -m 600 "$DECIFLOW_CERT_DIR/privkey.pem" "$proxy_config_dir/oauth2-proxy/tls/privkey.pem"
```

`allowed-emails.txt`의 예시 주소를 지우고 승인 Google 이메일을 한 줄에 하나씩 넣습니다.
`oauth2-proxy.cfg`의 `email_domains = []`는 유지합니다.

먼저 DeciFlow를 재시작합니다. 네이티브 인증 모드는 설정 실수로 `0.0.0.0`을
남겨도 루프백 바인딩을 강제합니다. `OAUTH2_PROXY_MANAGED=false`이면 호스트 프록시 바이너리나
HTTPS 포트 미점유 여부를 검사하지 않습니다.

```bash
deciflow stop
deciflow config test
deciflow start --daemon
```

이후 Docker 프록시를 기동합니다. Linux 호스트 네트워크로 DeciFlow 루프백에 연결하므로
4000을 외부 공개하지 않습니다. 프록시는 DeciFlow 실행 계정 권한으로 파일을 읽습니다.

```bash
docker run -d --name deciflow-oauth2-proxy --restart unless-stopped \
  --network host --user "$(id -u):$(id -g)" \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --env-file "$proxy_config_dir/.env" \
  -v "$proxy_config_dir/oauth2-proxy:/etc/oauth2-proxy:ro,Z" \
  quay.io/oauth2-proxy/oauth2-proxy:v7.15.5 \
  --config=/etc/oauth2-proxy/oauth2-proxy.cfg \
  --upstream=http://127.0.0.1:4000/ \
  --redirect-url="${DECIFLOW_HTTPS_URL}/oauth2/callback"
```

[검증](#verify)으로 진행합니다.

<a id="docker"></a>

## Docker Compose

저장소 루트에서 해당 `.env`에 공통 값을 적용합니다.

```bash
proxy_config_dir="$PWD"
```

```bash
test -f "$proxy_config_dir/oauth2-proxy/allowed-emails.txt" || \
  cp "$proxy_config_dir/oauth2-proxy/allowed-emails.example.txt" \
     "$proxy_config_dir/oauth2-proxy/allowed-emails.txt"
install -d -m 755 "$proxy_config_dir/oauth2-proxy/tls"
install -m 644 "$DECIFLOW_CERT_DIR/fullchain.pem" "$proxy_config_dir/oauth2-proxy/tls/fullchain.pem"
install -m 600 "$DECIFLOW_CERT_DIR/privkey.pem" "$proxy_config_dir/oauth2-proxy/tls/privkey.pem"
```

`allowed-emails.txt`의 예시 주소를 지우고 승인 Google 이메일을 한 줄에 하나씩 넣습니다.
`oauth2-proxy.cfg`의 `email_domains = []`는 유지합니다.

Compose 프록시는 이미지 UID 65532를 사용합니다. 권한을 지정하고 서비스를 재생성합니다.

```bash
sudo chown 65532 oauth2-proxy/tls/privkey.pem
chmod 644 oauth2-proxy/oauth2-proxy.cfg oauth2-proxy/allowed-emails.txt
sudo chcon -Rt container_file_t oauth2-proxy
docker compose config --quiet
docker compose up -d --remove-orphans --force-recreate ui oauth2-proxy
```

Compose가 UI 공개 포트를 제거하고 HTTPS 4443을 공개합니다.

[검증](#verify)으로 진행합니다.

<a id="source"></a>

## 프로세스 직접 실행

저장소 루트에서 해당 `.env`에 공통 값을 적용합니다.

```bash
proxy_config_dir="$PWD"
```

```bash
test -f "$proxy_config_dir/oauth2-proxy/allowed-emails.txt" || \
  cp "$proxy_config_dir/oauth2-proxy/allowed-emails.example.txt" \
     "$proxy_config_dir/oauth2-proxy/allowed-emails.txt"
install -d -m 755 "$proxy_config_dir/oauth2-proxy/tls"
install -m 644 "$DECIFLOW_CERT_DIR/fullchain.pem" "$proxy_config_dir/oauth2-proxy/tls/fullchain.pem"
install -m 600 "$DECIFLOW_CERT_DIR/privkey.pem" "$proxy_config_dir/oauth2-proxy/tls/privkey.pem"
```

`allowed-emails.txt`의 예시 주소를 지우고 승인 Google 이메일을 한 줄에 하나씩 넣습니다.
`oauth2-proxy.cfg`의 `email_domains = []`는 유지합니다.

먼저 DeciFlow를 재시작합니다. 네이티브 인증 모드는 설정 실수로 `0.0.0.0`을
남겨도 루프백 바인딩을 강제합니다. `OAUTH2_PROXY_MANAGED=false`이면 호스트 프록시 바이너리나
HTTPS 포트 미점유 여부를 검사하지 않습니다.

```bash
uv run deciflow stop --config-dir "$PWD"
uv run deciflow config test --config-dir "$PWD"
uv run deciflow start --daemon --config-dir "$PWD"
```

이후 Docker 프록시를 기동합니다. Linux 호스트 네트워크로 DeciFlow 루프백에 연결하므로
4000을 외부 공개하지 않습니다. 프록시는 DeciFlow 실행 계정 권한으로 파일을 읽습니다.

```bash
docker run -d --name deciflow-oauth2-proxy --restart unless-stopped \
  --network host --user "$(id -u):$(id -g)" \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --env-file "$proxy_config_dir/.env" \
  -v "$proxy_config_dir/oauth2-proxy:/etc/oauth2-proxy:ro,Z" \
  quay.io/oauth2-proxy/oauth2-proxy:v7.15.5 \
  --config=/etc/oauth2-proxy/oauth2-proxy.cfg \
  --upstream=http://127.0.0.1:4000/ \
  --redirect-url="${DECIFLOW_HTTPS_URL}/oauth2/callback"
```

[검증](#verify)으로 진행합니다.

<a id="verify"></a>

## 검증과 운영

쿠키 없이 API에 요청하면 인증서 검증 성공과 **401** 응답을 확인해야 합니다.
자체 서명은 `--cacert "$DECIFLOW_CERT_DIR/fullchain.pem"`을 추가합니다.

```bash
curl --connect-timeout 5 --max-time 15 -i "${DECIFLOW_HTTPS_URL}/api/status"
```

출력된 HTTPS 주소를 시크릿 브라우저로 열고 승인 계정 로그인·이메일 배지를 확인한 뒤
[데모](../INSTALL.ko.md#demo)를 반복하세요. 미등록 계정은 거부되어야 합니다.
로그아웃은 계정 메뉴의 Sign Out을 사용합니다.

| 배포 | 로그 | 프록시·인증서 변경 적용 |
| --- | --- | --- |
| 패키지 / 직접 실행 | `docker logs --tail=100 deciflow-oauth2-proxy` | `docker rm -f deciflow-oauth2-proxy` 후 해당 `docker run` 재실행 |
| Compose | `docker compose logs --tail=100 oauth2-proxy` | `docker compose up -d --no-deps --force-recreate oauth2-proxy` |

별도 운영하는 프록시 컨테이너는 CLI가 종료하지 않으며 Docker로 관리합니다.
애플리케이션 포트를 바꾸면 단독 컨테이너 upstream도 수정하세요.
프록시를 중지해도 네이티브 앱은 외부 HTTP가 아닌 루프백에 남습니다.

<a id="renewal"></a>

## 인증서 갱신

Let's Encrypt는 `sudo /opt/deciflow-certbot/bin/certbot renew --dry-run`으로 검사하고
사용 중인 Certbot 갱신 예약 작업을 활성화합니다. 갱신 후 준비 경로의 인증서 복사와
각 방식의 TLS 복사를 다시 수행하고 위 명령으로 프록시를 재생성하세요.
자체 서명은 만료 전에 재생성합니다.
RFC2136 자동화는 [DNS-01 운영](dns-tls.ko.md#dns01-renewal)을 참고하세요.

<a id="proxy-config"></a>

## 구성 항목

컨테이너의 기본 경로는 `/etc/oauth2-proxy/`입니다. 위 절차가 해당 경로로 마운트합니다.

| 설정 | 기본값과 용도 |
| --- | --- |
| `provider` | `"google"`: Google 로그인 제공자. |
| `https_address` | `"0.0.0.0:4443"`: 모든 IPv4 인터페이스의 4443 포트에서 HTTPS 수신. 공개 도메인이 아니라 바인딩 주소입니다. |
| `tls_cert_file`, `tls_key_file` | `/etc/oauth2-proxy/tls/fullchain.pem`, `/etc/oauth2-proxy/tls/privkey.pem`: 컨테이너 안에서 사용하는 경로입니다. |
| `authenticated_emails_file` | `/etc/oauth2-proxy/allowed-emails.txt`: 컨테이너 안에서 사용하는 이메일 파일입니다. |
| `email_domains` | `[]`: 개별 이메일 허용 목록 정책 유지. 네이티브 설정 검사는 비어 있지 않은 값을 거부합니다. |
| `reverse_proxy` | `false`: 기본 구성은 OAuth2-Proxy가 직접 TLS를 처리합니다. |
| `pass_access_token`, `pass_authorization_header`, `pass_basic_auth`, `pass_user_headers` | `false`: 해당 인증정보·사용자 헤더 전달 옵션을 비활성화합니다. |
| `cookie_name`, `cookie_path` | `"__Host-deciflow_session"`, `"/"`: 호스트 범위의 세션 쿠키. |
| `cookie_secure`, `cookie_httponly`, `cookie_samesite` | `true`, `true`, `"lax"`: HTTPS 전용, JavaScript 접근 금지, SameSite 보호. |
| `cookie_refresh`, `cookie_expire` | `"1h"`, `"8h"`: 갱신 주기와 세션 수명. |
| `code_challenge_method` | `"S256"`: OAuth PKCE 인증 방식. |
| `api_routes` | `["^/api(?:/|$)"]`: 미인증 API 요청에 로그인 페이지 리디렉션 대신 401 반환. |
| `flush_interval`, `upstream_timeout` | `"100ms"`, `"0s"`: 스트리밍 전달 주기와 upstream 응답 타임아웃 없음. |

<a id="api-origin-protection"></a>

## API 출처 보호

DeciFlow는 Source·Task 관리, 설정, 파일 접근 등 보호 대상 API 요청의
브라우저 `Origin` 헤더를 검사합니다.
[OWASP가 안내하는 Origin 검사 기법](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#using-standard-headers-to-verify-origin)을 사용하며,
`DECIFLOW_CSRF_TRUSTED_ORIGINS`는 HTTP 표준 헤더가 아닌 DeciFlow 설정입니다.
CSRF 토큰을 발급하거나 검증하지는 않습니다.

OAuth2-Proxy를 사용하지 않으면 요청의 스킴과 Host(포트 포함)가 출처와 같아야 합니다.
다른 PC에서도 서버 IP나 도메인으로 접속하면 별도 설정 없이 동작합니다.
OAuth2-Proxy를 활성화하면 백엔드 연결이 HTTP여도 `OAUTH2_PROXY_PUBLIC_URL`을
외부 HTTPS 출처로 사용합니다. 이 검사 자체는 전달 헤더를 읽지 않습니다.
전달 헤더를 활성화한다면 Uvicorn이 실제 프록시만 신뢰하도록 설정하세요.

일반적으로 `DECIFLOW_CSRF_TRUSTED_ORIGINS`는 비워 둡니다. 추가 UI 출처를 명시적으로
허용할 때만 전체 출처를 쉼표로 구분해 등록하며, 끝에 슬래시는 붙이지 않습니다.

```dotenv
DECIFLOW_CSRF_TRUSTED_ORIGINS=https://admin.example.com,https://console.example.com
```

각 항목은 보호 대상 API 작업을 허용하므로 직접 관리하는 출처만 등록하세요.
HTTPS 하위 도메인 와일드카드도 지원하지만 정확한 출처 지정을 권장합니다.
출처가 없거나 `null`이거나 허용되지 않으면 HTTP 403을 반환합니다.
명령행 API 클라이언트도 허용된 Origin을 보내야 합니다. 출처 등록이 CORS를 활성화하지는 않습니다.

이 검사는 브라우저를 이용한 교차 출처 요청을 방어하며 호출자를 인증하지는 않습니다.
직접 HTTP 요청을 만드는 클라이언트는 Origin을 위조할 수 있습니다.
인증은 OAuth2-Proxy로 수행하고 신뢰하지 않는 클라이언트가 백엔드에 직접 접근하지 못하게 하세요.
HTTP 모드에서 Host는 클라이언트가 제공하므로 이 검사만으로 DNS 리바인딩이나 직접 API 접근을 막지는 못합니다.
