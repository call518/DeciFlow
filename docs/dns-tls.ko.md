# DNS와 TLS 인증서 준비

[English](dns-tls.md) | [인증 안내](authentication.ko.md) | [문서 안내](README.ko.md)

**DeciFlow**는 소스를 읽고 UI·API를 제공하며 **Laya 서버**와 **Jev 서비스**는
추론을 담당합니다. **OAuth2-Proxy**는 브라우저·API 접근의 HTTPS 진입점입니다.
이 안내는 `OAUTH2_PROXY_ENABLED=true`일 때만 필요합니다. 기본 HTTP 데모에는
도메인·인증서가 필요하지 않습니다.

이 문서는 DNS 준비, Certbot DNS-01을 통한 Let's Encrypt 인증서 발급,
자동 갱신과 OAuth2-Proxy 반영을 안내합니다. 기존 권한 DNS 서버인 BIND9에
RFC2136·TSIG 업데이트를 설정하는 방식입니다. DNS 사업자가 지원하는 Certbot
플러그인도 다른 발급 방법입니다. 한 방법을 선택한 뒤 동일한 인증서 배포 단계를
따르세요. BIND9 직접 운영은 DeciFlow의 필수 요구사항이 아닙니다.

## 호스트와 예시 값

| 항목 | 예시 | 역할 |
| --- | --- | --- |
| DeciFlow·Certbot 호스트 | Linux 또는 WSL2, 저장소 `/opt/deciflow` | Docker·Certbot·갱신 스케줄러 실행 |
| 권한 Primary DNS | `192.0.2.53`, Ubuntu/Debian의 BIND9 | `example.com` 응답과 제한된 TXT 업데이트 |
| 앱의 공인 주소 | `203.0.113.10` | 브라우저가 접근할 공유기·서버 주소 |
| 앱 도메인 | `deciflow.example.com` | 인증서 이름과 공개 DNS 레코드 |
| 공개 출처 | `https://deciflow.example.com:4443` | 브라우저 URL과 Google OAuth 등록값 |

예시의 도메인·문서용 IP·저장소 경로·서비스 이름을 **모두** 실제 환경에 맞게
바꾸세요. 지원 중인 OS·패키지를 사용하며 특정 Certbot·BIND 버전은 프로젝트의
요구사항이 아닙니다. 호스트 명령에는 `sudo`를 사용합니다. TSIG 인증정보와 개인 키는
Git에 저장하지 마세요. 예시에는 실제 비밀값이 포함되어 있지 않습니다.

## 1. 공개 DNS와 접근 경로 준비

DNS 관리 호스트에서 `deciflow.example.com`의 A 레코드를 앱의 공인 IPv4 주소로
등록합니다. AAAA는 IPv6 라우팅·방화벽도 서비스에 연결될 때만 등록하세요.
기존 Zone의 위임·SOA·NS·Secondary·Zone 전송 설정은 유지합니다.

공개 DNS를 사용하는 컴퓨터에서 확인합니다.

```bash
dig NS example.com +short
dig A deciflow.example.com +short
dig AAAA deciflow.example.com +short
```

| 통신 | 필요한 경로 |
| --- | --- |
| 브라우저 → DeciFlow | 외부 TCP 4443 → Docker 호스트 TCP 4443 → OAuth2-Proxy 컨테이너 TCP 4443 |
| Certbot → Primary DNS | TSIG 인증 업데이트를 위한 TCP/UDP 53 |
| ACME 검증 → 권한 DNS | TCP/UDP 53의 공개 DNS 질의 |
| Certbot → Let's Encrypt | 외부로 나가는 TCP 443 HTTPS |

NAT 환경에서는 외부 TCP 4443을 Docker 호스트 TCP 4443으로 전달하고 호스트·Windows
방화벽도 확인하세요. UI 내부 4000 포트는 공개하지 않습니다. DNS-01 발급에는
외부에서 들어오는 웹 포트 80/443이나 실행 중인 OAuth2-Proxy가 필요하지 않습니다.
인증서 발급 성공만으로 브라우저의 4443 접속이 보장되지는 않습니다.
[Let's Encrypt 검증 방식](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge)을 참고하세요.

## 2. BIND9 업데이트 권한 제한

**Primary DNS 호스트**에 배포판의 BIND 도구로 `tsig-keygen`·`named-checkconf`·
`rndc`·`nsupdate`·`dig`를 준비합니다. 아래는 Debian/Ubuntu 경로와 `bind` 그룹을
사용하므로 다른 배포판은 조정하세요. Primary는 위임된 `example.com` Zone을
이미 제공하고 있어야 합니다.

신규 설치에서는 키를 화면에 출력하지 않고 비공개 TSIG 파일을 생성합니다.
전용 키가 이미 있다면 덮어쓰지 말고 해당 키를 재사용하세요.

```bash
sudo sh -c 'umask 077; tsig-keygen -a hmac-sha256 deciflow-acme. > /etc/bind/deciflow-acme.key'
sudo chown root:bind /etc/bind/deciflow-acme.key
sudo chmod 640 /etc/bind/deciflow-acme.key
```

기존 BIND 설정에 다음 include를 추가합니다.

```text
include "/etc/bind/deciflow-acme.key";
```

기존 `zone "example.com"` 블록 안에서 검증용 TXT 이름에만 권한을 부여합니다.

```text
update-policy {
    grant deciflow-acme. name _acme-challenge.deciflow.example.com. TXT;
};
```

Zone 전체 설정을 덮어쓰거나 `allow-update`와 `update-policy`를 함께 사용하지
마세요. 기존 정책이 있다면 해당 정책에 규칙을 통합한 뒤 실행합니다.

```bash
sudo named-checkconf
sudo rndc reconfig
sudo rndc zonestatus example.com
```

동적 업데이트가 활성화됐는지 확인합니다. BIND는 Zone 파일에 쓰고 같은 디렉터리에
`.jnl` 저널을 만들 수 있어야 합니다. 배포판이 허용한 쓰기 가능한 Zone 경로와
BIND 서비스 계정에 맞는 권한을 사용하세요.

사용자 지정 Zone 경로를 AppArmor가 차단하면 활성 BIND 프로파일에 포함되는
로컬 override에 필요한 경로만 허용합니다. `/etc/bind/zones` 경로의 예시입니다.

```text
/etc/bind/zones/ rw,
/etc/bind/zones/db.example.com rw,
/etc/bind/zones/db.example.com.jnl rwk,
```

경로를 조정한 뒤 프로파일을 다시 읽히며 AppArmor를 비활성화하지 않습니다.
SELinux 호스트에서는 AppArmor 규칙 대신 배포판의 BIND 레이블·정책을 적용하세요.

```bash
sudo apparmor_parser -r /etc/apparmor.d/usr.sbin.named
sudo journalctl -u bind9 -n 50 --no-pager
sudo journalctl -k -n 100 --no-pager
```

정책·쓰기 경로는 [RFC2136 플러그인 안내](https://certbot-dns-rfc2136.readthedocs.io/en/stable/#sample-bind-configuration)와
[BIND 설정 참조](https://bind9.readthedocs.io/en/stable/reference.html)를 참고하세요.

## 3. Certbot 준비와 DNS 업데이트 확인

**DeciFlow·Certbot 호스트**에서 배포판이 지원하는 방식으로 Certbot과 RFC2136
플러그인을 설치합니다. 활성 저장소에 아래 패키지가 있는 RPM 계열의 예시입니다.

```bash
sudo dnf install certbot python3-certbot-dns-rfc2136
certbot --version
certbot plugins
```

패키지가 없다면 OS에 맞는 [Certbot 설치 안내](https://certbot.eff.org/instructions)에
따라 동일한 환경에 DNS 플러그인도 설치하고 `dns-rfc2136` 표시를 확인하세요.
`nsupdate`·`dig`를 위한 BIND 클라이언트 도구도 설치합니다.

TSIG 키 파일을 이 호스트의 `/etc/letsencrypt/deciflow-acme.key`로 안전하게 복사하고
저장소에는 두지 않습니다. root만 접근하도록 제한합니다.

```bash
sudo chown root:root /etc/letsencrypt/deciflow-acme.key
sudo chmod 600 /etc/letsencrypt/deciflow-acme.key
sudo nsupdate -k /etc/letsencrypt/deciflow-acme.key
```

`nsupdate` 프롬프트에서 입력합니다.

```text
server 192.0.2.53
zone example.com.
update add _acme-challenge.deciflow.example.com. 60 TXT "deciflow-dns-test"
send
quit
```

Primary와 공개 DNS에서 모두 조회합니다. Secondary가 있으면 각각 확인하세요.

```bash
dig @192.0.2.53 TXT _acme-challenge.deciflow.example.com +short
dig TXT _acme-challenge.deciflow.example.com +short
```

전파 후 양쪽에 테스트 값이 보여야 합니다. `nsupdate`를 다시 실행해 이 테스트
레코드만 삭제합니다.

```text
server 192.0.2.53
zone example.com.
update delete _acme-challenge.deciflow.example.com. TXT "deciflow-dns-test"
send
quit
```

Certbot 호스트에 `/etc/letsencrypt/dns-rfc2136.ini`를 작성합니다.

```ini
dns_rfc2136_server = 192.0.2.53
dns_rfc2136_port = 53
dns_rfc2136_name = deciflow-acme.
dns_rfc2136_secret = REPLACE_WITH_GENERATED_TSIG_SECRET
dns_rfc2136_algorithm = HMAC-SHA256
```

BIND의 큰따옴표·세미콜론을 제외한 동일한 실제 비밀값을 넣으세요.
인증정보 파일은 root 소유·600 권한으로 제한합니다.

```bash
sudo chown root:root /etc/letsencrypt/dns-rfc2136.ini
sudo chmod 600 /etc/letsencrypt/dns-rfc2136.ini
```

## 4. 인증서 발급과 배포

**Certbot 호스트**에서 발급을 요청하고 최초 계정·약관 안내를 완료합니다.
`--cert-name`은 아래 명령에서 사용할 인증서 계보(lineage) 이름을 고정합니다.

```bash
sudo certbot certonly \
  --dns-rfc2136 \
  --dns-rfc2136-credentials /etc/letsencrypt/dns-rfc2136.ini \
  --dns-rfc2136-propagation-seconds 60 \
  --cert-name deciflow.example.com \
  -d deciflow.example.com
sudo certbot certificates
```

Certbot이 검증 TXT를 생성·삭제합니다. 권한 DNS 전파가 느리면 대기 시간을 늘리세요.
이 계보의 `/etc/letsencrypt/live/deciflow.example.com/` 아래 `fullchain.pem`은
공개 인증서 체인, `privkey.pem`은 개인 키입니다. 만료일을 스크립트에 고정하지 마세요.

Certbot 심볼릭 링크를 끊어진 상태로 복사하지 말고 저장소에 실제 내용을 배포합니다.

```bash
cd /opt/deciflow
sudo install -d -m 755 oauth2-proxy/tls
sudo install -m 644 /etc/letsencrypt/live/deciflow.example.com/fullchain.pem oauth2-proxy/tls/fullchain.pem
sudo install -o 65532 -m 600 /etc/letsencrypt/live/deciflow.example.com/privkey.pem oauth2-proxy/tls/privkey.pem
```

65532는 프로젝트가 고정한 OAuth2-Proxy 이미지의 실행 UID입니다. TLS 디렉터리는 Git과
이미지 빌드에서 제외됩니다. Certbot의 원본이 갱신돼도 이 복사본은 자동으로 바뀌지 않습니다.

[Google 로그인 설정](authentication.ko.md)을 이어서 진행하세요.
`OAUTH2_PROXY_PUBLIC_URL=https://deciflow.example.com:4443`을 지정하고 포트까지 정확히
일치하는 Google 콜백·클라이언트 인증정보·허용 목록을 준비한 뒤 Docker 호스트에서 실행합니다.

```bash
docker compose config --quiet
docker compose up -d
curl -I https://deciflow.example.com:4443/
curl -i https://deciflow.example.com:4443/api/status
```

인증서 검증이 성공해야 합니다. 미인증 메인 요청에는 로그인 화면과 함께 403이
표시될 수 있고 `/api/status`는 401이어야 합니다. 외부 네트워크에서도 확인하세요.
LAN 내부 테스트만으로 NAT 동작을 확인할 수는 없습니다.

## 5. 자동 갱신과 OAuth2-Proxy 반영

**Certbot 호스트**에서 갱신을 검증한 뒤 스케줄을 활성화합니다.

```bash
sudo certbot renew --cert-name deciflow.example.com --dry-run
systemctl list-unit-files '*certbot*.timer'
```

설치한 패키지가 제공하는 타이머를 사용합니다. 아래는 RPM 패키지에
`certbot-renew.timer`가 있을 때의 예시입니다. `certbot.timer`를 제공하는 패키지는
해당 이름과 연결된 서비스로 바꾸세요. 스케줄러는 하나만 사용합니다.

```bash
sudo systemctl enable --now certbot-renew.timer
systemctl status certbot-renew.timer --no-pager
systemctl list-timers certbot-renew.timer
systemctl cat certbot-renew.service
```

서비스가 비대화형으로 `certbot renew`를 실행하는지 확인합니다. 타이머가 없다면
설치한 Certbot 방식에서 지원하는 갱신 스케줄러를 구성하세요.

Certbot과 Docker가 같은 호스트라면 root 소유 실행 파일
`/etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh`를 아래 내용으로 작성합니다.
저장소 경로·인증서 계보를 먼저 조정하세요. 스케줄러 계정이 Docker에 접근할 수 있고,
PATH에서 `docker`를 찾으며 올바른 Docker context를 사용해야 합니다.

```sh
#!/bin/sh
set -eu

if [ "${RENEWED_LINEAGE:-}" != "/etc/letsencrypt/live/deciflow.example.com" ]; then
    exit 0
fi

cd /opt/deciflow
install -d -m 755 oauth2-proxy/tls
install -m 644 "$RENEWED_LINEAGE/fullchain.pem" oauth2-proxy/tls/fullchain.pem
install -o 65532 -m 600 "$RENEWED_LINEAGE/privkey.pem" oauth2-proxy/tls/privkey.pem
docker compose up -d --no-deps --force-recreate oauth2-proxy
```

```bash
sudo chown root:root /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
sudo chmod 700 /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
sudo sh -n /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
sudo env RENEWED_LINEAGE=/etc/letsencrypt/live/deciflow.example.com /etc/letsencrypt/renewal-hooks/deploy/deciflow-op.sh
```

마지막 명령은 현재 인증서로 배포를 테스트하며 **OAuth2-Proxy를 재생성**합니다.
브라우저 스트림이 잠시 끊기지만 UI·Laya·백그라운드 Task는 계속 실행됩니다.
계보 검사는 다른 인증서에 대한 실행을 건너뜁니다. Certbot은 갱신 성공 후 deploy hook을
실행하며 일반 `--dry-run`만으로 이 hook이 테스트되지는 않습니다.
ACME staging 인증서를 운영 서비스에 배포하지 마세요.
[Certbot 갱신·hook 안내](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates)를 참고하세요.

Certbot이 다른 호스트에 있다면 안전한 인증서 전송과 원격 OAuth2-Proxy 재생성 방식으로
배포 hook을 조정하세요. 위 스크립트는 Certbot·Docker가 같은 호스트인 경우입니다.

## 6. 점검과 문제 해결

```bash
sudo certbot certificates
sudo journalctl -u certbot-renew.service -n 100 --no-pager
sudo tail -n 100 /var/log/letsencrypt/letsencrypt.log
openssl s_client -connect deciflow.example.com:4443 -servername deciflow.example.com -verify_hostname deciflow.example.com -verify_return_error </dev/null
```

| 증상 | 확인할 사항 |
| --- | --- |
| DNS 주소가 잘못 조회됨 | 공개 A/AAAA·위임·모든 권한 DNS 응답 |
| 업데이트 `REFUSED` / `NOTAUTH` | TSIG 이름·비밀값·알고리즘·Zone·정확한 TXT 권한 |
| `SERVFAIL` / 저널 권한 오류 | BIND 로그·Zone 파일과 디렉터리 권한·AppArmor/SELinux 거부 |
| Certbot이 플러그인을 찾지 못함 | 실제 실행되는 Certbot과 같은 환경에 플러그인이 설치됐는지 |
| Primary에서만 TXT가 조회됨 | Secondary 전송·알림·전파 대기 시간 |
| 발급 성공 후 브라우저 접속 실패 | NAT 4443/TCP·호스트 방화벽·WSL 라우팅·OAuth2-Proxy 실행 상태 |
| OAuth2-Proxy가 개인 키를 읽지 못함 | 배포한 키 UID 65532·권한 600·부모 디렉터리 접근 권한 |
| 브라우저에 이전 인증서가 표시됨 | hook의 갱신 파일 복사·OAuth2-Proxy 재생성 여부와 로그 |
| 타이머 비활성·다음 실행 없음 | 실제 unit 이름·활성 상태·스케줄러 로그 |
| Google `redirect_uri_mismatch` | :4443까지 일치하는 HTTPS 출처·콜백. 인증 안내 참고 |

WSL2의 systemd 타이머에는 systemd 활성화가 필요합니다. WSL 배포판이 중지되거나
Windows가 종료되면 예약 갱신을 실행할 수 없으므로 가동 시간을 확보하거나 Windows
예약 작업으로 WSL을 실행하는 방식을 마련하세요. hook 실행 시 Docker 엔진·context도
사용 가능해야 합니다. [WSL systemd 설정](https://learn.microsoft.com/en-us/windows/wsl/systemd)을 참고하세요.

완료 기준은 올바른 공개 DNS, 발급·갱신 dry-run 성공, 다음 갱신 예약,
배포 hook 성공, 외부 HTTPS에서 배포한 인증서와 로그인·API 접근 제어 확인입니다.
