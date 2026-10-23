<p align="center">
  <a href="https://youtu.be/bXuBJs4Hf70" target="_blank" rel="noopener noreferrer"><img src="images/DeciFlow-Logo.png" alt="DeciFlow" width="480"></a>
</p>

# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**Make fast AI decisions across diverse datasets and automate follow-up workflows your way.**

<p align="left">
  <a href="https://youtu.be/bXuBJs4Hf70" target="_blank" rel="noopener noreferrer">Demo Video - YouTube</a>
</p>

## Installation

**DeciFlow** serves the UI/API and reads sources. A separate **Laya server** runs
inference, or choose **Jev**, a paid hosted inference API. Choose one installation
method in this recommended order:

| Priority | Method and Guide | Default `.env` Location |
| --- | --- | --- |
| 1 — Recommended | [PyPI / uv tool](docs/tool-install.md) | `~/.config/deciflow/.env` |
| 2 | [Git clone + Docker Compose](#quick-start--docker--laya-cpu) | `<checkout>/.env` → `/app/.env` inside the UI container |
| 3 | [Git clone + native Python](docs/native.md) | `<checkout>/.env` for DeciFlow and the local Laya adapter |

`<checkout>` means the cloned DeciFlow repository root. These files are not shared
automatically. See [environment file locations](docs/configuration.md#environment-file-locations)
for path selection and precedence.

Install from PyPI and initialize your configuration:

```bash
uv tool install deciflow
deciflow init
```

Maintainers publish matching tag versions to TestPyPI and PyPI through the
[tag release workflow](docs/tool-install.md#publish-from-a-git-tag).
Edit `~/.config/deciflow/.env`, connect a running Laya server or configure Jev,
and prepare writable storage using the [installation guide](docs/tool-install.md).
Then start:

```bash
deciflow
```

Every `deciflow` startup checks prerequisites before starting the server.
Use `deciflow config test` for detailed diagnostics and `deciflow config list`
to inspect effective settings with secrets redacted. For another configuration
directory, pass the same `--config-dir` to every command.

## Architecture

[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/call518/DeciFlow)

![DeciFlow architecture](images/DeciFlow-Architecture.png)

DeciFlow reads TEXT log chunks or individual JSONL records and sends their text
to Laya or Jev. A Criteria profile defines named `choice`, `score`, and `noul`
decisions in one request; the number and mix of decisions are configurable.
System profiles retain **Normal, Warning, Error, Security, Other**, urgency, and
work-ticket probability. Consultation profiles can classify inquiry type,
handling status, follow-up ownership, urgency, and follow-up need.

Each result shows all decisions in the profile's configured order. **Result #** identifies
completion order within a run, independently of input order. Numbers stay unchanged
by filtering or paging; the latest unfiltered result number equals the completed total. Expand **Probabilities and Criteria** for its distribution
and definitions. **Review** records typed human corrections without
changing AI predictions. Scores are probability-weighted values, not rounded grades.
DeciFlow does not create tickets automatically.

Token-limit and shortened-Criteria warnings appear on the affected result. See
[token warnings](docs/usage.md#token-warnings) for detection limits. Criteria-shortening
metadata is provided by the local adapter; external servers may omit it. The current
provider contract has no separate output-truncation signal.

The **Processing Time** card groups Avg, Min, Max, P(50), P(95), and P(99). Throughput shows
successful results per active classification second, excluding idle time and Action delivery. All metrics cover the selected run;
filters and pagination do not change these run metrics. The Overview chart reflects
all results matching the active filters, across pages.
Run URLs retain chart selections, Show Decisions, and result filters on reload;
list searches persist within the same browser tab.

**DeciFlow** runs on the node containing your logs, reads events, and displays
results in a browser. The **Laya server** runs the decision model on the same or a separate
host; **Jev** is an alternative hosted decision API. DeciFlow sends events to the
selected engine and receives predictions.

- **Use logs where they live.** Register local files and SSH remote files,
  including wildcard patterns; select saved Sources without retyping paths.
- **Switch from investigation to monitoring.** Read existing files in batches or
  monitor new lines and file rotation. Newest completed predictions appear first.
- **Keep people in control.** Inspect uncertain predictions, record reviewer
  corrections, and export results as JSON. Rejected events retain their original
  text for review.
- **Share inference across nodes.** Run DeciFlow on each log node and connect
  to a shared Laya server; DeciFlow nodes need no local GPU or PyTorch.
- **Choose your engine.** Use self-hosted Laya by default without Jev API charges,
  or select Jev in `.env`. Both use the same workflow; no automatic paid fallback.

For access logs, application errors, and operational events—start with an existing
log file and review the predictions in your browser.

Result JSON keeps input text once; SQLite shares repeated Criteria definitions per run. Custom Actions should follow the [compact v2 contract](docs/actions.md#compact-result-json-contract-version-2).

Menus, item details/editors, Task History, and execution results have [shareable clean URLs](docs/usage.md#shareable-urls), including result filters and cursor pages. Legacy hash links remain supported.

## Quick start — Docker + Laya CPU

**Requires:** Git and Docker Compose 2.20.0+ on one Linux host.
The default HTTP demo needs no domain, certificate, or Google configuration.
A compatible NVIDIA GPU can improve Laya's inference performance; see
[Run with GPU (CUDA)](#laya-gpu). This quick start
uses CPU so you can try DeciFlow across a wider range of environments.
Laya runs inference; DeciFlow reads sources and serves the UI/API.
Optional OAuth2-Proxy adds HTTPS, Google sign-in, and an email allow list.

### 1. Prepare the repository

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
# Only if .env does not exist / 기존 .env가 없다면
test -f .env || cp .env.example .env
```

The `.env` above is `<checkout>/.env` on the Docker host and is mounted as
`/app/.env` inside the UI container. Docker does not read the uv tool configuration
at `~/.config/deciflow/.env`. See [environment file locations](docs/configuration.md#environment-file-locations).

### 2. Configure CPU execution

Set these values in `.env`. The `laya` hostname resolves inside the Compose network
for both CPU and CUDA. Keep your existing API key; Compose passes it to both containers.

```dotenv
COMPOSE_PROFILES=cpu
OAUTH2_PROXY_ENABLED=false
DECIFLOW_BIND_HOST=127.0.0.1
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya:8000/v1/systemone
PORT=4000
```

### 3. Start the containers

For the HTTP demo, leave OAuth settings blank. To require sign-in instead,
complete [Google sign-in and HTTPS setup](docs/authentication.md), including
[DNS and TLS preparation](docs/dns-tls.md), and set `OAUTH2_PROXY_ENABLED=true`.

```bash
docker compose up -d --remove-orphans
docker compose logs --follow laya-cpu
```

Wait for the initial model download/loading, then press `Ctrl+C` to leave the log viewer.
[Check readiness](#laya-health) before continuing.

### 4. Analyze sample logs

Open **http://localhost:4000**. With OAuth2-Proxy enabled, open `OAUTH2_PROXY_PUBLIC_URL` and sign in
with an approved Google account instead. In **Sources**, edit
**Sample HTTP access** to use `/host-logs/sample-logs/access-100.log` and save.
In **Tasks**, add a named **Batch / Manual** Task, select **Sample HTTP access**,
**Sample HTTP access** criteria, **Events/Chunk: 1**, and **Action: None**, then save.
New Tasks default to Disabled. Enable the Task, then click **Run** in Tasks to open Main and view its results automatically. Use **Pause / Resume** in Tasks to continue the same execution later. New active executions also recover after a server restart; paused executions stay paused. See [recovery limits](docs/tasks.md#recovery-after-a-server-restart).

Referenced Sources, Criteria, Tasks, and SSH settings remain editable; existing runs retain their snapshots. Stop active runs before changing Action code or environments, or resetting them. Deletion is blocked while referenced or in use.

For optional GPU acceleration, see [Docker deployment details](#laya-docker);
for a paid API, see [Jev](#jev).
The default key `changeme` is for trials. Change it in `.env` before deployment.

Choose access in `.env`: `OAUTH2_PROXY_ENABLED=false` serves local HTTP; `true`
serves authenticated HTTPS on port 4443 and keeps the UI inside Docker.
After switching, run `docker compose up -d --remove-orphans` to remove the unused
proxy. Data volumes are retained. For access from other hosts in HTTP mode, set
`DECIFLOW_BIND_HOST=0.0.0.0` and the browser origin in `DECIFLOW_CSRF_TRUSTED_ORIGINS`,
then run the same command. Forward TCP 4000 if needed; anyone reaching it can use
all management features. See [Google sign-in setup](docs/authentication.md).

A built-in **Sample DeciFlow Server Log** Task monitors `DECIFLOW_LOG_DIR/server.log` / `DECIFLOW_LOG_DIR/access.log`; it is disabled by default (enable it before Run). Missing default configuration is restored on startup, including after Reset DeciFlow. See [Tasks](docs/tasks.md).

Use **Export Reviewed JSON** in Classification Results to download only results
with human corrections to any Choice, Score, or Noul decision in the selected run.

## Analyze customer consultations

Use this workflow as an alternative to the log example; both remain supported.

1. In **Sources**, use the automatically provided **Sample VOC Asia Culture Center Consulting QnA** sample,
   or register a readable file, select **JSONL (Line)**, and enter its
   **Content Field** (`consulting_content` for both supplied samples). With the
   supplied host samples and Compose mount, use
   `/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl` or
   `/host-logs/sample-logs/voc-central-gov-consulting-qna.jsonl`.
2. In **Criteria**, select **Sample VOC Asia Culture Center Consulting QnA**, automatically added
   at startup when absent, or Clone it to customize. Use a query-specific profile
   for question-only inputs; follow-up judgments require conversation evidence.
3. Enable the provided **Sample VOC Asia Culture Center Consulting QnA** Batch Task and Run, or
   create a Task with the desired Source and Criteria and Action None.
   JSONL always processes one object per line, preserving repeated conversations
   as separate records. The supplied consultation file has 841 input records.
4. In **Main**, select the Task, inspect results, and record corrections. Mixed
   classification schemes have separate choices under **Criteria** in the chart.

The Overview **Decision** selector includes every decision.
Every Criteria profile has a UUID, shown with a copy button as **Criteria ID** in
View and Edit. Names can change without changing IDs; cloning creates a new ID.
Source, Criteria, and Action lists provide **Manage → Ref.**, Edit provides a **References** link, and View displays reference details inline
for inspecting Task assignments and execution dependencies. Existing Criteria can
be revised with AI in Edit; review the draft before saving.

Default Chart Decision selects one item of any type and can be changed without changing
AI answers or filters. Choice charts count selected options; Score charts round weighted scores to the
nearest level; Noul charts group Yes probabilities into 25% intervals. Certainty groups
refer to the selected Choice. Score and Noul have no certainty groups. Show Decisions
selects which judgments appear in each card without filtering results or fetching data.
Decision, Processing Status, Source, Host, Review Status, and Search Text filter the whole run.
Decision filtering affects result cards only; the other filters also update Overview.
Needs Review includes issues in any decision. Switching charts does not run inference.

Content Field is a literal top-level key containing nonempty text. Malformed JSONL
records are retained as failures while later records continue. Files must be
accessible inside the DeciFlow container; this workflow does not upload files.
Existing Sources default to **TEXT (Chunk)**. See [Sources](docs/sources.md) and
[Criteria](docs/criteria.md) for configuration and limits.

See the [VOC walkthrough and complete sample form values](docs/voc.md) and
[field-by-field Criteria authoring guide](docs/criteria.md) before customizing.

Criteria can also be drafted with **Generate With AI** in Add Profile. Set
`OPENAI_API_KEY` and `OPENAI_CRITERIA_MODEL` (default `gpt-5.6-terra`) in DeciFlow's `.env`
and restart DeciFlow. Select a Source (and one SSH Host for remote files), preview
and redact samples. Sample Count offers 10 (default), 20, 30, 50, or 100. Preview scans the
entire Source and randomly selects complete samples, totaling at most 150,000 UTF-8
bytes; empty and oversized inputs are excluded. Source size or the byte limit may
yield fewer samples. Scans time out after 20 seconds without returning a partial
preview; preview again to draw a new random sample. More samples consume more tokens and may increase API charges.
Only the remaining edited samples are sent on generation. Analysis Purpose Mode defaults to
Automatic (ChatGPT); choose Manual to supply your own objective. Review the
suggested purpose and generated Criteria before saving.
Events Per Sample groups TEXT events for preview only; JSONL shows an explanation
that one record is one sample. Purpose guidance explains the desired decisions,
judgment time, and rules.
Creation and editing share Automatic/Manual purpose modes and optional
**Additional Instructions**; application rules take precedence over conflicting requests.
OpenAI receives the edited samples, purpose, additions, authoring rules, and current
draft when editing; generation incurs
API charges. Review the complete validated draft and select **Save Changes**.
Classification continues to use Laya or Jev; generation does not assign a Task.
See [AI Criteria generation](docs/criteria.md#generate-criteria-with-ai).

### Government QnA Sample

**Sample VOC Central Gov Consulting QnA** is also added at startup, including to existing
installations. Its Source uses `/host-logs/sample-logs/voc-central-gov-consulting-qna.jsonl`,
JSONL (Line), and Content Field `consulting_content` (3,965 records).
The **Sample VOC Central Gov Consulting QnA** Criteria classify Policy Area,
Response Type, Follow-up Owner, Urgency, and Follow-up Required. They distinguish
rule explanations, application guidance, referrals, completed processing, and
explicitly outstanding agency actions. Referrals and contact footers alone do not
create agency follow-up obligations; the profiles do not verify current law.
The provided **Sample VOC Central Gov Consulting QnA** Task uses Korean Criteria,
Batch / Manual, Events/Chunk 1, and Action None. It starts disabled with Resume on
Restart off. Enable it and click Run to analyze the sample. Saved edits are preserved.

### Local Government QnA Sample

**Sample VOC Local Gov Consulting QnA** Source, Criteria, and Task are added at startup,
including to existing installations; saved edits are preserved. The Source reads
`/host-logs/sample-logs/voc-local-gov-consulting-qna.jsonl` (3,280 records) as
JSONL (Line), with Content Field `상담내용`. Only this field is sent for classification;
`지방자치단체명` and `상담담당부서` remain original record metadata, including empty departments.
The Korean Criteria cover local policy area, response type, follow-up owner, urgency,
and follow-up required. General project schedules and improvement plans alone do not
count as outstanding commitments for an individual inquiry. The Task uses Batch / Manual,
Events/Chunk 1, and Action None, with Enabled and Resume on Restart off. Start
DeciFlow-UI, enable the Task, and click Run. Host execution and Source paths are
covered in the [native guide](docs/native.md).

All bundled VOC Criteria are Korean-only and omit language suffixes. Saved Source
paths and customizations are preserved; edit Source paths manually when needed.

Bundled Source, Criteria, Task, and Action names begin with **Sample**.
Saved names and settings are preserved.
Reset recreates the same sample names.

Task History and reopened results show the engine and requested model saved when
the run started. Missing historical metadata is **Not Recorded**; current server
settings are never substituted.

Floating **▲ / ▼** buttons scroll to the top or bottom of Classification Results
without changing result pages or starting analysis.

Per-result Action, Source/Host, and Criteria/chunk metadata is collapsed under **Details**;
Action failures show a short summary on the card; expand **Error Details** for
execution metadata and the recorded error output. Full metadata is retained in **View Result JSON**.

Every result includes a **Response** disclosure styled like **Review**,
with a read-only response panel and Copy. It shows the provider response and specific format-validation
errors for Laya and Jev, including non-JSON error bodies. Historical records without
a saved body and requests that received no response are identified explicitly.

## Usage and configuration

Browse the [documentation guide](docs/README.md) for all guides, deployment references,
and request/result examples.

| Guide | Contents |
| --- | --- |
| [Tasks](docs/tasks.md) | Reusable executions, cron schedules, continuous monitoring, and durable run history |
| [Result Storage](docs/result-storage.md) | SQLite, pagination, configuration/result storage, backups, and database adapters |
| [Sources](docs/sources.md) | Register local/SSH sources, manage SSH Keys in Settings, and select sorted dropdown entries |
| [Usage](docs/usage.md) | Input modes, criteria, filters, human review, reconnecting, timing |
| [Configuration](docs/configuration.md) | Environment variables, models, input budgets |
| [Criteria](docs/criteria.md) | Manage typed decision profiles in one list with internal UUIDs and optional AI generation |
| [Python Actions](docs/actions.md) | Configuration viewing, environment Status, pip-enabled environments, Reset venv, deletion, source assignment |
| [Result JSON](docs/results.md) | Current request/result examples and field reference |

Configure Sources → Criteria → optional Actions → Tasks, then select Tasks in Main to view current or latest results. Sources accept multiple paths or patterns, one per line. Remote Sources define reusable paths; each Task chooses one or more
SSH Hosts per Source. Hosts collect independently, share classification slots
fairly, and produce unified results with Host filtering and collection status.

Sources, Criteria, Actions, and Tasks lists sort names alphabetically, including Korean
names. All Criteria share the same View, Edit, Clone, and Delete controls. Sources show type/format badges and one path per line.
Result cards share borders and thick separators across all Tasks. Compact filter controls
select a filter type and its value; conditions combine, remain active when switching types,
and can be removed individually or with **Clear All**.
**Results per Page** defaults to 30, with 10/30/50/100 options; saved preferences are preserved.

The browser updates only new results and reuses existing cards. Rendering pauses
while Main or the tab is hidden; Tasks keep running and all results are retained.

Main groups Source, Criteria, Actions, and Tasks; Settings groups SSH Keys and
SSH Hosts and Configurations (engine/model/budget/concurrency overrides, AI authoring model, result page size, and maintenance). Returning through the sidebar opens lists and discards unsaved drafts.
[Usage](docs/usage.md) covers navigation, result controls, and reconnecting.
Settings and results share `DECIFLOW_DATA_DIR/deciflow.sqlite3`; only SSH key material, known_hosts and Action execution files remain on disk. This test-stage storage change does not import earlier JSON registries or databases: reset application data before use.

A bundled **Sample Elasticsearch** Action is registered on fresh initialization/reset (Python 3.12, module `elasticsearch`). Startup automatically prepares its script, venv, Python and module before Tasks start (download access is required). Setup failures appear in Actions and can be retried by saving or restarting. It is not assigned to Tasks automatically.

Action execution files use `actions/<Action UUID>/`; changing the Name does not create another venv. Action and SSH Key names are editable. Task Action selections and SSH Host key selections use UUIDs; renaming preserves assignments, key files, and Action environments.

**Settings → Configurations** lets you save non-secret operational overrides without restarting the server. New runs use them; active/recovered runs retain their snapshots. UI overrides take precedence over `.env`; clear Use UI Override to restore its fallback. API keys and deployment settings remain in `.env`. See [configuration](docs/configuration.md).
**Restart DeciFlow**, below Reset, preserves data and suspends/recovers eligible Tasks before replacing the UI process; Docker/Laya deployment changes require their own restart/recreation.

**Settings → Configurations → Reset DeciFlow** permanently clears application data
and restarts the UI server after explicit confirmation. Back up data first; see
[reset scope and behavior](docs/configuration.md#reset-deciflow).

Settings accepts private keys by **Upload, Path, or Paste**, copies them into managed
storage, and derives public keys. SSH Hosts save connection details and a key.
**Test Connection** checks SSH authentication and SFTP; the visible host list also
checks sequentially once per visit. View and redraws do not repeat checks. Unknown fingerprints
require approval in an in-app dialog. Approved host keys persist only in
`DECIFLOW_DATA_DIR/ssh-hosts/known_hosts`, separately from user SSH.
See [Sources and SSH settings](docs/sources.md) for setup and trust management.

- **Tasks:** Save Source/Criteria/chunk/Action settings. Run Batch manually or with cron; run Realtime continuously. Disable stops the current run and blocks future starts. Main prioritizes running Tasks and shows compact Source details with full hover tooltips. See [Tasks](docs/tasks.md).
- **Batch:** Analyze registered local, SSH, or HDFS files. Docker maps host `/var/log` to `/host-logs/var/log`.
- **Realtime:** Follow new logs; choose criteria and chunk size per source.
- **Processing status:** Success / Failed / Total shows classified, failed, and total completed chunks. Action Success / Failed / Total counts follow-up executions separately. Needs Review
  counts successful classifications only. On page load, an HTTP-only check shows Reachable when the engine responds. New classification requests then update the status to Operational or an error. Historical results do not change it.
- **Review:** Filter Needs Review and record corrections. **Export All JSON** includes the entire selected run; **Export Reviewed JSON** includes only results with human corrections to Choice, Score, or Noul decisions. Certain does not
  guarantee accuracy. Task definitions and run history persist in the data volume; reviewer corrections persist in SQLite.

## Docker deployment details

<a id="laya-docker"></a>

### Use the Laya decision engine

Connect to an existing shared Laya server, or set up one on a remote host below.
If a server is already available, skip setup and configure DeciFlow.

Use [docker-compose.yml](docker-compose.yml) from the cloned repository on the Laya
host. CPU is the default in `.env.example`; a compatible NVIDIA GPU can improve
inference performance. Actual performance varies with hardware and workload.
Compose validates the complete `.env`, including OAuth settings, even when selecting
only a Laya service. Complete [deployment setup](docs/authentication.md) first.

#### CPU execution

Set `COMPOSE_PROFILES=cpu` in `.env`, then run:

```bash
docker compose up -d laya-cpu
```

For Laya and DeciFlow together, use `docker compose up -d` instead.
Both Laya variants publish host port **8000**, share the `deciflow-laya-model-cache`
volume, and preload `english`, `multilingual`, and `typed-decisions`.
Choose exactly one profile; CPU and CUDA cannot run together with this configuration.
`LAYA_API_KEY` in `.env` configures both Laya and DeciFlow; an empty key disables authentication.

<a id="laya-gpu"></a>

#### Optional: GPU acceleration (CUDA)

CUDA additionally requires a compatible NVIDIA GPU, a driver, and
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Check the GPU and driver with `nvidia-smi`: its `CUDA Version` describes driver
support, not the installed Toolkit. These containers need no local CUDA Toolkit.
The CUDA 13.0 image requires [driver 580 or newer](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).
The CUDA service reserves all GPUs; the CPU service requests none.

To switch an existing deployment, export any results you need, then stop the current
stack **before editing the profile**:

```bash
docker compose down
```

Set `COMPOSE_PROFILES=cuda` in `.env`, then run:

```bash
docker compose up -d
docker compose logs --follow laya-cuda
```

To return to CPU, follow the same steps with `COMPOSE_PROFILES=cpu`.
The internal URL `http://laya:8000/v1/systemone` stays the same.

<a id="laya-health"></a>

#### Check and manage

Use the server's key for the health request. This command reads it inside the
selected container without printing it; replace `laya-cpu` with `laya-cuda` for CUDA:

```bash
docker compose exec laya-cpu python -c 'import os, urllib.request; r = urllib.request.Request("http://127.0.0.1:8000/health", headers={"Authorization": "Bearer " + os.environ["LAYA_API_KEY"]}); print(urllib.request.urlopen(r).read().decode())'
```

For CUDA, inspect `checkpoint_devices`/`device` and `cpu_fallbacks` to verify GPU use.
Restrict Laya access to trusted DeciFlow nodes and use TLS over external networks.
Keep `LAYA_JEV_STRICT=0` for required truncation metadata. Initial model loading can
take several minutes; inspect container logs for startup errors.

| Action | Command |
| --- | --- |
| Status | `docker compose ps` |
| Logs | `docker compose logs --tail=100` |
| Stop | `docker compose stop` |
| Resume | `docker compose start` |
| Remove containers | `docker compose down` |

`down` preserves named volumes. Do not add `--volumes` if you need to keep data.
Choose either native execution or Docker.

#### DeciFlow connection

For the same Compose stack, set `LAYA_API_URL=http://laya:8000/v1/systemone`.
For an external Laya server, set its reachable URL and matching API key in `.env`:

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

Set `COMPOSE_PROFILES=` and run `docker compose up -d`; UI starts without local Laya; OAuth2-Proxy follows OAUTH2_PROXY_ENABLED.
For execution without Docker, follow the [native guide](docs/native.md).

<a id="jev"></a>

### Use the Jev decision engine

Obtain a TypeSafe API key from the [Jev setup guide](https://docs.typesafe.ai/introduction/quickstart)
and set it in `.env`. Jev is paid; no Laya server is needed.

```dotenv
DECISION_ENGINE=jev
JEV_MODEL=jev-1.13.0
JEV_API_KEY=your-typesafe-api-key
PORT=4000
```

### DeciFlow Docker

Choose Docker or the [native installation](docs/native.md). The DeciFlow host needs
Docker with Compose, not local Python/uv/CUDA. Configure `.env` for Laya or Jev first.
For external Laya or Jev, set `COMPOSE_PROFILES=` and start the selected access mode:

```bash
docker compose up -d
```

Compose uses the published `call518/deciflow-ui:0.0.2` image from Docker Hub.
The image provides Python, uv, and operational utilities. The repository is mounted
read-only at `/app`; `uv sync --frozen` installs dependencies into `deciflow-venv`
on startup. Initial startup needs network access. Compose passes `.env` to the UI;
`PORT` controls the UI port (default: 4000). HTTP mode publishes it on
`DECIFLOW_BIND_HOST`; OAuth2-Proxy mode publishes only HTTPS on 4443.
Compose checks for updated images on each `up` with `pull_policy: always`.
The UI and Laya services map `host.docker.internal` to the Docker host gateway via `extra_hosts`. Recreate existing containers to apply this mapping.

#### Dockerfile and Compose responsibilities

[`Dockerfile`](Dockerfile) builds the UI runtime from `python:3.12-slim`, installs
uv `0.7.20` and operational tools, and sets `/app` as the working directory.
The runtime also includes Java and the Apache Hadoop `3.5.0` client libraries
(`libhdfs`) for PyArrow `23.0.1`, plus `hdfs` and `hadoop` CLI commands on PATH. Hadoop archives are verified with pinned SHA-512
checksums; Linux amd64 and arm64 binaries are selected during the build.
Standard Hadoop configuration templates are installed at `/etc/hadoop/conf`,
including `core-site.xml`, `hdfs-site.xml`, environment scripts, policies, and SSL
examples. Logging defaults to WARN on stderr. Cluster endpoints and credentials
are not preconfigured.
It does not copy application source or preinstall project dependencies. Its startup
command runs `uv sync --frozen --no-dev --no-install-project --no-cache`, then starts
`server.main(host='0.0.0.0')`. The published UI image therefore still needs the cloned
repository mounted at `/app`. UI inference runs on Laya or Jev, not inside this image.
For SSH Key management and remote file requirements, see [Sources](docs/sources.md).

HDFS Sources offer **HDFS (Native)** and **HDFS (WebHDFS)** for Batch reads of
UTF-8 TEXT and JSONL files. See
[HDFS configuration and limits](docs/sources.md#hdfs) for cluster mounts, authentication,
and execution behavior.
To check PyArrow/JVM/libhdfs loading and file I/O without an HDFS server, run the
following against a locally built image (the temporary container uses its own venv):

```bash
docker build --tag deciflow-ui:hdfs-runtime-check .
docker run --rm --mount type=bind,src="$PWD",dst=/app,readonly \
  deciflow-ui:hdfs-runtime-check sh -c \
  'uv sync --frozen --no-dev --no-install-project --no-cache && /opt/deciflow-venv/bin/python scripts/check_hdfs_runtime.py'
```

The check uses Hadoop's local filesystem through JNI and `hdfs dfs -ls`. It does not verify HDFS
connectivity, Kerberos authentication, or cluster compatibility.

[`docker-compose.yml`](docker-compose.yml) supplies the runtime configuration:

| Item | Behavior |
| --- | --- |
| `name: deciflow` | Compose project/group name; lowercase. Individual container names retain DeciFlow capitalization. |
| `ui` | Always enabled; pulls the published UI image if missing, reads `.env`, listens internally on PORT, and mounts source/logs/data. No build step. |
| `laya-cpu` / `laya-cuda` | Selected by COMPOSE_PROFILES=cpu or cuda; same laya network alias and port 8000. Only CUDA reserves GPUs. |
| `oauth2-proxy` | Enabled when OAUTH2_PROXY_ENABLED=true as DeciFlow-OAuth2-Proxy; publishes HTTPS on 4443 and forwards approved users to ui. |
| `x-laya` | YAML anchor for shared Laya settings; not an additional container. |
| Named volumes | deciflow-venv, deciflow-data, deciflow-logs, and deciflow-laya-model-cache retain their existing names. |

Compose reads `.env` for interpolation and passes it to the UI through `env_file`.
Only the declared Laya server variables are passed to Laya; its API key uses the same
`LAYA_API_KEY`. Process environment values override `.env` during interpolation.
`COMPOSE_PROFILES` is independent of `DECISION_ENGINE`: for Jev or external Laya,
leave profiles empty; UI remains enabled and OAuth2-Proxy follows OAUTH2_PROXY_ENABLED. The UI can start before Laya is ready;
check Laya readiness before analyzing logs. There is no automatic paid fallback.

With OAuth2-Proxy enabled, only HTTPS on 4443 is published; open `OAUTH2_PROXY_PUBLIC_URL`.
With OAuth2-Proxy disabled, open `http://localhost:4000` (or your configured HTTP host/port).
Laya's separate API remains on 8000.
The `deciflow-data` volume stores Sources, Tasks and run history, Actions, Criteria, SSH Key pairs, and SSH Hosts at `DECIFLOW_DATA_DIR`
(default: `/var/lib/deciflow-data`); `deciflow-logs` stores server logs.
Use absolute container paths for custom data/log directories.

#### Mount host log directories

Host `/var/log` and repository `sample-logs` are mounted read-only at
`/host-logs/var/log` and `/host-logs/sample-logs`. For other logs, add a mount under
`services.ui.volumes` in `docker-compose.yml`:

```yaml
      - /your/logs:/host-logs/custom:ro
```

Apply mount changes with `docker compose up -d ui`. Recreating the UI interrupts
active executions; Task history remains in the data volume. In the UI, use the container
path `/host-logs/custom/app.log`. The process needs permission to read host files.

#### Connection settings and restart

The Compose Laya address is `http://laya:8000/v1/systemone`; for an external server,
use an address reachable from the container. `127.0.0.1` refers to the UI container.
Sidebar host/OS/IP information describes the container.
For `.env` engine settings (`DECISION_ENGINE`, `LAYA_*`, `JEV_*`), use Docker
Desktop Restart on DeciFlow-UI or `docker compose restart ui`, then refresh the
browser. **Restart DeciFlow** is also available in Configurations. UI overrides take precedence; clear them to use changed `.env` values. The UI reloads explicit engine settings from the mounted file at startup.
Ports, mounts, Compose profiles, and Laya service settings still require
`docker compose up -d` to recreate affected containers.
For source changes, run `docker compose restart ui` and refresh the browser after UI
changes. If you modify the Dockerfile, build the UI image explicitly with
`docker build --tag call518/deciflow-ui:0.0.2 .`, then run
`docker compose up -d --force-recreate ui`.
Stop DeciFlow before switching source versions.

With OAuth2-Proxy enabled, Compose sets the UI trusted origin from
`OAUTH2_PROXY_PUBLIC_URL`, including its HTTPS
port. After changing this URL, update the Google authorized origin/redirect URI too
and run `docker compose up -d ui oauth2-proxy`. Changing
`DECIFLOW_CSRF_TRUSTED_ORIGINS` alone does not override the Compose setting.
Native networking and authentication are covered in the [native guide](docs/native.md).
See [authentication operations](docs/authentication.md#operations) for credential,
allow-list, and certificate changes.

## Limits

- No application file-size or line-count cap. SQLite stores accumulated results; memory still depends on active files, hosts, and individual event size. Disk retention is not automatic. See [Result storage](docs/result-storage.md).
  File reads are incremental. Chunks use an event count; each nonempty line currently forms one event.
  Automatic multiline event-boundary detection is not implemented.
- **Laya:** selected checkpoint; request windows and question budgets are in the [configuration reference](docs/configuration.md).
  The [official HTTP server](https://nandhakishorm.github.io/laya/http-api/#limits)
  also limits state to 50,000 characters and requests to 2 MiB; verify the deployed version.
  Truncated responses or missing truncation metadata are rejected.
- **Jev:** `jev-1.13.0`, [32k state + longest question, 64k full request](https://docs.typesafe.ai/models).
  The byte budget is a conservative guard, not a token count or acceptance guarantee.
- Rejected events retain their original text for review; other events continue.
  Local file read/UTF-8 errors stop the run. SSH read failures are recorded per
  Source/Host while other readers continue; completed results are retained.
- Each chunk makes one request. Engine concurrency settings default to 4 per run;
  timeouts are Laya 120s and Jev 30s. Higher client concurrency does not guarantee
  parallel inference or higher throughput; server capacity and admission limits apply.
- Realtime scans every 250ms after each discovery pass and waits for complete lines.
  SSH inputs reuse scan metadata; unchanged files get a one-second replacement check.
  Rotation leftovers are
  marked `incomplete`; line numbers reset on rotation. Rapid rotation or
  copy-truncate/regrowth can lose events. File deduplication does not remove duplicate
  contents; avoid matching both active logs and their rotated copies.
- Laya sends logs to your server; Jev sends them to TypeSafe and incurs API charges.
  Task history saves original logs, results, and Action outcomes to the data volume.
  Protect that volume and its backups, remove sensitive data before submission,
  and never commit `.env`. Public deployment needs authentication and
  usage limits.

`Ctrl+C` suspends active runs and preserves history. After restart, checkpointed
Batch and Realtime runs recover with their original IDs; paused runs stay paused.
Explicitly stopped runs and older runs without checkpoints do not restart automatically.
See [recovery requirements and limits](docs/tasks.md#recovery-after-a-server-restart).

## Appendix — Potential applications

Logs are the starting point. Extending input handling and decision criteria could
bring the same workflow to real-time `tcpdump` traffic monitoring or manufacturing
quality decisions based on sensor and inspection data. These applications require
additional integration and domain validation; image inspection also requires a
vision model.

## Run Without Docker

Choose the recommended [uv tool installation](docs/tool-install.md), or
[Git checkout native installation](docs/native.md) for local CPU and development.
Both support existing Laya/Jev and optional automatic OAuth2-Proxy execution.

## Appendix — Custom Docker images (optional)

Build from Laya **v0.4.1** only when you need your own image. Run the CPU **or** CUDA
build command for your target:

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

Replace the selected Laya service image in `docker-compose.yml` with your custom tag.
`cpu` installs CPU-only PyTorch; `cu130` means CUDA **13.0**. Select a CUDA build
supported by your GPU/driver and the Dockerfile's `TORCH_VERSION` using the
[PyTorch installation list](https://pytorch.org/get-started/previous-versions/).
Validate API compatibility when upgrading Laya.

## Development

For model evaluation commands and report fields, see [Laya log validation](docs/laya-validation.md).
Evaluate the selected Laya model on 36 labeled cases across five profiles:

```bash
uv run python -m scripts.evaluate_laya \
  --output /tmp/laya-validation.json
```

`scripts/evaluate_laya.py` is an optional evaluation utility, not needed for UI or
Compose startup. It calls your Laya server only and refuses paid Jev. The small
sample is not an accuracy guarantee.

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

Python 3.11 is the minimum supported version; Python 3.12 is recommended for
development and used by the Docker runtime. GitHub Actions runs the full pytest
suite on every push using Ubuntu with both Python 3.11 and 3.12, without a personal
`.env` or production credentials. View results in the
repository's **Actions → Pytest** page; **Run workflow** also starts a manual run.

Pytest automatically downloads and verifies OAuth2-Proxy v7.15.5 for Linux/macOS
amd64/arm64. OpenSSL and initial GitHub access are required. Release archives are
cached outside Git in `~/.cache/deciflow/test-tools/`; binaries and test certificates
use temporary storage. Set `OAUTH2_PROXY_BINARY` to use an existing executable offline.

Action tests prepare pinned `pip`, `setuptools`, and `wheel` wheels once per test
session using PyPI/index access and temporary storage. Action environments then
install offline from this local index using the Python version under test.
Tests use temporary data/log paths and generated Compose settings; no root access
or personal `.env` is required.

UI regression test (requires Node.js only for testing):

```bash
node --test tests/test_ui.mjs
```

Tests cover both providers without paid calls, input budgets, streaming,
cancellation, and file discovery/rotation. Keep both READMEs and actual/example
`.env` files synchronized; environment comments use English and Korean.

Local Laya installation and execution are covered in the
[native guide](docs/native.md#quick-start-local-cpu).

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)

### DeciFlow HTTP logs

Set `DECIFLOW_LOG_DIR=/var/log/deciflow` in `.env` and restart DeciFlow to write timestamped
`server.log` (startup and server errors) and `access.log` (client, request, HTTP status),
while retaining console logs. The default is `/var/log/deciflow`; missing directories
are created automatically with parent directories, requiring write permission. Relative paths start at the project directory. Each
file rotates at 10 MiB with 5 backups. Empty disables file logging. This does not
record browser interactions or classification results. Docker Compose already persists these logs in the `deciflow-logs` volume.
For direct host-directory access, replace that volume mount with a writable bind mount.
