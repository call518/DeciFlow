# Laya Integration and Validation

[English](laya.md) | [한국어](laya.ko.md) | [Documentation](README.md) | [README](../README.md)

## Request contract

DeciFlow sends a TEXT chunk or text extracted from JSONL as `state`, with the
Criteria profile's variable question map in `questions`. Question count, names,
and the mix of `choice`, `score`, and `noul` vary by profile. The system profile's
category, urgency, and ticket questions are one example. Laya and Jev share
request construction, result validation, and UI behavior in
[`classifier.py`](../deciflow/classifier.py). See [request/result JSON](results.md)
and [Criteria](criteria.md).

| Setting | DeciFlow behavior |
| --- | --- |
| `LAYA_MODEL` | Explicit built-in or server-registered model name; no automatic model selection |
| `LAYA_MAX_TOKENS` | Sent as max_len. Blank selects 512 for English or 8192 for Multilingual/Typed-decisions. Custom models require an explicit value |
| `LAYA_HEAD_TOKENS` | Sent as head_max_len; default 256, positive and below the selected total window |
| `LAYA_CONCURRENCY` | Maximum simultaneous requests per run; default 4. File Batch sends individual requests, not an inference batch |

Jev receives its own model name and no Laya token-budget fields. Engine selection
is explicit; DeciFlow never falls back automatically to paid Jev.

Multi-host Tasks use the same request contract: host identity stays in result
metadata and is not added to `state`. Concurrency is shared across the run, while
host readers receive rotating opportunities. See [Tasks](tasks.md#multiple-source-hosts).

## Input and response validation

Budgets are caps, not fixed allocations. Actual log space depends on the rendered
question and sequence overhead; `max_len - head_max_len` is not an exact token
counter. Increasing the question budget can reduce log space.

Laya responses must contain a Boolean `usage.truncated`. True or missing/invalid
truncation metadata causes rejection, with the original log retained.
`state_tokens_dropped` and `truncated_questions`, when provided, describe log/state
truncation, not shortened question instructions. False does not guarantee that
all instructions or option descriptions were preserved.

The local `laya_server.py` adapter also reports `usage.criteria_tokens_dropped`
when instruction or option tokens are shortened. DeciFlow flags these results for
review. The standard Compose server may not provide this metadata.

Every answer requested by the profile must pass validation. Choice probabilities
must match that profile's options and sum approximately to one. Score answers
must match the profile's legend, probabilities, and weighted score; Noul answers
must contain a probability from zero to one. Missing or invalid answers fail the
whole request.

Choice checks include selected probability below 70%, a highest-two gap below
10 percentage points, and Laya-reported option collapse. Score and Noul use their
own type-specific review rules; one category probability does not assess the entire
profile. Original predictions and probabilities are preserved. Custom models also
require matching `routing.model`. See [review rules](usage.md#uncertainty-and-human-review).

## Server settings: configure on the Laya host

| Setting | Effect / operational guidance |
| --- | --- |
| `LAYA_MAX_TOKEN_BUDGET` | Default 8192; caps both request budget overrides. Exceeding it returns 422. Does not enlarge encoder capacity |
| `LAYA_MAX_CONCURRENT` | Default 16 admitted requests; excess returns 503. Inference worker count is one in v0.4.1 |
| `LAYA_THREADS` | CPU intra-op threads; keep at or below physical core count. Not a CUDA concurrency switch |
| `LAYA_PRELOAD`, `LAYA_MODELS`, `LAYA_MAX_LOADED` | Startup loading and residency. Preloading raises the residency cap to fit loaded models, so the three-model preload does not need an extra `LAYA_MAX_LOADED=3` |
| `LAYA_IDLE_UNLOAD_SECONDS` | Default 0 keeps models resident; enabling unload saves residency at the cost of subsequent cold loads |
| `LAYA_DEVICE` | Device preference. Verify authenticated `/health` actual device and per-checkpoint fallbacks; requesting CUDA alone does not prove CUDA execution |
| `LAYA_JEV_STRICT` | Keep 0 for DeciFlow: strict mode removes required truncation metadata and routing details |
| `LAYA_EXTRA_MODELS` | Registers named custom checkpoints. DeciFlow accepts registered names with an explicit total token window |

Do not copy these server settings into DeciFlow's `.env` expecting the remote
container to change. DeciFlow's `LAYA_CONCURRENCY` is per-run; aggregate demand
from multiple DeciFlow runs/nodes shares the server's admission limit.

For Compose deployments, configure server variables in the selected Laya service's
`environment` in `docker-compose.yml`, then recreate that service. Only explicitly
interpolated settings such as `LAYA_API_KEY` are read from `.env` for Laya.

## Limits

DeciFlow does not train or calibrate models, use native inference batching, or
check complete instruction preservation with the served tokenizer. Category
probabilities and review thresholds do not establish prediction accuracy.
The Docker Hub image's installed Laya version and model revisions must be checked
on the running server; repository configuration alone does not identify them.
The upstream references below describe Laya v0.4.1 behavior.

<a id="evaluation"></a>

## Model Evaluation

Use `scripts/evaluate_laya.py` to evaluate the configured Laya model against
labeled logs. Each request sends the log as `state` with category (`choice`),
urgency (`score`), and work-ticket need (`noul`) questions. The classifier validates
all three answers; expected-label comparisons measure **category only**.
The script does not measure urgency or ticket-probability accuracy and refuses Jev.

### Run an evaluation

Set `DECISION_ENGINE=laya` and choose `LAYA_MODEL` in `.env`. The model must be
available on the Laya server. Choose one execution method:

- **Docker Compose:** run inside the UI container, where `http://laya:8000/v1/systemone`
  reaches the selected CPU or CUDA service.
- **Local Python:** run from the cloned repository with uv and project dependencies
  installed. Set `LAYA_API_URL` to a reachable Laya address; use
  `http://127.0.0.1:8000/v1/systemone` for Laya on the same host.

Docker Compose:

```bash
docker compose exec ui uv run --no-sync python -m scripts.evaluate_laya \
  --output /tmp/laya-validation.json
docker compose cp ui:/tmp/laya-validation.json /tmp/laya-validation.json
```

Local Python:

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

By default, the evaluator uses [36 synthetic cases across five profiles](../tests/fixtures/log_evaluation.json)
and caps concurrent requests at two. It uses the bundled profile definitions in
[`deciflow/profiles/`](../deciflow/profiles/), not profiles edited and saved through the UI.
For UI-edited criteria, put the labeled logs in a UTF-8 file, register a Local File
Source, and run a Batch Task with that criteria profile. Inspect its results in Main.

To compare prepared models, repeat `--model` (append these options to the chosen command):

```text
--model english --model multilingual --model typed-decisions
```

Use `--cases PATH` for a UTF-8 JSON list of labeled cases:

```json
[
  {
    "log": "application: database connection failed",
    "expected": "error",
    "profile": "617706a3-c4ee-426f-81cf-7f5d80ecf67a"
  }
]
```

Each case requires log text and one expected category: `normal`, `warning`,
`error`, `security`, or `other`. `profile` is the bundled Criteria UUID and defaults to Sample General System. The cases path must be readable in the environment running the evaluator.

### Read the report

The generated JSON contains UTC `evaluatedAt` and a `reports` list with one entry
per model:

| Field | Meaning |
| --- | --- |
| `model` | Requested checkpoint name |
| `total` / `correct` | Case count / category predictions matching the expected label |
| `failed` | Rejected requests, invalid answers, and connection/API errors |
| `uncertain` | Successful predictions flagged Uncertain |
| `certain` / `certainCorrect` | Successful predictions without Uncertain / matching labels within that group |
| `confusionMatrix` | Expected-category rows and predicted-category columns, including failed |
| `rows` | Input case, match flag, and classifier result including all three questions and answers when successful |

Certain means the prediction passes DeciFlow's probability and option-integrity
checks; it does not prove correctness. Use representative labeled logs to assess
misclassification and review workload. Synthetic cases are regression probes,
not a production accuracy estimate. Model, criteria, and input budgets affect
results; keep them consistent when comparing runs.

See [request/result JSON](results.md) for the response schema and
[uncertainty rules](usage.md#uncertainty-and-human-review) for review thresholds.


## Sources

- [Upstream README: budgets and honest limits](https://github.com/NandhaKishorM/laya#honest-limits)
- [HTTP API: request controls, limits, devices, concurrency](https://nandhakishorm.github.io/laya/http-api/)
- [v0.4.1 HTTP implementation](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/serve.py)
- [v0.4.1 Agent: rendering and usage](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/agent.py)
- [v0.4.1 Router: routing, preload, batch](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/router.py)
- [Token-budget tuning guide](https://nandhakishorm.github.io/laya/langchain/#7-widening-the-token-budget-for-many-options)

## Docker Laya Reference

<a id="laya-docker"></a>

#### Use the Laya decision engine

Connect to an existing shared Laya server, or set up one on a remote host below.
If a server is already available, skip setup and configure DeciFlow.

Use [docker-compose.yml](../docker-compose.yml) from the cloned repository on the Laya
host. CPU is the default in `.env.example`; a compatible NVIDIA GPU can improve
inference performance. Actual performance varies with hardware and workload.
Compose validates the complete `.env`, including OAuth settings, even when selecting
only a Laya service. Complete [deployment setup](authentication.md) first.

##### CPU execution

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

##### Optional: GPU acceleration (CUDA)

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

##### Check and manage

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

##### DeciFlow connection

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
For execution without Docker, follow the [native guide](../INSTALL.md#direct-processes).
