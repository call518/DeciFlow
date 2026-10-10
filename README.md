# DeciFlow

[English](README.md) | [한국어](README.ko.md)

Classify logs with **Laya** or **Jev**. Paste logs, process files in batches, or
follow live files; review predictions and export results as JSON.

DeciFlow runs on the node containing your logs and sends events to a remote Laya
server or the Jev API. Laya is the default; there is no automatic paid fallback.

## Quick start

Requires **Python 3.11+** and **uv**. Remote clients need no Docker or CUDA.

Create `.env` from [.env.example](.env.example) if it does not exist. Set your Laya
server URL and matching API key:

```dotenv
DECISION_ENGINE=laya
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

Run from the DeciFlow directory:

```bash
uv sync
uv run python server.py
```

Open **http://127.0.0.1:4000**. Restart the server after configuration changes.
To use Jev, set `DECISION_ENGINE=jev` and `TYPESAFE_API_KEY` instead.

## Remote Laya server

Choose **one** deployment method on the remote Laya host:

- **Docker run:** start a prebuilt image with a script.
- **Docker Compose:** clone the official Laya repository and build from source.

This guide uses Docker to simplify Laya server setup for both CPU and CUDA.
CUDA additionally requires an NVIDIA driver and
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Check the GPU and driver with `nvidia-smi`: its `CUDA Version` describes driver
support, not the installed Toolkit. `nvcc --version` checks a local Toolkit,
which these containers do not require. A CUDA 13.0 image requires a compatible GPU
and [driver 580 or newer](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).

### Docker run

Use **`call518/deciflow-laya:cpu`** or **`call518/deciflow-laya:cuda`**.
No clone or build is needed. Copy the required script to the Laya host.

CPU: [run-deciflow-laya-cpu.sh](scripts/run-deciflow-laya-cpu.sh)

```bash
bash scripts/run-deciflow-laya-cpu.sh
```

CUDA: [run-deciflow-laya-cuda.sh](scripts/run-deciflow-laya-cuda.sh)

```bash
bash scripts/run-deciflow-laya-cuda.sh
```

The scripts set `LAYA_API_KEY` to `changeme` by default; an existing environment
value overrides it. Use a strong key for deployment and set the same value in
DeciFlow's `.env`.

The scripts use port **8000**, preload `multilingual`, and share the
`deciflow-laya-model-cache` volume. CUDA exposes all GPUs to the container.
To change the host interface/port, edit `--publish HOST_IP:HOST_PORT:8000` and
update `LAYA_API_URL`. Both scripts use `laya-server`; stop/remove the existing
container before switching CPU/CUDA or changing settings.

### Docker Compose

Requires Docker Compose v2. Clone Laya and configure its official Compose files;
this method builds a local image from source.
Use a strong API key instead of `changeme` and set the same key in DeciFlow's `.env`.

```bash
git clone --branch v0.4.1 --depth 1 https://github.com/NandhaKishorM/laya.git
cd laya

export LAYA_API_KEY="${LAYA_API_KEY:-changeme}"
export LAYA_BIND_ADDRESS=0.0.0.0
export LAYA_PORT=8000
export LAYA_PRELOAD=1
export LAYA_MODELS=multilingual
```

Choose **CPU or CUDA**:

**CPU**

```bash
export COMPOSE_FILE=compose.yaml:compose.http.yaml
export LAYA_DEVICE=cpu
export LAYA_TORCH_INDEX=cpu

docker compose up --detach --build --wait laya-serve
```

**CUDA**

```bash
export COMPOSE_FILE=compose.yaml:compose.http.yaml:compose.cuda.yaml
export LAYA_DEVICE=cuda
export LAYA_TORCH_INDEX=cu130

docker compose up --detach --build --wait laya-serve
```

`compose.http.yaml` configures the HTTP server; `compose.cuda.yaml` adds GPU access
and the CUDA build. `LAYA_BIND_ADDRESS` selects the host IP and `LAYA_PORT` sets both
host and container ports. Update `LAYA_API_URL` to match. Keep the same directory,
`COMPOSE_FILE`, and exported settings for management; repeat `up` after changes.
For slow model loading, add `--wait-timeout 1200`.

### Check and manage

Use the server's key in `LAYA_API_KEY` for the health request (default: `changeme`).

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${LAYA_API_KEY:-changeme}" \
  http://127.0.0.1:8000/health
```

On the DeciFlow node, replace `127.0.0.1` with the server address. Inspect
`checkpoint_devices`/`device` and `cpu_fallbacks` to verify actual GPU use.
Restrict access to trusted clients and use TLS over external networks.
Keep `LAYA_JEV_STRICT=0` for required truncation metadata. Initial model loading
can take several minutes; inspect container logs for startup errors.

| Action | Docker run | Compose |
| --- | --- | --- |
| Status | `docker ps --filter name=laya-server` | `docker compose ps` |
| Logs | `docker logs --tail=100 laya-server` | `docker compose logs --tail=100 laya-serve` |
| Stop | `docker stop laya-server` | `docker compose stop laya-serve` |
| Resume | `docker start laya-server` | `docker compose up --detach` |
| Remove | `docker rm laya-server` after stopping | `docker compose down` |

Removal preserves the model cache. Use only one deployment method at a time.

### Custom Docker run images (optional)

Build from Laya **v0.4.1** only when you need your own image:

```bash
git clone --branch v0.4.1 --depth 1 https://github.com/NandhaKishorM/laya.git
cd laya

docker build \
  --build-arg TORCH_INDEX=cpu \
  --tag my-laya:cpu .

docker build \
  --build-arg TORCH_INDEX=cu130 \
  --tag my-laya:cuda .
```

Replace the image in the chosen Docker run script with your custom tag.
`cpu` installs CPU-only PyTorch; `cu130` means CUDA **13.0**. Select a CUDA build
supported by your GPU/driver and the Dockerfile's `TORCH_VERSION` using the
[PyTorch installation list](https://pytorch.org/get-started/previous-versions/).
Validate API compatibility when upgrading Laya.

## Configuration

Client settings live in `.env`; process environment variables take precedence.
Laya server settings are managed separately on the remote host.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DECISION_ENGINE` | `laya` | `laya` or `jev` |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | Full Laya URL, including any proxy prefix |
| `LAYA_API_KEY` | `changeme` | Key matching the Laya server |
| `PORT` | `4000` | DeciFlow web port |
| `TYPESAFE_API_KEY` | Unset | Jev API key |
| `MAX_JEV_INPUT_BYTES` | `30000` | Jev request JSON budget in UTF-8 bytes; range 1–30000 |

## Usage

| Source | Behavior |
| --- | --- |
| Paste logs | One event per nonempty line |
| Batch file | Read matching files from the beginning to EOF |
| Follow file | Start at existing files' end; read new/replacement files from the beginning |

File sources require local browser access (`localhost`/`127.0.0.1`) and regular
UTF-8 files readable by DeciFlow. Enter one path or pattern per line; absolute paths,
multiple directories, `*`, `?`, `[abc]`, and recursive `**` are supported. Relative
paths start at the server's working directory. Matches are deduplicated by file.
Batch needs matching files; Follow can wait for new matches.

Predictions use **Normal, Warning, Error, Security, Other**; criteria are defined in
[classifier.py](classifier.py). Results display newest completions first, with probabilities, confidence, progress,
and elapsed time. Below 70% confidence or Other requires review. Filter results,
correct reviewer categories, and export JSON; the UI displays 100 results per page.
Results are kept in browser memory, so export before leaving.
Reviewer category saves a human correction in JSON as `reviewerCategory`; it does
not change the model prediction, review flag, or train the model.
Average processing time is the mean duration of all completed requests, including
failures and network/server wait; it excludes waiting for new file lines.

**Stop processing** cancels file readers and pending client requests while retaining
completed results. A model inference already running on the remote server may finish.

## Limits

- No application file-size or line-count cap; RAM and browser capacity still matter.
  File reads are incremental. Multiline events are not grouped.
- **Laya:** `multilingual`, 8192 tokens including the question (question head: 256).
  The documented server also limits events to 50,000 characters and requests to 2 MiB.
  Truncated responses or missing truncation metadata are rejected.
- **Jev:** `jev-1.13.0`, [32k state + longest question, 64k full request](https://docs.typesafe.ai/models).
  The byte budget is a conservative guard, not a token count or acceptance guarantee.
- Rejected events retain their original text for review; other events continue.
  Source read/UTF-8 errors stop processing and preserve completed results.
- Each event makes one request, with up to four concurrent calls (Laya: 120s timeout;
  Jev: 30s). Laya serializes inference. Throughput depends on hardware/network and
  provider limits; confidence is model certainty, not measured accuracy.
- Follow polls every 250ms and waits for complete lines. Rotation leftovers are
  marked `incomplete`; line numbers reset on rotation. Rapid rotation or
  copy-truncate/regrowth can lose events. File deduplication does not remove duplicate
  contents; avoid matching both active logs and their rotated copies.
- Laya sends logs to your server; Jev sends them to TypeSafe and incurs API charges.
  DeciFlow does not save logs/results to server disk. Remove sensitive data before
  submission and never commit `.env`. Public deployment needs authentication and
  usage limits.

## Development

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

UI regression test (requires Node.js only for testing):

```bash
node --test tests/test_ui.mjs
```

Tests cover both providers without paid calls, input budgets, streaming,
cancellation, and file discovery/rotation. Keep both READMEs and actual/example
`.env` files synchronized; environment comments use English and Korean.

For optional local Laya development (0.3.20):

```bash
uv sync --extra laya
uv run --extra laya python laya_server.py
```

Set the client URL to loopback and start DeciFlow in another terminal. Use this
adapter for 0.3.20; it adds token-budget checks and truncation metadata missing from
that version's HTTP server. Set local server options through process environment
variables. Remote clients do not need the `laya` extra.

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)
