# Development and Releases

[한국어](development.ko.md) | [Project Overview](../README.md) | [Installation](../INSTALL.md)

Run development commands from a Git checkout prepared with
[direct-process installation](../INSTALL.md#direct-processes). Use the project uv
environment; the installed PyPI command alone does not include this test checkout.

Maintainers publish matching tag versions to TestPyPI and PyPI, then create a
GitHub Release with commit messages since the previous published Release through
the [tag release workflow](development.md#publish-from-a-git-tag).

Model evaluation commands, reports, and limits are in [Laya validation](laya.md#evaluation).

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

See [authentication tests](#authentication-tests) for OAuth2-Proxy downloads and offline preparation.

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
[native guide](../INSTALL.md#direct-processes).

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)

## Publish from a Git Tag

Maintainers publish with `.github/workflows/pypi-publish.yml`. A pushed tag starts
Python 3.12 tests, builds an sdist and wheel, verifies their versions against the
tag, and tests the installed wheel. The same artifacts are uploaded to **TestPyPI
first**, then **PyPI** only after TestPyPI succeeds. A final, separate job creates
a GitHub Release with English headings for the same tag only after PyPI succeeds. Normal branch
pushes do not publish packages or Releases; the separate pytest workflow checks
Python 3.11 and 3.12.

`pyproject.toml` uses `dynamic = ["version"]` and Hatch's `hatch-vcs` plugin
(backed by `setuptools-scm`). A clean `0.5.7` or `v0.5.7` tag produces package
version `0.5.7`; these are examples, not a selected release version. Canonical
prerelease tags such as `0.5.7rc1` are also accepted and publish to both indexes.
Commits after a tag or a modified checkout produce development versions. CI fetches
full Git history so version detection works. No manual version edit or API token
is needed. Install Git when building from a checkout; published sdists retain
version metadata so wheel builds from an sdist do not need Git history.

Before the first tag push:

1. On GitHub, configure repository **Settings → Environments** named `testpypi`
   and `pypi`. Ensure any deployment restrictions allow release tags. Required
   reviewers, if configured, pause the corresponding publishing job for approval.
2. On **each** index, register a Trusted Publisher with project name `deciflow`,
   owner `call518`, repository `DeciFlow`, workflow `pypi-publish.yml`, and its
   matching environment (`testpypi` or `pypi`). A Pending Publisher creates the
   project on the first successful upload; it does not reserve the project name.
3. Commit the release changes, including this workflow, and create and push the
   chosen version tag on that commit. Pushing an old commit without this workflow
   does not use the new release process.

Package publishing uses GitHub OIDC with `id-token: write` only in the index
publishing jobs. Only the GitHub Release job receives `contents: write` and uses
the automatically provided `GITHUB_TOKEN`; no personal token or repository-wide
write default is required. The workflow does not create tags or commits.

Release notes collect **full commit messages**, including merge commits and breaking
change descriptions, in oldest-first topological order with commit links. The range
starts after the most recently **published GitHub Release**, not the preceding Git
tag. Published prereleases count as a previous Release; drafts and the current tag
are excluded. Tags without a Release do not narrow the range. With no published
Release, all history reachable from the current tag is included. Commit messages
are preserved verbatim rather than translated or summarized.

The Release job checks that the remote tag, local tag, and checked-out commit match,
and stops if the previous Release tag is missing or is not an ancestor. Existing
published Releases are left unchanged on reruns; an existing draft for the same tag
requires manual review. Tags ending in `aN`, `bN`, or `rcN` create prereleases and
are not marked Latest. GitHub selects Latest automatically for normal Releases.
Only Release jobs are serialized, with up to 100 pending jobs retained. Push version
tags one at a time; concurrent or out-of-order publishing can make a newer Release
an invalid baseline for an older tag, which fails safely rather than guessing.

Existing package versions cannot be overwritten. If TestPyPI succeeds but PyPI fails,
fix the cause and rerun the failed job in the same workflow run to reuse its artifacts.
If only GitHub Release creation fails, rerun only the failed Release job; do not rerun
successful package uploads. A Release failure does not roll back packages already
published to either index. Installing or running local checks does not upload anything;
`python3 -m scripts.publish_release TAG` is a publishing command for the workflow.


## Verify a Distribution

From the Git checkout, build an sdist and wheel, then test the wheel:

```bash
uv build
uv run python scripts/check_distribution.py dist/*.whl
```

Use an output directory containing only the wheel being tested. The check creates
an isolated temporary uv tool installation outside the checkout, verifies bundled
UI resources and private-file exclusion, and starts, restarts, and stops the installed server.
It requires dependency download access and makes no inference requests. GitHub
Actions runs this check after pytest on both Python 3.11 and 3.12.


<a id="authentication-tests"></a>

## Authentication Smoke Tests

Run from a prepared Git checkout root.

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
the [manual access checks](authentication.md#verify).


<a id="storage"></a>

## Storage Implementation

`ResultRepository` is the result interface; `open_result_store()` selects its only
current implementation, `SQLiteResultStore`. Configuration SQL is in `config_store.py`.
No PostgreSQL/MySQL implementation or connection setting exists. Operational backups
belong in [Configuration](configuration.md#storage); the external JSON contract is
in [Result JSON](results.md).

- Definitions are stored per internal ID, with nested JSON payloads. Bundled profiles
  under `deciflow/profiles/` are read-only seeds; application startup initializes samples.
- `result_decisions` indexes decision selections/buckets and Choice certainty. Filters
  and cursor queries run on the server; the browser retains only its current page.
  Substring search can still scan many rows; constant CPU cost is not guaranteed.
- Each live job caches at most 128 recent events; completed objects are evicted beyond
  32 cached jobs while durable history remains. Active files/hosts, event size,
  concurrency, and SQLite/OS caches consume memory without retaining all accumulated results.
- Aggregates update incrementally. `processing_times` stores one row per distinct
  duration per run for exact Median/P95/P99. Throughput is successful results per active
  classification second. Run metrics are independent of display filters; charts
  aggregate all matching results.
- Exports stream bounded batches up to the starting cursor. Reviewed exports use a
  partial index and return full results with `reviewerDecisions` without a second result store.
- Inserting `pending_work` and advancing `source_checkpoints` share one transaction,
  as do result insertion and queue removal. Action intent/outcomes are journaled
  separately to avoid repeating uncertain external effects. Criteria/Action snapshots
  remain fixed for the run.
- Input text is stored once; repeated Criteria and diagnostic questions are shared
  by hash in `result_contexts`. Reads, reviews, replay, and exports restore definitions
  with bounded caching. Standalone Action/export JSON retains required definitions.
  `log_folded` is a deliberate search copy.
- SQLite uses WAL, FULL synchronous commits, and a 2 MiB connection cache. Task deletion
  removes histogram rows and shared contexts. Reads do not rewrite stored originals
  or Elasticsearch documents.

## Docker Runtime and Image Reference

#### DeciFlow Docker

Choose Docker or the [native installation](../INSTALL.md#direct-processes). The DeciFlow host needs
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

<a id="docker-runtime"></a>

##### Dockerfile and Compose responsibilities

[`Dockerfile`](../Dockerfile) builds the UI runtime from `python:3.12-slim`, installs
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
For SSH Key management and remote file requirements, see [Sources](sources.md).

HDFS Sources offer **HDFS (Native)** and **HDFS (WebHDFS)** for Batch reads of
UTF-8 TEXT and JSONL files. See
[HDFS configuration and limits](sources.md#hdfs) for cluster mounts, authentication,
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

[`docker-compose.yml`](../docker-compose.yml) supplies the runtime configuration:

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

##### Mount host log directories

Host `/var/log` and repository `sample-logs` are mounted read-only at
`/host-logs/var/log` and `/host-logs/sample-logs`. For other logs, add a mount under
`services.ui.volumes` in `docker-compose.yml`:

```yaml
      - /your/logs:/host-logs/custom:ro
```

Apply mount changes with `docker compose up -d ui`. Recreating the UI interrupts
active executions; Task history remains in the data volume. In the UI, use the container
path `/host-logs/custom/app.log`. The process needs permission to read host files.

##### Connection settings and restart

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
and run `docker compose up -d ui oauth2-proxy`. Additional trusted UI origins can be set with
`DECIFLOW_CSRF_TRUSTED_ORIGINS`; they do not replace the public URL.
Native networking and authentication are covered in the [native guide](../INSTALL.md#direct-processes).
See [authentication operations](authentication.md#verify) for credential,
allow-list, and certificate changes.

### Appendix — Custom Docker images (optional)

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

### Update or Stop Docker

Use `docker compose stop` to stop containers, or `docker compose down` to remove
the stack's containers and networks. `down` preserves named data volumes; do not add
`--volumes` when results must be retained. Stop executions and back up the required
data/settings before updating the source. From the repository root:

```bash
docker compose down
git pull --ff-only
docker compose up -d --remove-orphans
```

Preserve the existing `.env` and review changed settings instead of copying it again.
The configured `pull_policy: always` checks images; the UI uses the updated mounted
source. Recheck engine readiness and refresh the UI. Dockerfile changes additionally
require an image build; follow [runtime image details](#docker-runtime).
