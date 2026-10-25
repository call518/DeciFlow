# 설치

[English](INSTALL.md) | [소개](README.ko.md) | [문서 안내](docs/README.ko.md)

**DeciFlow**는 분류 UI/API, **Laya**는 Docker에서 추론을 담당합니다.
아래 설치 방식 **하나만 선택**하세요. 기본은 HTTP이며 **OAuth2-Proxy는 선택 사항**입니다.
필요할 때 [인증 문서](docs/authentication.ko.md)에서 별도로 추가합니다.
Jev는 대체 가능한 유료 엔진으로 이 데모에는 필요하지 않습니다.

Rocky Linux 8·9·10 호스트에 아래 도구와 Docker 실행 권한·외부 다운로드 연결이
준비되어 있다고 가정합니다.
호스트 방화벽과 Compose 바인드 마운트의 SELinux 라벨은 배포 환경에 맞춰 준비하세요.
명령은 DeciFlow 실행 계정으로 수행합니다. root 계정은 `sudo`를 생략합니다.

| 방식 | 필요한 도구 | 환경 파일 |
| --- | --- | --- |
| [1. PyPI: uv tool 또는 pip](#pypi) (권장) | Python 3.12, uv, Docker | `~/.config/deciflow/.env` |
| [2. Docker Compose](#docker-compose) | Git, Docker Compose 2.20+ | `<checkout>/.env` |
| [3. 소스 직접 실행](#direct-processes) | Python 3.12, uv, Git, Docker | `<checkout>/.env` |

기본 HTTP 수신 주소는 `DECIFLOW_BIND_HOST=0.0.0.0`입니다. OAuth2-Proxy를 추가할 때는
인증 우회를 막도록 `127.0.0.1`로 변경합니다.

결과의 호스트 식별자는 기본적으로 시스템 호스트명을 사용합니다. Docker에서는
`.env`의 `DECIFLOW_HOST`에 실제 호스트명을 지정하세요.
[호스트 식별](docs/configuration.ko.md#결과-호스트-식별)을 참고하세요.

설정 예시는 `.env.example`과 같은 순서입니다.
동일 출처 UI 요청은 별도 출처 설정 없이 동작합니다. 예외 설정은
[API 출처 보호](docs/authentication.ko.md#api-origin-protection)를 참고하세요.
데모의 Laya 키는 `changeme`이며 배포 시 변경하세요. 같은 `.env`를 Laya에도 전달하므로
별도 키 파일은 필요하지 않습니다.

<a id="pypi"></a>

## 1. PyPI: uv tool 또는 pip

### 설치와 초기화

uv가 없다면 먼저 설치합니다.

```bash
curl -LsSf https://astral.sh/uv/0.7.20/install.sh | sh
```

**선택 1 또는 선택 2 중 하나만 실행하세요. 둘 다 실행하지 않습니다.**

---

#### 선택 1: uv tool로 설치 (권장)

```bash
uv tool install --python 3.12 deciflow
```

명령을 찾지 못하면 `uv tool update-shell` 후 새 셸에서 실행하세요.

→ **[설치 완료: 다른 선택지는 생략하고 공통 초기화로 이동](#package-init)**

---

#### 선택 2: pip로 설치

전용 가상환경에 설치합니다.

```bash
python3.12 -m venv "$HOME/.venvs/deciflow"
source "$HOME/.venvs/deciflow/bin/activate"
python -m pip install deciflow
```

→ **[설치 완료: 다른 선택지는 생략하고 공통 초기화로 이동](#package-init)**

---

<a id="package-init"></a>

#### 공통 초기화

선택한 방법의 설치가 끝났다면 아래 공통 초기화를 진행합니다. **설정 검사 전에 데이터·로그 디렉터리가
없으면 `mkdir -p`로 만들고 실행 계정에 쓰기 권한을 부여하세요.** root 계정은
아래 `sudo`를 생략합니다.

```bash
deciflow init
sudo mkdir -p /var/lib/deciflow-data /var/log/deciflow
sudo chown "$(id -un):$(id -gn)" /var/lib/deciflow-data /var/log/deciflow
```

### `.env` 설정

`init`으로 생성된 **`~/.config/deciflow/.env`**의 기존 항목을 수정합니다.
같은 키를 중복 추가하지 마세요. 데이터는 `/var/lib/deciflow-data`, 로그는 `/var/log/deciflow`를 기본으로 사용합니다.

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

### Laya와 DeciFlow 기동

Laya를 Docker로 기동합니다. 모델 적재 후 `Ctrl+C`로 로그 보기만 종료합니다.
기존 Laya가 있다면 아래 컨테이너 대신 해당 URL·키를 사용하세요.

Docker가 없다면 먼저 설치하고 데몬을 기동합니다. 이미 준비되어 있다면 생략하세요.
root 계정은 `sudo`를 생략합니다.

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

**`http://YOUR_SERVER_IP:4000`**을 여세요. 설정 검사 실패 시 해당 항목을 해결한 뒤
기동합니다. 아래 명령으로 데모 입력 소스 파일을 직접 만듭니다. DeciFlow가 자동 생성하는
파일이 아니며, 운영 로그(`server.log`, `access.log`, `daemon.log`)와는 별개입니다.

```bash
cat > "$HOME/.config/deciflow/demo.log" <<'EOF'
127.0.0.1 - - [25/Oct/2026:12:00:00 +0900] "GET /health HTTP/1.1" 200 12
127.0.0.1 - - [25/Oct/2026:12:00:01 +0900] "GET /missing HTTP/1.1" 404 0
127.0.0.1 - - [25/Oct/2026:12:00:02 +0900] "POST /login HTTP/1.1" 401 0
EOF
realpath "$HOME/.config/deciflow/demo.log"
```

출력된 경로로 [데모 실행](#demo)을 진행하세요. 종료·기동은 `deciflow stop`,
`deciflow start --daemon`입니다. pip 방식은 해당 가상환경을 활성화합니다.
Laya는 `docker stop deciflow-laya` / `docker start deciflow-laya`로 별도 관리합니다.
HTTPS가 필요하면 [PyPI 인증 구성](docs/authentication.ko.md#pypi)을 따르세요.

→ **[이 방식 설치 완료: 다른 방식은 생략하고 데모 실행으로 이동](#demo)**

<a id="docker-compose"></a>

## 2. Docker Compose

### 준비와 설정

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
test -f .env || cp .env.example .env
chmod 600 .env
```

**`<checkout>/.env`**를 수정합니다.

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

### 기동과 확인

Compose가 DeciFlow와 Laya를 함께 기동합니다. 1번 방식의 단독 Laya 컨테이너를
동시에 기동하지 마세요.

Docker가 없다면 먼저 설치하고 데몬을 기동합니다. 이미 준비되어 있다면 생략하세요.
root 계정은 `sudo`를 생략합니다.

```bash
sudo curl -fsSL https://download.docker.com/linux/rhel/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

```bash
docker compose up -d --remove-orphans
docker compose logs -f laya-cpu
```

모델 적재 후 `Ctrl+C`로 로그 보기를 종료하고 **`http://YOUR_SERVER_IP:4000`**을 여세요.
[데모 실행](#demo)의 Source 경로는 **`/host-logs/sample-logs/access-100.log`**입니다.

종료·기동은 `docker compose stop` / `docker compose start`, `.env` 변경 후에는
`docker compose up -d --remove-orphans`를 사용합니다. 데이터는 이름 있는 볼륨에 보존합니다.
HTTPS가 필요하면 [Compose 인증 구성](docs/authentication.ko.md#docker)을 따르세요.

→ **[이 방식 설치 완료: 다른 방식은 생략하고 데모 실행으로 이동](#demo)**

<a id="direct-processes"></a>

## 3. 소스 직접 실행

### 준비와 설정

DeciFlow만 저장소에서 실행하고 Laya는 Docker를 사용합니다.
`laya` Python 추가 의존성이나 별도 Python 서버는 설치하지 않습니다.

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
test -f .env || cp .env.example .env
chmod 600 .env
uv sync --frozen
sudo mkdir -p /var/lib/deciflow-data /var/log/deciflow
sudo chown "$(id -un):$(id -gn)" /var/lib/deciflow-data /var/log/deciflow
```

**`<checkout>/.env`**를 수정합니다.

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

저장소의 `.env`로 Laya를 기동합니다.

Docker가 없다면 먼저 설치하고 데몬을 기동합니다. 이미 준비되어 있다면 생략하세요.
root 계정은 `sudo`를 생략합니다.

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

적재 후 `Ctrl+C`로 로그 보기를 종료하고 DeciFlow를 기동합니다.

```bash
uv run deciflow config test --config-dir "$PWD"
uv run deciflow start --daemon --config-dir "$PWD"
realpath sample-logs/access-100.log
```

**`http://YOUR_SERVER_IP:4000`**을 열고 출력된 절대 경로로 [데모 실행](#demo)을 진행합니다.
항상 `--config-dir "$PWD"`로 이 저장소의 설정을 선택하세요.
종료는 `uv run deciflow stop --config-dir "$PWD"`, 기동은 위 명령을 사용합니다.
데이터·로그는 `/var/lib/deciflow-data`·`/var/log/deciflow`에 남고 Laya는 Docker에서 별도 관리합니다.
HTTPS가 필요하면 [직접 실행 인증 구성](docs/authentication.ko.md#source)을 따르세요.

→ **[이 방식 설치 완료: 다른 방식은 생략하고 데모 실행으로 이동](#demo)**

<a id="demo"></a>

## 데모 실행

1. UI의 Decision Engine 상태가 정상인지 확인합니다.
2. **Sources**의 **Sample HTTP access**를 편집해 해당 방식의 파일 경로를 저장합니다.
3. **Tasks**에서 이름을 입력한 **Batch / Manual** Task를 만듭니다. Source·Criteria는
   **Sample HTTP access**, **Events/Chunk: 1**, **Action: None**을 선택합니다.
4. 저장·활성화 후 **Run**을 누릅니다. Main의 판정 결과와 새로고침 후 실행 재조회를
   확인합니다. 패키지 데모는 3개, 저장소 샘플은 100개 이벤트입니다.

도메인·인증서·Google 계정·Elasticsearch·SSH 구성은 필요하지 않습니다.
HTTP 접속에는 로그인이 없으므로 접근 범위는 환경에 맞게 제한하세요.

## 운영

Laya의 키 등 컨테이너 환경을 바꿨다면 `docker rm -f deciflow-laya` 후
해당 `docker run` 명령으로 재생성합니다. 단순 stop/start는 `.env`를 다시 읽지 않습니다.

- 패키지: `deciflow status`, 로그는 `/var/log/deciflow/`.
- 저장소: `uv run deciflow status --config-dir "$PWD"`, 로그는 `/var/log/deciflow/`.
- Compose: `docker compose ps`, `docker compose logs --tail=100 ui laya-cpu`.
- 최초 Laya 모델 다운로드·적재에는 시간이 걸립니다. `config test`의 엔진 연결 실패 시
  Laya 준비 상태를 확인하며 유료 Jev로 바꿀 필요는 없습니다.

전체 환경·저장소 설정은 [설정 문서](docs/configuration.ko.md), CUDA·기존 서버는
[Laya 문서](docs/laya.ko.md#laya-docker), 선택적 Docker Google 로그인은
[인증 문서](docs/authentication.ko.md)를 참고하세요.

