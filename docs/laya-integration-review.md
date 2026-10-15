# Laya integration review

Reviewed on 2026-10-10 against upstream documentation and v0.4.1 source.
This is a configuration/code review, not a new performance or accuracy benchmark.
The Docker Hub image's installed version and loaded checkpoint revisions must be
checked separately; repository documentation does not establish image contents.

## Current request contract

DeciFlow sends one chunk and three questions (five-category `choice`, urgency
`score`, and work-ticket need `noul`) to
`/v1/systemone`, with an explicit model and token budgets. File Batch mode sends
individual requests concurrently; it does not call `/v1/systemone/batch`.
Jev uses the shared classification/validation/UI path without Laya-only controls.

| Control | Upstream behavior | DeciFlow / recommendation |
| --- | --- | --- |
| `model` | Pins the checkpoint; overrides automatic routing | Explicit built-in model selected by `LAYA_MODEL`; no automatic type/model selection |
| `max_len` | Per-call total token window; inherited when omitted | Explicit 512 for English, 8192 for the other built-ins; future tuning should validate actual chunks, not just raise the cap |
| `head_max_len` | Per-call question/option rendering budget | `.env` `LAYA_HEAD_TOKENS` becomes this exact JSON field; default 256 |
| `lang`, `lang_guess`, `task` | Language/workflow routing and, where applicable, language-specific inference behavior | Not sent; fixed model selection remains deliberate. These are not general accuracy controls |
| `min_confidence` | Marks abstention while preserving the answer; uses `answer_confidence`, falling back to `confidence` | Not sent. DeciFlow uses selected category probability <70% or top-two gap <10 percentage points for Uncertain; avoid two unexplained thresholds |
| `batch_size`, `sort_by_length` | Batch forward-pass sizing and padding optimization | Not used on current single-request path; do not add them to `/v1/systemone` requests |

Budgets are **caps**, not fixed allocations. Actual state room depends on the
rendered head and sequence overhead. With many options, rendering floors can even
make the head exceed the nominal head budget. `max_len - head_max_len` is not an
exact token counter. Current five-category questions avoid the high-cardinality
case, but long descriptions can still be shortened.

`usage.truncated`, `state_tokens_dropped`, and `truncated_questions` describe
state truncation; the last field names questions whose state was truncated, not
questions whose instructions were shortened. DeciFlow rejects truncated states
and preserves the original event. It retains `usage.options` in `providerResponse`
when the server reports collapsed options, and now surfaces that as an Uncertain/review reason. No `usage.truncated=false` guarantee covers the entire question.

## Server settings: configure on the Laya host

| Setting | Effect / operational guidance |
| --- | --- |
| `LAYA_MAX_TOKEN_BUDGET` | Default 8192; caps both request budget overrides. Exceeding it returns 422. Does not enlarge encoder capacity |
| `LAYA_MAX_CONCURRENT` | Default 16 admitted requests; excess returns 503. Inference worker count remains one in v0.4.1 |
| `LAYA_THREADS` | CPU intra-op threads; keep at or below physical core count. Not a CUDA concurrency switch |
| `LAYA_PRELOAD`, `LAYA_MODELS`, `LAYA_MAX_LOADED` | Startup loading and residency. Preloading raises the residency cap to fit loaded models, so the existing three-model preload does not need an extra `LAYA_MAX_LOADED=3` |
| `LAYA_IDLE_UNLOAD_SECONDS` | Default 0 keeps models resident; enabling unload saves residency at the cost of subsequent cold loads |
| `LAYA_DEVICE` | Device preference. Verify authenticated `/health` actual device and per-checkpoint fallbacks; requesting CUDA alone does not prove CUDA execution |
| `LAYA_JEV_STRICT` | Keep 0 for DeciFlow: strict mode removes required truncation metadata and routing details |
| `LAYA_EXTRA_MODELS` | Registers named custom checkpoints. Upstream supports them; DeciFlow now supports registered names with an explicit total token window |

Do not copy these server settings into DeciFlow's `.env` expecting the remote
container to change. DeciFlow's `LAYA_CONCURRENCY` is per-run; aggregate demand
from multiple DeciFlow runs/nodes shares the server's admission limit.

## Implementation status

Implemented after this review:

- Collapsed `usage.options.category` now sets `collapsed_options`, Uncertain,
  and Needs review; UI explains the reason. Category/probabilities remain intact.
- `LAYA_MAX_TOKENS` controls actual `max_len`. Built-in defaults remain unchanged;
  registered custom model names require an explicit validated window.
- Evaluation now covers five profiles with 36 synthetic cases and reports a
  confusion matrix, failures, Uncertain, and correct predictions among Certain.
  Use `--cases` for domain data. This does not establish production accuracy.

Still deferred: exact instruction/description preservation checks with the
served tokenizer revision, native inference batching, training, and calibration.
Option-collapse metadata detects one integrity problem, not every shortened
instruction. No speedup or accuracy gain has been measured for this change.

## Improvement priorities

1. **Accuracy first:** grow the labeled log fixtures and evaluate every served
   checkpoint with the exact profile wording. Include routine, degraded, failed,
   and security events plus timestamp/PID variants. Upstream explicitly describes
   Laya as a base to specialize rather than a universal zero-shot decision engine.
   Longer prompts, a different primitive, or lower uncertainty thresholds do not
   establish correctness. See [existing evaluation](laya-validation.md).
2. **Question integrity:** verify every profile's rendered instructions/options
   with the matching checkpoint tokenizer and budget. Surface collapsed-option
   metadata if available; it does not detect all shortened descriptions. Keep
   this check separate from state truncation.
3. **Throughput:** benchmark true `/v1/systemone/batch` for queued chunks sharing
   model, profile, and budgets. Preserve original per-chunk metadata, stop behavior,
   and a bounded Realtime flush delay. More concurrent single requests are not
   equivalent to one GPU batch. No batching change was made in this review.
4. **Domain specialization:** consider supporting registered custom checkpoint
   names and explicit budgets after a log-specific model is validated. Fit
   probability calibration on held-out domain data; a high category probability
   is not measured accuracy. Custom-name support is now implemented; no model was trained or calibrated.

## Sources

- [Upstream README: budgets and honest limits](https://github.com/NandhaKishorM/laya#honest-limits)
- [HTTP API: request controls, limits, devices, concurrency](https://nandhakishorm.github.io/laya/http-api/)
- [v0.4.1 HTTP implementation](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/serve.py)
- [v0.4.1 Agent: rendering and usage](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/agent.py)
- [v0.4.1 Router: routing, preload, batch](https://github.com/NandhaKishorM/laya/blob/v0.4.1/laya/router.py)
- [Token-budget tuning guide](https://nandhakishorm.github.io/laya/langchain/#7-widening-the-token-budget-for-many-options)
