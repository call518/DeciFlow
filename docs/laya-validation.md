# Laya log validation — 2026-10-10

[English](laya-validation.md) | [한국어](laya-validation.ko.md)

**The display/budget fixes are verified; log classification is still unreliable.**
We tested 13 General system cases on the remote CUDA server. Expected labels are
engineering judgments in [the fixture](../tests/fixtures/general_evaluation.json),
not a held-out accuracy benchmark. No paid Jev calls were made.

| Checkpoint | Final expected labels matched | Final Certain results |
| --- | --- | --- |
| English | 9/13 | 0/13 |
| Multilingual | 5/13 | 4/13 |
| Typed-decisions | 6/13 | 0/13 |

Certain means passing the selected-category probability and margin thresholds;
it is not correctness. Fixing the confidence scale does not force Certain results.

## Changes applied

- Chart **Truncated** counts confirmed `usage.truncated=true` responses across
  all groups. These rejected predictions are included in request failures.
- UI shows selected-category probability; Uncertain uses probability below 70%
  or a top-two gap below 10 percentage points. Provider confidence stays in JSON.
- English question budget increased from 192 to 256; its request window remains
  512. The official tokenizer showed 26 of 89 instruction tokens dropped at 192,
  and none at 256. Multilingual/Typed-decisions kept their full instructions at 256.
  The server does not report its cached tokenizer revision, so this token check
  uses the official repository's current tokenizer.

`usage.truncated` reports state/log truncation, not question truncation. Increasing
question budget can leave less room for logs; rejected originals remain available.

## Experiments not adopted

We made 156 comparison requests across three checkpoints, using the existing
question, a larger question budget, shorter positive criteria, and shorter
criteria with syslog-header normalization. Short criteria raised Typed-decisions
from 7/13 to 10/13 in that comparison, but still misclassified `falseticker` as
Security and synchronization failure as Warning. Header removal did not improve
all checkpoints. Repeating the existing Typed-decisions request scored 6/13 in
final validation, so the small-sample results are not stable enough to justify
changing production criteria or automatically switching models.

The remaining issue is semantic classification: thresholds and larger windows do
not teach the model what an unfamiliar service message means. Validate more
representative labeled logs before using these categories to trigger actions.

## Reproduce the final validation

With `DECISION_ENGINE=laya` and the selected checkpoint available on the server:

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

To compare all three prepared checkpoints, repeat `--model`:

```bash
uv run python -m scripts.evaluate_laya \
  --model english \
  --model multilingual \
  --model typed-decisions \
  --output /tmp/laya-validation.json
```

The script uses current production criteria, caps concurrency at two, writes
individual responses and mismatches, and refuses Jev. The historical experiments
and final responses are in [laya-validation.json](laya-validation.json).
