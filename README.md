# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**Classify logs with AI and spot error and security events at a glance.**

DeciFlow classifies each log event as **Normal, Warning, Error, Security, or Other**
with Laya or Jev. Scan a batch, follow new events, and focus your review with
category probabilities and confidence instead of reading every line unaided.

**DeciFlow** runs on the node containing your logs, reads events, and displays
results in a browser. The **Laya server** runs the decision model on a separate
host; **Jev** is an alternative hosted decision API. DeciFlow sends events to the
selected engine and receives predictions.

- **Use logs where they live.** Paste text or select multiple files across
  directories with wildcard patterns; no manual file merging.
- **Switch from investigation to monitoring.** Read existing files in batches or
  monitor new lines and file rotation. Newest completed predictions appear first.
- **Keep people in control.** Filter uncertain predictions, record reviewer
  corrections, and export results as JSON. Rejected events retain their original
  text for review.
- **Share inference across nodes.** Run DeciFlow on each log node and connect
  to a shared Laya server; DeciFlow nodes need no local GPU or PyTorch.
- **Choose your engine.** Use self-hosted Laya by default without Jev API charges,
  or select Jev in `.env`. Both use the same workflow; no automatic paid fallback.

For access logs, application errors, and operational events—start with an existing
log file and review the predictions in your browser.

## Quick start

Choose **Laya or Jev** below; configure only one engine.

Requires **Python 3.11+** and **uv** on the DeciFlow node. A separate Laya server
or the Jev API handles inference, so this node needs no Docker or CUDA.
Create and activate the virtual environment, then install dependencies from the
DeciFlow directory (Linux/macOS/WSL, Bash):

```bash
uv venv
source .venv/bin/activate
uv sync
```

If `.env` does not exist, copy [.env.example](.env.example) to `.env`.
Apply the settings for your chosen engine:

### Use the Laya decision engine

Connect to an existing shared Laya server, or set up one on a remote host below.
If a server is already available, skip setup and configure DeciFlow.

The instructions below use Docker run on the Laya host. Docker Compose is an
alternative; see the official guide linked below and choose only one method.

This guide uses Docker to simplify Laya server setup for both CPU and CUDA.
CUDA additionally requires an NVIDIA driver and
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Check the GPU and driver with `nvidia-smi`: its `CUDA Version` describes driver
support, not the installed Toolkit. `nvcc --version` checks a local Toolkit,
which these containers do not require. A CUDA 13.0 image requires a compatible GPU
and [driver 580 or newer](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).

#### Docker run

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

> **NOTE:** For Docker Compose deployment, see the official
> [Laya Docker guide — HTTP serving](https://nandhakishorm.github.io/laya/docker/#http-serving).

#### Check and manage

Use the server's key in `LAYA_API_KEY` for the health request (default: `changeme`).

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${LAYA_API_KEY:-changeme}" \
  http://127.0.0.1:8000/health
```

On the DeciFlow node, replace `127.0.0.1` with the server address. Inspect
`checkpoint_devices`/`device` and `cpu_fallbacks` to verify actual GPU use.
Restrict Laya access to trusted DeciFlow nodes and use TLS over external networks.
Keep `LAYA_JEV_STRICT=0` for required truncation metadata. Initial model loading
can take several minutes; inspect container logs for startup errors.

| Action | Docker run |
| --- | --- |
| Status | `docker ps --filter name=laya-server` |
| Logs | `docker logs --tail=100 laya-server` |
| Stop | `docker stop laya-server` |
| Resume | `docker start laya-server` |
| Remove | `docker rm laya-server` after stopping |

Removal preserves the model cache. Use only one deployment method at a time.

#### Custom Docker run images (optional)

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

#### DeciFlow connection

On the DeciFlow node, set the shared Laya server URL and matching API key in `.env`:

```dotenv
DECISION_ENGINE=laya
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

### Use the Jev decision engine

Obtain a TypeSafe API key from the [Jev setup guide](https://docs.typesafe.ai/introduction/quickstart)
and set it in `.env`. Jev is paid; no Laya server is needed.

```dotenv
DECISION_ENGINE=jev
TYPESAFE_API_KEY=your-typesafe-api-key
PORT=4000
```

### Run DeciFlow

```bash
uv run python server.py
```

Open **http://127.0.0.1:4000**. Restart DeciFlow after configuration changes.

## Configuration

DeciFlow settings live in `.env`; process environment variables take precedence.
Laya server settings are managed separately on the Laya host.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DECISION_ENGINE` | `laya` | `laya` or `jev` |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | Full Laya URL, including any proxy prefix |
| `LAYA_API_KEY` | `changeme` | Key matching the Laya server |
| `PORT` | `4000` | DeciFlow web port |
| `TYPESAFE_API_KEY` | Unset | Jev API key |
| `MAX_JEV_INPUT_BYTES` | `30000` | Jev request JSON budget in UTF-8 bytes; range 1–30000 |
| `LAYA_CONCURRENCY` | `4` | Maximum simultaneous Laya requests per run; positive integer |
| `JEV_CONCURRENCY` | `4` | Maximum simultaneous Jev requests per run; positive integer |

Concurrency applies to Paste, Batch, and Realtime. It controls DeciFlow requests,
not Laya server workers. Increase gradually within server capacity and API limits.

## Usage

The sidebar identifies the DeciFlow log source host by hostname, detected IPs, and OS name/version.
In WSL or containers, these identify that environment; IPs are not a full interface inventory.

### Decision profiles and chunks

Select a profile and **Lines/chunk** for each path or pattern; Paste has its own
profile and chunk size. Defaults: **General system**, **1 nonempty line**.
Profiles are maintained separately in [`profiles/`](profiles/); edit or add a JSON
profile and restart DeciFlow to update the selector. Built-ins: General system,
Authentication, HTTP access, Application, and Network / tcpdump text.
New profiles must retain the existing five category keys.
Laya and Jev use the same selected criteria; automatic type detection is disabled.

Chunks never mix files. Batch submits the remainder at EOF. Realtime submits when
the chunk fills or no new nonempty line arrives for one second, and separates file
rotation boundaries. Stopping discards unsubmitted chunks. Identical overlapping
source settings are deduplicated; conflicting settings are rejected.
**Pause updates** freezes the result list while analysis and metrics continue.
Filters and pagination use the frozen list; **Resume updates** includes new results.
JSON export includes all received results, even while paused.

Use **View JSON** on a result to inspect its fields, including failures and reviewer edits.

Batch uses **File line(s)** for actual file line numbers. Realtime uses
**Observed line(s)** for the sequence since monitoring started or the file rotated.

Results and JSON retain the profile, configured chunk size, actual line count,
and file line range. Metrics count chunks, not individual lines; request durations
are per chunk. Model input budgets still apply to the complete chunk and question;
oversized or truncated inputs are retained for review rather than silently shortened.
Network input supports UTF-8 tcpdump text, not binary PCAP. Specialized criteria
need validation on your own logs; a larger chunk does not guarantee accuracy.

| Source | Behavior |
| --- | --- |
| Realtime | Start at existing files' end; read new/replacement files from the beginning |
| Batch | Read matching files from the beginning to EOF |
| Paste | Nonempty lines grouped by the selected chunk size |

File sources require local browser access (`localhost`/`127.0.0.1`) and regular
UTF-8 files readable by DeciFlow. Enter one path or pattern per line; absolute paths,
multiple directories, `*`, `?`, `[abc]`, and recursive `**` are supported. Relative
paths start at the server's working directory. Matches are deduplicated by file.
Batch needs matching files; Realtime can wait for new matches.

Predictions use **Normal, Warning, Error, Security, Other**; criteria are defined in
[classifier.py](classifier.py). Results display newest completions first, with probabilities, confidence, progress,
and elapsed time. Below 70% confidence, Other, or failed requests require review. Filter all results,
items needing review, or items not needing review;
correct reviewer categories, and export JSON; the UI displays 100 results per page.
Results are kept in browser memory, so export before leaving.
Reviewer category saves a human correction in JSON as `reviewerCategory`; it does
not change the model prediction, review flag, or train the model.
Average processing time is the mean duration of all completed requests, including
failures and network/server wait; it excludes waiting for new file lines.
Active processing time measures intervals with at least one request in flight,
counting overlapping requests once. Its share of total elapsed time stays within
0–100%; network/server wait is included, idle time is excluded. Timing refreshes
once per second while waiting. Stopped/disconnected runs retain the last received
snapshot, which may lag by about one second. This is not CPU utilization.

**Stop processing** cancels file readers and pending requests to Laya or Jev while retaining
completed results. A model inference already running on the remote server may finish.

## Limits

- No application file-size or line-count cap; RAM and browser capacity still matter.
  File reads are incremental. Chunks use a fixed nonempty-line count, not automatic
  event-boundary detection.
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
- Realtime polls every 250ms and waits for complete lines. Rotation leftovers are
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

Set DeciFlow's `LAYA_API_URL` to loopback and start DeciFlow in another terminal. Use this
adapter for 0.3.20; it adds token-budget checks and truncation metadata missing from
that version's HTTP server. Set local server options through process environment
variables. DeciFlow nodes using a separate Laya server do not need the `laya` extra.

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)
