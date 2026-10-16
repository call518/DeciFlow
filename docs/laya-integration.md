# Laya integration

[English](laya-integration.md) | [한국어](laya-integration.ko.md) | [Documentation](README.md) | [README](../README.md)

## Request contract

DeciFlow sends one log chunk as `state` to `/v1/systemone` with three questions:
category (`choice`), urgency (`score`), and work-ticket need (`noul`). Both Laya and
Jev share the request construction, result validation, and UI behavior in
[`classifier.py`](../classifier.py). See [request/result JSON](results.md).

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

All three answers must pass validation. Category probabilities must cover all five
categories and sum approximately to one. Urgency requires the expected legend,
four valid probabilities, and a score matching their weighted sum. Ticket need is
a probability from zero to one. Missing/invalid answers fail the entire decision.

Successful results become Uncertain when selected category probability is below
70%, the highest-two probability gap is below 10 percentage points, or Laya reports
collapsed category options. Original predictions and probabilities are preserved.
Registered custom models also require matching `routing.model` confirmation.
See [review rules](usage.md#uncertainty-and-human-review).

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

## Evaluation and limits

Use the [evaluation guide](laya-validation.md) to compare model predictions with
labeled logs. The evaluator sends all three questions and reports category matches,
request failures, uncertainty counts, and a confusion matrix.

DeciFlow does not train or calibrate models, use native inference batching, or
check complete instruction preservation with the served tokenizer. Category
probabilities and review thresholds do not establish prediction accuracy.
The Docker Hub image's installed Laya version and model revisions must be checked
on the running server; repository configuration alone does not identify them.
The upstream references below describe Laya v0.4.1 behavior.

## Sources

- [Upstream README: budgets and honest limits](https://github.com/NandhaKishorM/laya#honest-limits)
- [HTTP API: request controls, limits, devices, concurrency](https://nandhakishorm.github.io/laya/http-api/)
- [v0.4.1 HTTP implementation](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/serve.py)
- [v0.4.1 Agent: rendering and usage](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/agent.py)
- [v0.4.1 Router: routing, preload, batch](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/router.py)
- [Token-budget tuning guide](https://nandhakishorm.github.io/laya/langchain/#7-widening-the-token-budget-for-many-options)
