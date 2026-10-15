# Laya log validation

[English](laya-validation.md) | [한국어](laya-validation.ko.md) | [Documentation](README.md) | [README](../README.md)

Use `scripts/evaluate_laya.py` to evaluate the configured Laya model against
labeled logs. Each request sends the log as `state` with category (`choice`),
urgency (`score`), and work-ticket need (`noul`) questions. The classifier validates
all three answers; expected-label comparisons measure **category only**.
The script does not measure urgency or ticket-probability accuracy and refuses Jev.

## Run an evaluation

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
[`profiles/`](../profiles/), not profiles edited and saved through the UI.
For UI-edited criteria, validate the same labeled logs through the UI.

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
    "profile": "application"
  }
]
```

Each case requires log text and one expected category: `normal`, `warning`,
`error`, `security`, or `other`. `profile` defaults to `general` and must name a
bundled profile. The cases path must be readable in the environment running the evaluator.

## Read the report

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
