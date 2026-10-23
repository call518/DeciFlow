# Git Checkout Native Installation

[한국어](native.ko.md) | [Project README](../README.md) | [Documentation](README.md)

Run DeciFlow locally, open the browser, and classify a sample log. Docker, a domain,
and a certificate are not required for this local workflow.
This is the third recommended method, after [PyPI / uv tool](tool-install.md)
and [Docker Compose](../README.md#alternative-installation-docker--laya-cpu). Choose one method;
this guide runs Git checkout scripts directly.

**DeciFlow** reads sources and serves the UI/API. The **Laya server** runs inference
locally or remotely; **Jev** is an alternative paid hosted inference service.
**OAuth2-Proxy** can protect browser access, but is a separate native process.
Choose native execution instead of the Compose deployment for the same installation.

## Environment File

Both `server.py` and the local `laya_server.py` adapter read `<checkout>/.env`,
where `<checkout>` is the cloned repository root. They do not read
`~/.config/deciflow/.env`. Run the documented commands from the checkout; source
script paths are not selected by the installed command's `--config-dir` option.
See [environment file locations](configuration.md#environment-file-locations).

## Quick Start: Local CPU

Requires Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.11+
compatible with the locked dependencies, and download access for dependencies and
the model. Linux/WSL2 is the example environment; no GPU is required.
The first Laya model download/loading can take several minutes. If a Laya server
is already available, use [an existing engine](#use-an-existing-engine) instead.

### 1. Prepare the Repository

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
test -f .env || cp .env.example .env
uv sync --frozen --extra laya
```

### 2. Configure Local Execution

Edit the existing entries in `.env`; preserve other values and the template's order
and comments:

```dotenv
OAUTH2_PROXY_ENABLED=false
DECIFLOW_BIND_HOST=127.0.0.1
DECISION_ENGINE=laya
PORT=4000
DECIFLOW_DATA_DIR=./data
DECIFLOW_LOG_DIR=./logs
DECIFLOW_CSRF_TRUSTED_ORIGINS=
LAYA_API_URL=http://127.0.0.1:8000/v1/systemone
LAYA_MODEL=multilingual
LAYA_MAX_TOKENS=
LAYA_HEAD_TOKENS=512
```

The repository's local Laya adapter reads the same `.env` API key as DeciFlow.
For another Laya server, set `LAYA_API_KEY` to its matching key. The Compose hostname
`laya` and `/host-logs` mounts are unavailable outside Docker.
`COMPOSE_PROFILES` is ignored by these native commands. OAuth values may remain
blank when `OAUTH2_PROXY_ENABLED=false`. Set `DECIFLOW_BIND_HOST=0.0.0.0` and
add the public browser origin to `DECIFLOW_CSRF_TRUSTED_ORIGINS` for external HTTP
access, then restart DeciFlow. Anyone reaching that port can manage all data.

### 3. Start Laya and DeciFlow

In terminal A, from the repository root:

```bash
uv run --extra laya python laya_server.py
```

This starts the local adapter on `127.0.0.1:8000`, using CPU unless process
environment settings select another device. Wait for model loading to complete.
It checks token budgets and exposes truncation metadata through the Laya API.

In terminal B, from the same repository:

```bash
uv run --extra laya python server.py
```

Both commands use `--extra laya` to keep the same environment. DeciFlow listens on
`127.0.0.1:4000` by default. Keep both terminals open.

### 4. See the First Result

Open **http://127.0.0.1:4000**. No Google login is required in this local workflow.

1. In **Sources**, edit **Sample HTTP access** to point to the actual absolute path
   of `sample-logs/access-100.log` in this repository.
2. In **Tasks**, add a **Batch / Manual** Task using that Source,
   **Sample HTTP access** criteria, **Events/Chunk: 1**, and **Action: None**.
3. Save, enable the Task, and click **Run**. Results appear in Main.

Use an absolute Source path; the Docker-specific `/host-logs/sample-logs/...` path
will not work. The startup-created Elasticsearch Action is not needed for this demo.
Startup may download its Python environment and modules; no Elasticsearch server
is needed when the Task's Action is None. More workflows are in [Usage](usage.md).

### 5. Stop and Restart

Press `Ctrl+C` in terminal B to stop DeciFlow, then in terminal A to stop Laya.
Rerun the same commands to start again. Sources, settings, and run history remain
in `./data`; logs remain in `./logs`. Active runs with checkpoints can recover;
paused runs remain paused. See [Task recovery](tasks.md#recovery-after-a-server-restart).
Restart the relevant native process after changing its environment settings.

## Use an Existing Engine

Choose one of these instead of starting local Laya. The DeciFlow host needs no
local model, GPU, or `laya` extra. Use steps 1–2 above, but install with
`uv sync --frozen` instead of `uv sync --frozen --extra laya`.

| Engine | Set in `.env` |
| --- | --- |
| Existing Laya | `DECISION_ENGINE=laya`, reachable `LAYA_API_URL` including `/v1/systemone`, matching `LAYA_API_KEY` and model |
| Jev | `DECISION_ENGINE=jev`, your `JEV_API_KEY`, and a supported `JEV_MODEL`; API calls incur charges |

For a Laya server on the same host, use `http://127.0.0.1:8000/v1/systemone`.
For a remote server, use its actual reachable URL. There is no automatic fallback
to paid Jev. Keep the writable data/log paths from step 2, then run only:

```bash
uv run python server.py
```

Open the same local UI and follow the sample steps above.

## Optional: Native HTTPS with OAuth2-Proxy

Set `OAUTH2_PROXY_ENABLED=true` to start OAuth2-Proxy automatically with the same
`uv run --extra laya python server.py` command. DeciFlow stays on loopback;
OAuth2-Proxy owns the external HTTPS listener:

```text
Browser → OAuth2-Proxy HTTPS :4443 → DeciFlow HTTP 127.0.0.1:4000 → Laya or Jev
```

1. Install the official [OAuth2-Proxy v7.15.5 binary](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.5)
   for your OS/architecture on PATH and verify the release checksum.
2. Prepare a domain and trusted certificate using [DNS/TLS preparation](dns-tls.md).
   Its Docker deploy hook does not apply to native execution. Put actual certificate
   files in `oauth2-proxy/tls/`; the native process owner must be able to read the
   private key, with mode 600. Docker UID 65532 is not a native ownership rule.
3. Follow [Google registration and the email allow list](authentication.md).
   Fill the client ID, client secret, and cookie key in `.env`, then set:

```dotenv
OAUTH2_PROXY_ENABLED=true
OAUTH2_PROXY_PUBLIC_URL=https://deciflow.example.com:4443
```

Restart DeciFlow using the same terminal B command. With an existing engine,
omit `--extra laya` as above. The launcher supplies native paths, the configured
`PORT`, callback, and trusted origin automatically. Keep OAuth settings and private
files out of Git. Do not publish the internal UI port. Missing settings, an absent
binary, or an OAuth2-Proxy exit stop startup/service; HTTP is never enabled as a fallback.

Open the public HTTPS URL. Verify approved and unapproved accounts and a cookieless
`/api/status` request (401). `Ctrl+C` stops DeciFlow and OAuth2-Proxy together; Laya remains
in terminal A. UI Restart/Reset also cleans up OAuth2-Proxy before restarting DeciFlow.

To switch modes or apply changed credentials, certificates, allow-list or policy,
stop terminal B with `Ctrl+C` and run the same command again after editing files.
For renewal, restart this native deployment using your host service manager;
Docker recreation commands do not manage it. No native service unit is installed.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Data/log permission error | Use `./data` and `./logs`, or other writable native paths |
| Model download/loading is slow | Inspect terminal A; initial loading needs download access and adequate memory |
| Engine cannot be reached | Laya process/readiness, native API URL, and API key; `laya` resolves only in Compose |
| Source not found | Absolute host path rather than `/host-logs/...` |
| Native OAuth2-Proxy returns 403 for UI API calls | Public HTTPS origin in `DECIFLOW_CSRF_TRUSTED_ORIGINS`; restart DeciFlow after editing |
| OAuth2-Proxy cannot read certificates | Native file paths and private-key owner/permissions |
| Port already in use | Stop the other installation or choose free ports consistently |

For HDFS native Sources, the host also needs the Java/Hadoop/libhdfs requirements
described in [Sources](sources.md#hdfs). They are not prerequisites for the local
TEXT sample. More engine settings are in [Configuration](configuration.md).
