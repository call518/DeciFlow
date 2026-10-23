# Google Sign-In and Email Allow List

[한국어](authentication.ko.md) | [Project README](../README.md)

DeciFlow reads sources, calls the **Laya server** (self-hosted inference) or the
**Jev service** (paid hosted inference), and serves the web UI and API.
**OAuth2-Proxy** protects incoming browser/API traffic with Google sign-in and
an administrator-maintained email allow list. It directly handles HTTPS and
forwards authorized requests to DeciFlow; Nginx is not required.
Source access, Laya/Jev calls, and Action delivery keep their existing authentication.
All admitted users share DeciFlow's data and administrative capabilities; this
does not add per-user storage or roles.

This guide uses **Docker Compose**: run commands from the checkout and edit
`<checkout>/.env`, mounted as `/app/.env` inside the UI container. OAuth2-Proxy
files are in `<checkout>/oauth2-proxy/`. For installation without Docker, choose
the recommended [uv tool guide](tool-install.md#optional-google-sign-in) or the
[Git checkout native guide](native.md). Their configuration paths differ; see
[environment file locations](configuration.md#environment-file-locations).

Set `OAUTH2_PROXY_ENABLED=true` in `.env` to use this guide. The default `false`
provides an HTTP demo at `http://localhost:4000` without OAuth or certificate files.
With OAuth2-Proxy enabled, only HTTPS port 4443 is published; the UI has no host port.
After changing the mode, run `docker compose up -d --remove-orphans`. This recreates
the UI port bindings and removes an unused OAuth2-Proxy container without deleting data.
Do not use `restart` alone to switch modes. Invalid enabled-mode settings stop
startup; there is no automatic fallback to HTTP.

The entry point remains `docker-compose.yml`. It automatically selects the files
in `compose/` from this setting; do not pass those files with `-f`.
Docker Compose 2.20.0+ is required for this include mechanism.

## Prerequisites

- Docker with the Compose plugin, and the DeciFlow `.env`.
- A domain pointing to the DeciFlow host, a trusted TLS certificate for that domain,
  and TCP 4443 reachable on that host. DNS registration alone does not enable HTTPS.
- A Google Cloud project where you can register an OAuth **Web application**.

The examples use `https://deciflow.example.com:4443`; replace it with your HTTPS origin.
Certificate issuance/renewal and Google account setup are performed by the operator;
the Compose configuration does not create them.
For domain records, certificate issuance, renewal, and OAuth2-Proxy deployment, follow
[DNS and TLS preparation](dns-tls.md) before continuing below.

## 1. Register Google Sign-In

In the [Google Cloud console](https://console.cloud.google.com/), configure the OAuth
consent screen and create an OAuth client of type **Web application**:

- Authorized JavaScript origin: `https://deciflow.example.com:4443`
- Authorized redirect URI: `https://deciflow.example.com:4443/oauth2/callback`

If the consent screen is in Testing mode, add your users as Google test users too.
Google's test-user list and DeciFlow's allow list are separate checks.
Keep the client ID and client secret for the next step. Do not send secrets in chat.
See the [OAuth2-Proxy Google guide](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/google/).

## 2. Prepare Local Settings

Run from the DeciFlow repository root on the Docker host:

```bash
test -f .env || cp .env.example .env
test -f oauth2-proxy/allowed-emails.txt || cp oauth2-proxy/allowed-emails.example.txt oauth2-proxy/allowed-emails.txt
mkdir -p oauth2-proxy/tls
chmod 600 .env
openssl rand -base64 32
```

Edit `.env`: set `OAUTH2_PROXY_ENABLED=true` and `OAUTH2_PROXY_PUBLIC_URL` to your HTTPS origin without a path
or trailing slash, fill in `OAUTH2_PROXY_CLIENT_ID` and `OAUTH2_PROXY_CLIENT_SECRET`,
and place the generated value in `OAUTH2_PROXY_COOKIE_SECRET`.

Edit `oauth2-proxy/allowed-emails.txt` to contain **only approved Google account
email addresses, one per line**. Replace the example address. Do not use a domain
wildcard or add `email_domains` to the proxy configuration.

The email file uses exact addresses, not regular expressions or `*@domain` patterns.
Lines starting with `#` are comments; put `#` in column one and do not use inline
comments. Google sign-in accepts Gmail, Workspace, and other Google accounts.
`email_domains` is a setting in `oauth2-proxy/oauth2-proxy.cfg`, not a file: adding
a domain allows all Google accounts in that domain in addition to listed emails.
The default empty list keeps admission restricted to the email file.

Place actual certificate files, rather than symlinks to files outside the mounted
directory, at `oauth2-proxy/tls/fullchain.pem` and `oauth2-proxy/tls/privkey.pem`.
The pinned image runs as UID 65532. Set private-key ownership and permissions:

```bash
sudo chown 65532 oauth2-proxy/tls/privkey.pem
sudo chmod 600 oauth2-proxy/tls/privkey.pem
```

Keep the public certificate and allow list readable by the container. After certificate
renewal, replace the files, reapply key permissions, and recreate the proxy.
The local settings, allow list, and TLS directory are excluded from Git and image builds.

## 3. Validate and Start

Validate without printing the rendered configuration, which contains secrets:

```bash
docker compose config --quiet
```

Select CPU, CUDA, or external inference through `COMPOSE_PROFILES` in `.env`, then start:

```bash
docker compose up -d
```

Open your **HTTPS** origin. OAuth2-Proxy publishes port 4443; the DeciFlow UI port
is removed from the host's published ports. Do not run another native DeciFlow
process or a separate unprotected UI container on a publicly reachable port.
Laya's existing port and API-key configuration are unchanged.

OAuth2-Proxy v7.15.5 is pinned. It uses secure, HTTP-only host cookies, Google
session refresh every hour, and an eight-hour session lifetime. API requests
without a valid session receive **401**; reload the page to sign in again.
Streaming uses a 100 ms flush interval and no upstream response timeout, allowing
long-running result streams. A session expiring does not cancel background Tasks;
an already-open stream is not continuously reauthorized.

## 4. Verify Access

Before exposing the service to users, verify:

1. An incognito browser must sign in before viewing Main or a saved run URL.
2. An approved account can load sources/settings and run a Task; an unlisted
   account is denied. Being a Google test user alone must not grant access.
3. Without cookies, `curl -i https://deciflow.example.com:4443/api/status` returns 401.
   Forged user/email headers must not grant access.
4. The host's former DeciFlow UI port is unreachable from another machine.
5. Result events arrive during a run, including runs lasting over 30 seconds.
   Check Laya and Jev separately if both are configured; Jev incurs API charges.
6. Sign out at `https://deciflow.example.com:4443/oauth2/sign_out`, then reload Main;
   API access must require sign-in again. This clears the proxy session, not the
   Google account session.

The automated local smoke test downloads OAuth2-Proxy v7.15.5 for Linux/macOS
amd64/arm64, verifies its pinned official SHA-256 digest, and caches the archive in
`~/.cache/deciflow/test-tools/` outside the repository. The executable and test TLS
files use temporary pytest storage. OpenSSL and GitHub access are required on the
first run; a verified cache avoids repeat downloads. Download or checksum errors
fail the test instead of silently skipping it.

```bash
uv run pytest -q tests/test_oauth2_proxy.py
```

For an offline environment or an existing executable, supply its absolute path:

```bash
OAUTH2_PROXY_BINARY=/path/to/oauth2-proxy uv run pytest -q tests/test_oauth2_proxy.py
```

The smoke test uses disposable local settings and a self-signed test certificate;
it does not contact Google or use your credentials. A test-only public route checks
stream forwarding. Real Google admission/rejection and production TLS still require
the manual checks above.

## Operations

For an allow-list edit, the proxy watches for file changes, but editors that replace
the bind-mounted file can leave the container reading the old file. Recreate only
the proxy to reliably apply changes. Use the same command after updating
`oauth2-proxy/oauth2-proxy.cfg`, Google credentials, the cookie key, or TLS files:

```bash
docker compose up -d --no-deps --force-recreate oauth2-proxy
```

If `OAUTH2_PROXY_PUBLIC_URL` changes, update both authorized URLs in Google, including
the port, then run `docker compose up -d ui oauth2-proxy` to update the callback and
UI trusted origin. `redirect_uri_mismatch` means the requested callback does not
exactly match a URI registered for that Google client.

Keep `.env` in the same setting order and comment layout as `.env.example` while
preserving your values. Do not print `docker compose config` without `--quiet`,
because it renders secrets.

For urgent session revocation, replace the cookie secret too and recreate the proxy;
this invalidates all existing proxy cookies. Close existing connections if immediate
disconnection is required. Restarting the proxy disconnects streams but does not stop Tasks.

To stop web access while keeping background Tasks running:

```bash
docker compose stop oauth2-proxy
```

The UI remains internal; stopping the proxy does not enable unauthenticated access.
