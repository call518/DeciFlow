# Optional Google Sign-In with Docker

[한국어](authentication.ko.md) | [Installation](../INSTALL.md) | [Documentation](README.md)

Start DeciFlow using [INSTALL](../INSTALL.md) first. Add **OAuth2-Proxy in Docker**
only when HTTPS/Google sign-in is needed. All approved users share DeciFlow data
and administrative capabilities. Laya remains independent.

Choose the section matching your DeciFlow installation after common preparation:
[PyPI](#pypi) · [Docker Compose](#docker) · [Direct process](#source).

| Method | `.env` and Proxy Directory Root |
| --- | --- |
| PyPI | `~/.config/deciflow` |
| Docker Compose / Direct process | `<checkout>` |

Native CLI installations use `OAUTH2_PROXY_MANAGED=false` to keep the proxy in
Docker while retaining the signed-in account UI.

<a id="certificates"></a>

## Common Preparation

Assumes a domain reachable by browsers and TCP 4443 allowed. Set the domain once
in this setup shell. `example.com` is documentation-only; use your actual domain.

```bash
export DECIFLOW_DOMAIN="deciflow.example.com"
export DECIFLOW_HTTPS_URL="https://${DECIFLOW_DOMAIN}:4443"
export DECIFLOW_CERT_DIR="$HOME/.config/deciflow-certificates/${DECIFLOW_DOMAIN}"
```

### Certificate: Choose One

**Run Option 1 OR Option 2. Do not run both.**

---

#### Option 1: Let's Encrypt Certificate (Recommended)

 public DNS must reach this host and TCP 80 must
be available during HTTP-01 issuance/renewal. Python 3.12 and sudo are assumed.
Complete Certbot's email/terms prompts.

```bash
sudo python3.12 -m venv /opt/deciflow-certbot
sudo /opt/deciflow-certbot/bin/python -m pip install certbot
sudo /opt/deciflow-certbot/bin/certbot certonly --standalone \
  --cert-name "$DECIFLOW_DOMAIN" -d "$DECIFLOW_DOMAIN"
```

<a id="certificate-files"></a>

Copy actual file contents (also use this step after [DNS-01](dns-tls.md#dns01) issuance):

```bash
install -d -m 700 "$DECIFLOW_CERT_DIR"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 644 \
  "/etc/letsencrypt/live/$DECIFLOW_DOMAIN/fullchain.pem" "$DECIFLOW_CERT_DIR/fullchain.pem"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 600 \
  "/etc/letsencrypt/live/$DECIFLOW_DOMAIN/privkey.pem" "$DECIFLOW_CERT_DIR/privkey.pem"
```

→ **[Certificate ready: skip the other option and go to Google settings](#google-settings)**

---

#### Option 2: Self-Signed Certificate

 if option 1 is unavailable, skip Certbot and create the same
files below. The browser will show a certificate warning; continue through it.

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

→ **[Certificate ready: skip the other option and go to Google settings](#google-settings)**

---

<a id="google-settings"></a>

### Google and `.env`

In [Google Cloud](https://console.cloud.google.com/), configure the consent screen,
create an OAuth **Web application** client, and register the printed values.
Add intended accounts as test users if the app is in Testing mode.

```bash
printf 'JavaScript origin: %s\n' "$DECIFLOW_HTTPS_URL"
printf 'Redirect URI: %s/oauth2/callback\n' "$DECIFLOW_HTTPS_URL"
openssl rand -base64 32
```

Set `DECIFLOW_BIND_HOST` to `127.0.0.1` to block direct HTTP authentication bypass.
Compose removes the host-published UI port while retaining container-network access.

Use the last output as the cookie key. In your method's **existing `.env`**, apply
the following output, replacing the three placeholders. Save actual URL values,
not shell variable references.

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

## PyPI: uv tool or pip

Use the initialized package settings and apply the common `.env` values.
Activate the pip environment when applicable.

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

Edit `allowed-emails.txt` to contain approved Google emails, one per line;
remove the example address. Keep `email_domains = []` in `oauth2-proxy.cfg`.

Restart DeciFlow first. Protected native mode enforces loopback even if
`0.0.0.0` is accidentally left in the setting. Config testing does not require a host proxy binary
or an unused HTTPS port when `OAUTH2_PROXY_MANAGED=false`.

```bash
deciflow stop
deciflow config test
deciflow start --daemon
```

Then start the Docker proxy. Linux host networking reaches DeciFlow's loopback
without exposing port 4000; the proxy reads files as the DeciFlow account.

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

Continue with [verification](#verify).

<a id="docker"></a>

## Docker Compose

From the checkout root, apply the common values to its `.env`:

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

Edit `allowed-emails.txt` to contain approved Google emails, one per line;
remove the example address. Keep `email_domains = []` in `oauth2-proxy.cfg`.

The Compose proxy uses image UID 65532. Set permissions and recreate services:

```bash
sudo chown 65532 oauth2-proxy/tls/privkey.pem
chmod 644 oauth2-proxy/oauth2-proxy.cfg oauth2-proxy/allowed-emails.txt
sudo chcon -Rt container_file_t oauth2-proxy
docker compose config --quiet
docker compose up -d --remove-orphans --force-recreate ui oauth2-proxy
```

Compose removes the public UI port and exposes HTTPS on 4443.

Continue with [verification](#verify).

<a id="source"></a>

## Direct Process

From the checkout root, apply the common values to its `.env`:

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

Edit `allowed-emails.txt` to contain approved Google emails, one per line;
remove the example address. Keep `email_domains = []` in `oauth2-proxy.cfg`.

Restart DeciFlow first. Protected native mode enforces loopback even if
`0.0.0.0` is accidentally left in the setting. Config testing does not require a host proxy binary
or an unused HTTPS port when `OAUTH2_PROXY_MANAGED=false`.

```bash
uv run deciflow stop --config-dir "$PWD"
uv run deciflow config test --config-dir "$PWD"
uv run deciflow start --daemon --config-dir "$PWD"
```

Then start the Docker proxy. Linux host networking reaches DeciFlow's loopback
without exposing port 4000; the proxy reads files as the DeciFlow account.

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

Continue with [verification](#verify).

<a id="verify"></a>

## Verify and Operate

Without cookies, the API must return **401** and certificate validation must pass.
For a self-signed certificate, add `--cacert "$DECIFLOW_CERT_DIR/fullchain.pem"`.

```bash
curl --connect-timeout 5 --max-time 15 -i "${DECIFLOW_HTTPS_URL}/api/status"
```

Open the printed HTTPS URL in a private browser, sign in with an approved
account, confirm the email badge, and repeat [the demo](../INSTALL.md#demo).
An unlisted account must be denied. Sign Out is in the account menu.

| Deployment | Logs | Apply Proxy/Certificate Changes |
| --- | --- | --- |
| Package / Direct process | `docker logs --tail=100 deciflow-oauth2-proxy` | `docker rm -f deciflow-oauth2-proxy`, then rerun its `docker run` command |
| Compose | `docker compose logs --tail=100 oauth2-proxy` | `docker compose up -d --no-deps --force-recreate oauth2-proxy` |

The native CLI no longer stops the separately operated proxy container; manage it
with Docker. If the application port changes, update the standalone upstream too.
Stopping a proxy leaves the native app on loopback, not public HTTP.

<a id="renewal"></a>

## Certificate Renewal

For Let's Encrypt, test `sudo /opt/deciflow-certbot/bin/certbot renew --dry-run`
and enable your Certbot renewal scheduler. After renewal, repeat the certificate
preparation copy and your method's TLS copy, then recreate the proxy using the
commands above. For self-signed certificates, regenerate before expiry instead.
[DNS-01 operations](dns-tls.md#dns01-renewal) covers RFC2136 automation.

<a id="proxy-config"></a>

## Configuration Fields

Container paths start at `/etc/oauth2-proxy/`; the procedures above mount that directory.

| Setting | Default and Purpose |
| --- | --- |
| `provider` | `"google"`: Google sign-in provider. |
| `https_address` | `"0.0.0.0:4443"`: HTTPS listener on all IPv4 interfaces, port 4443. This is a bind address, not the public domain. |
| `tls_cert_file`, `tls_key_file` | `/etc/oauth2-proxy/tls/fullchain.pem` and `/etc/oauth2-proxy/tls/privkey.pem`: paths inside the container. |
| `authenticated_emails_file` | `/etc/oauth2-proxy/allowed-emails.txt`: email file inside the container. |
| `email_domains` | `[]`: keep the explicit email allow-list policy. Native configuration validation rejects a nonempty value. |
| `reverse_proxy` | `false`: shipped setup terminates TLS at OAuth2-Proxy directly. |
| `pass_access_token`, `pass_authorization_header`, `pass_basic_auth`, `pass_user_headers` | `false`: disable these credential/user-header forwarding options to DeciFlow. |
| `cookie_name`, `cookie_path` | `"__Host-deciflow_session"`, `"/"`: host-scoped session cookie. |
| `cookie_secure`, `cookie_httponly`, `cookie_samesite` | `true`, `true`, `"lax"`: HTTPS-only cookie, inaccessible to JavaScript, with SameSite protection. |
| `cookie_refresh`, `cookie_expire` | `"1h"`, `"8h"`: refresh interval and session lifetime. |
| `code_challenge_method` | `"S256"`: OAuth PKCE challenge method. |
| `api_routes` | `["^/api(?:/|$)"]`: unauthenticated API requests receive 401 instead of a login-page redirect. |
| `flush_interval`, `upstream_timeout` | `"100ms"`, `"0s"`: streaming flush interval and no upstream response timeout. |

<a id="api-origin-protection"></a>

## API Origin Protection

DeciFlow checks the browser's `Origin` header for protected API requests,
including Source/Task management, settings, and file access. This uses the
[OWASP Origin-checking technique](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#using-standard-headers-to-verify-origin);
`DECIFLOW_CSRF_TRUSTED_ORIGINS` is a DeciFlow setting, not an HTTP standard header.
No CSRF tokens are issued or validated.

Without OAuth2-Proxy, the origin must match the request scheme and Host
(including the port). A browser on another computer can use the server IP or
domain without extra configuration. With OAuth2-Proxy enabled,
`OAUTH2_PROXY_PUBLIC_URL` supplies the expected external HTTPS origin even when
the backend connection is HTTP. Forwarded headers are not read by this check;
configure Uvicorn to trust only the actual proxy when enabling forwarded headers.

Leave `DECIFLOW_CSRF_TRUSTED_ORIGINS` empty normally. To explicitly allow additional
UI origins, list complete origins separated by commas, without trailing slashes:

```dotenv
DECIFLOW_CSRF_TRUSTED_ORIGINS=https://admin.example.com,https://console.example.com
```

Each entry grants access to protected API operations; allow only origins you
control. HTTPS subdomain wildcards are supported, but exact origins are preferable.
Missing, `null`, or unrecognized origins receive HTTP 403. Command-line API callers
must also supply an accepted Origin. An allow-list entry does not enable CORS.

This check mitigates browser cross-site requests; it does not authenticate callers.
A direct HTTP client can forge Origin. Use OAuth2-Proxy for authentication and keep
the backend inaccessible to untrusted clients. In HTTP mode, Host is supplied by
the client; this check alone does not prevent DNS rebinding or direct API access.
