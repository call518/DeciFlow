# Installation

[한국어](INSTALL.ko.md) | [Overview](README.md) | [Documentation](docs/README.md)

**DeciFlow** serves the classification UI/API; **Laya** runs inference in Docker.
Choose **one** installation method below. Start with HTTP; **OAuth2-Proxy is
optional** and is configured separately in [Authentication](docs/authentication.md).
Jev is an alternative paid engine, not required for this demo.

Assumes a Rocky Linux 8/9/10 host with the tools below, Docker access, and outbound
download access already prepared. Prepare the host firewall and, for Compose bind mounts, SELinux
labels to match your deployment. Commands run as the DeciFlow owner. Omit `sudo` when running as root.

| Method | Required Tools | Environment File |
| --- | --- | --- |
| [1. PyPI: uv tool or pip](#pypi) (Recommended) | Python 3.12, uv, Docker | `~/.config/deciflow/.env` |
| [2. Docker Compose](#docker-compose) | Git, Docker Compose 2.20+ | `<checkout>/.env` |
| [3. Run from Source](#direct-processes) | Python 3.12, uv, Git, Docker | `<checkout>/.env` |

HTTP defaults to `DECIFLOW_BIND_HOST=0.0.0.0`. When adding OAuth2-Proxy, change it
to `127.0.0.1` to prevent bypassing authentication.

Settings follow the order in `.env.example`.
Same-origin UI requests work without additional origin settings. See
[API origin protection](docs/authentication.md#api-origin-protection) for exceptions.
The demo uses `changeme` as the Laya key; change it for deployment. The same `.env`
is passed to Laya, so no second key file is needed.

<a id="pypi"></a>

## 1. PyPI: uv tool or pip

### Install and Initialize

If uv is missing, install it first.

```bash
curl -LsSf https://astral.sh/uv/0.7.20/install.sh | sh
```

**Run Option 1 OR Option 2. Do not run both.**

---

#### Option 1: Install with uv tool (Recommended)

```bash
uv tool install --python 3.12 deciflow
```

If the executable is missing, run `uv tool update-shell` and open a new shell.

→ **[Installation complete: skip the other option and go to Shared Initialization](#package-init)**

---

#### Option 2: Install with pip

Install in a dedicated virtual environment:

```bash
python3.12 -m venv "$HOME/.venvs/deciflow"
source "$HOME/.venvs/deciflow/bin/activate"
python -m pip install deciflow
```

→ **[Installation complete: skip the other option and go to Shared Initialization](#package-init)**

---

<a id="package-init"></a>

#### Shared Initialization

After your chosen installation finishes, run the shared initialization below. **Before config testing, create
missing data/log directories with `mkdir -p` and grant the running account write
access.** Omit `sudo` when running as root:

```bash
deciflow init
sudo mkdir -p /var/lib/deciflow-data /var/log/deciflow
sudo chown "$(id -un):$(id -gn)" /var/lib/deciflow-data /var/log/deciflow
```

### Edit `.env`

Edit **`~/.config/deciflow/.env`** created by `init`. Replace its existing entries;
do not append duplicate keys. Data defaults to `/var/lib/deciflow-data` and logs to `/var/log/deciflow`.

```dotenv
DECISION_ENGINE=laya
PORT=4000
DECIFLOW_BIND_HOST=0.0.0.0
OAUTH2_PROXY_ENABLED=false
DECIFLOW_LOG_DIR=/var/log/deciflow
LAYA_API_URL=http://127.0.0.1:8000/v1/systemone
LAYA_API_KEY=changeme
LAYA_MODEL=multilingual
LAYA_HEAD_TOKENS=512
DECIFLOW_DATA_DIR=/var/lib/deciflow-data
```

### Start Laya and DeciFlow

Start Laya in Docker. When loading finishes, leave the log viewer with `Ctrl+C`
(the container keeps running). Use an existing Laya URL/key instead if available.

If Docker is not installed, install it and start the daemon first. Skip if already prepared.
Omit `sudo` when running as root.

```bash
sudo curl -fsSL https://download.docker.com/linux/rhel/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

```bash
docker run -d --name deciflow-laya --restart unless-stopped \
  -p 127.0.0.1:8000:8000 --env-file "$HOME/.config/deciflow/.env" \
  -e LAYA_HOST=0.0.0.0 -e LAYA_DEVICE=cpu \
  -e LAYA_MODELS=multilingual -e LAYA_PRELOAD=1 \
  -v deciflow-laya-cache:/home/laya/.cache/huggingface \
  call518/deciflow-laya-cpu:0.0.1 laya-serve
docker logs -f deciflow-laya
```

```bash
deciflow config test
deciflow start --daemon
deciflow status
```

Open **`http://YOUR_SERVER_IP:4000`**. If the config test fails, resolve its failed
items before starting. Create the demo input source file explicitly below. DeciFlow does
not generate this sample automatically; it is separate from its operational logs
(`server.log`, `access.log`, and `daemon.log`).

```bash
cat > "$HOME/.config/deciflow/demo.log" <<'EOF'
127.0.0.1 - - [25/Oct/2026:12:00:00 +0900] "GET /health HTTP/1.1" 200 12
127.0.0.1 - - [25/Oct/2026:12:00:01 +0900] "GET /missing HTTP/1.1" 404 0
127.0.0.1 - - [25/Oct/2026:12:00:02 +0900] "POST /login HTTP/1.1" 401 0
EOF
realpath "$HOME/.config/deciflow/demo.log"
```

Use the printed path in [Run the Demo](#demo). Stop/start with `deciflow stop`
and `deciflow start --daemon`. Keep the pip environment active when applicable.
Operate Laya independently with `docker stop deciflow-laya` / `docker start deciflow-laya`.
For optional HTTPS, follow [PyPI authentication](docs/authentication.md#pypi).

→ **[Method complete: skip other methods and go to Run the Demo](#demo)**

<a id="docker-compose"></a>

## 2. Docker Compose

### Prepare and Configure

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
test -f .env || cp .env.example .env
chmod 600 .env
```

Edit **`<checkout>/.env`**:

```dotenv
COMPOSE_PROFILES=cpu
DECISION_ENGINE=laya
PORT=4000
DECIFLOW_BIND_HOST=0.0.0.0
OAUTH2_PROXY_ENABLED=false
DECIFLOW_LOG_DIR=/var/log/deciflow
LAYA_API_URL=http://laya:8000/v1/systemone
LAYA_API_KEY=changeme
LAYA_MODEL=multilingual
LAYA_HEAD_TOKENS=512
DECIFLOW_DATA_DIR=/var/lib/deciflow-data
```

### Start and Verify

Compose starts both DeciFlow and Laya; do not start the standalone Laya container
from method 1 alongside it.

If Docker is not installed, install it and start the daemon first. Skip if already prepared.
Omit `sudo` when running as root.

```bash
sudo curl -fsSL https://download.docker.com/linux/rhel/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

```bash
docker compose up -d --remove-orphans
docker compose logs -f laya-cpu
```

After model loading, exit log viewing with `Ctrl+C` and open
**`http://YOUR_SERVER_IP:4000`**. In [Run the Demo](#demo), use Source path
**`/host-logs/sample-logs/access-100.log`**.

Stop/start with `docker compose stop` / `docker compose start`; after `.env`
changes use `docker compose up -d --remove-orphans`. Named volumes preserve data.
For optional HTTPS, follow [Compose authentication](docs/authentication.md#docker).

→ **[Method complete: skip other methods and go to Run the Demo](#demo)**

<a id="direct-processes"></a>

## 3. Run from Source

### Prepare and Configure

DeciFlow runs from the checkout; Laya still runs in Docker. The `laya` Python
extra and a second native Python process are unnecessary.

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
test -f .env || cp .env.example .env
chmod 600 .env
uv sync --frozen
sudo mkdir -p /var/lib/deciflow-data /var/log/deciflow
sudo chown "$(id -un):$(id -gn)" /var/lib/deciflow-data /var/log/deciflow
```

Edit **`<checkout>/.env`**:

```dotenv
COMPOSE_PROFILES=
DECISION_ENGINE=laya
PORT=4000
DECIFLOW_BIND_HOST=0.0.0.0
OAUTH2_PROXY_ENABLED=false
DECIFLOW_LOG_DIR=/var/log/deciflow
LAYA_API_URL=http://127.0.0.1:8000/v1/systemone
LAYA_API_KEY=changeme
LAYA_MODEL=multilingual
LAYA_HEAD_TOKENS=512
DECIFLOW_DATA_DIR=/var/lib/deciflow-data
```

Start Laya with the checkout's `.env`:

If Docker is not installed, install it and start the daemon first. Skip if already prepared.
Omit `sudo` when running as root.

```bash
sudo curl -fsSL https://download.docker.com/linux/rhel/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

```bash
docker run -d --name deciflow-laya --restart unless-stopped \
  -p 127.0.0.1:8000:8000 --env-file "$PWD/.env" \
  -e LAYA_HOST=0.0.0.0 -e LAYA_DEVICE=cpu \
  -e LAYA_MODELS=multilingual -e LAYA_PRELOAD=1 \
  -v deciflow-laya-cache:/home/laya/.cache/huggingface \
  call518/deciflow-laya-cpu:0.0.1 laya-serve
docker logs -f deciflow-laya
```

After loading, leave the log viewer with `Ctrl+C`, then start DeciFlow:

```bash
uv run deciflow config test --config-dir "$PWD"
uv run deciflow start --daemon --config-dir "$PWD"
realpath sample-logs/access-100.log
```

Open **`http://YOUR_SERVER_IP:4000`** and use the printed absolute path in
[Run the Demo](#demo). Always select this checkout with `--config-dir "$PWD"`.
Stop with `uv run deciflow stop --config-dir "$PWD"`; start with the command above.
Data/logs stay in `/var/lib/deciflow-data` / `/var/log/deciflow`. Laya is managed separately in Docker.
For optional HTTPS, follow [direct-process authentication](docs/authentication.md#source).

→ **[Method complete: skip other methods and go to Run the Demo](#demo)**

<a id="demo"></a>

## Run the Demo

1. Confirm healthy Decision Engine status in the UI.
2. In **Sources**, edit **Sample HTTP access** and save your method's file path.
3. In **Tasks**, create a named **Batch / Manual** Task: Source and Criteria
   **Sample HTTP access**, **Events/Chunk: 1**, **Action: None**.
4. Save, enable, and **Run**. Confirm decisions appear in Main and reopen the run
   after refreshing. The package demo has 3 events; checkout samples have 100.

No domain, certificate, Google account, Elasticsearch, or SSH configuration is
needed for this demo. HTTP access has no login; restrict reachability appropriately.

## Operations

If Laya container settings such as its key change, use `docker rm -f deciflow-laya`
and rerun its `docker run` command. A simple stop/start does not reread `.env`.

- Package: `deciflow status`; logs under `/var/log/deciflow/`.
- Checkout: `uv run deciflow status --config-dir "$PWD"`; logs under `/var/log/deciflow/`.
- Compose: `docker compose ps` and `docker compose logs --tail=100 ui laya-cpu`.
- Laya startup takes time on the first model download. A failed `config test`
  engine connection is not a reason to switch to paid Jev.

See [Configuration](docs/configuration.md) for environment/storage settings,
[Laya](docs/laya.md#laya-docker) for CUDA/existing servers, and
[Authentication](docs/authentication.md) for optional Docker-based Google sign-in.

