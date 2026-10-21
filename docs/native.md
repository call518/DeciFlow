# Run Without Docker

[한국어](native.ko.md) | [Project README](../README.md) | [Documentation](README.md)

Run DeciFlow locally, open the browser, and classify a sample log. Docker, a domain,
and a certificate are not required for this local workflow.

**DeciFlow** reads sources and serves the UI/API. The **Laya server** runs inference
locally or remotely; **Jev** is an alternative paid hosted inference service.
**OAuth2-Proxy (OP)** can protect browser access, but is a separate native process.
Choose native execution instead of the Compose deployment for the same installation.

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
blank for local HTTP execution; setting them does not automatically start OP.

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

## Optional: Native HTTPS with OP

This is a manual two-process setup, not an implemented `.env` mode switch.
DeciFlow stays on loopback; OP owns the external HTTPS listener:

```text
Browser → OP HTTPS :4443 → DeciFlow HTTP 127.0.0.1:4000 → Laya or Jev
```

1. Install the official [OAuth2-Proxy v7.15.5 binary](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.5)
   for your OS/architecture on PATH. Verify the release checksum. No Docker is required.
2. Prepare a domain and trusted certificate using [DNS/TLS preparation](dns-tls.md).
   Use its DNS/issuance instructions; its Docker deploy-hook commands do not apply
   to native OP. Put actual certificate files in `oauth2-proxy/tls/` and make the
   private key readable by the **native OP process owner**, with mode 600. The
   Docker UID 65532 ownership rule is specific to the container; do not change a
   key used by a running Docker deployment to repurpose it for native execution.
3. Follow [Google registration and allow-list setup](authentication.md). Set
   `DECIFLOW_PUBLIC_URL` and the OAuth client/cookie values in `.env`. For the
   example domain, also set:

```dotenv
DECIFLOW_PUBLIC_URL=https://deciflow.example.com:4443
DECIFLOW_CSRF_TRUSTED_ORIGINS=https://deciflow.example.com:4443
```

Keep the private key, allow list, and `.env` outside Git as configured by the project.
Register `https://deciflow.example.com:4443/oauth2/callback` in Google. Replace the
example domain consistently; do not use a Docker-only hostname as the native upstream.

Start DeciFlow with the earlier command in terminal B. In terminal C, from the
repository root, run:

```bash
uv run --env-file .env --extra laya oauth2-proxy \
  --config=oauth2-proxy/oauth2-proxy.cfg \
  --upstream=http://127.0.0.1:4000/ \
  --redirect-url=https://deciflow.example.com:4443/oauth2/callback \
  --authenticated-emails-file=oauth2-proxy/allowed-emails.txt \
  --tls-cert-file=oauth2-proxy/tls/fullchain.pem \
  --tls-key-file=oauth2-proxy/tls/privkey.pem
```

The command overrides the policy file's container paths with native paths.
For an existing Laya server or Jev, omit `--extra laya` here as well.
Change the upstream port if you changed DeciFlow's `PORT`.
Open your public HTTPS origin and test approved/unlisted accounts and a cookie-free
`/api/status` request (401). The browser's public URL, Google callback, and trusted
origin must agree, including the port. Do not forward the UI's internal port.

Stop OP with `Ctrl+C` in terminal C. For renewed certificates or allow-list/policy
changes, update the files and restart **the native OP process**; Docker Compose
recreation commands do not manage it. Keep certificate permissions appropriate to
that process owner. Run OP under your host's service manager if unattended renewal
and restart are needed; no native service unit is installed by this project.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Data/log permission error | Use `./data` and `./logs`, or other writable native paths |
| Model download/loading is slow | Inspect terminal A; initial loading needs download access and adequate memory |
| Engine cannot be reached | Laya process/readiness, native API URL, and API key; `laya` resolves only in Compose |
| Source not found | Absolute host path rather than `/host-logs/...` |
| Native OP returns 403 for UI API calls | Public HTTPS origin in `DECIFLOW_CSRF_TRUSTED_ORIGINS`; restart DeciFlow after editing |
| OP cannot read certificates | Native file paths and private-key owner/permissions |
| Port already in use | Stop the other installation or choose free ports consistently |

For HDFS native Sources, the host also needs the Java/Hadoop/libhdfs requirements
described in [Sources](sources.md#hdfs). They are not prerequisites for the local
TEXT sample. More engine settings are in [Configuration](configuration.md).
