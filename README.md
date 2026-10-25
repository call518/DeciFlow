<p align="center">
  <a href="https://youtu.be/bXuBJs4Hf70" target="_blank" rel="noopener noreferrer"><img src="images/DeciFlow-Logo.png" alt="DeciFlow" width="480"></a>
</p>

# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**Make fast AI decisions across diverse datasets and automate follow-up workflows your way.**

<p align="left">
  <a href="https://youtu.be/bXuBJs4Hf70" target="_blank" rel="noopener noreferrer">Demo Video - YouTube</a>
</p>

**[Installation and Configuration → INSTALL.md](INSTALL.md)**

Choose [PyPI: pip or uv tool](INSTALL.md#pypi),
[Docker Compose with Git Clone](INSTALL.md#docker-compose), or
[Direct Processes with Git Clone](INSTALL.md#direct-processes).
The installation guide covers prerequisites, engine connections, storage,
authentication, startup, verification, and maintenance for each method.

## Overview

**DeciFlow** turns text logs and structured conversation records into typed AI
decisions, keeps the evidence available for human review, and can run Python Actions
after classification. It reads local, SSH, and HDFS Sources and displays results in
a browser. Existing files can be investigated in Batch mode; Realtime mode follows
new log events.

The **Laya server** runs the decision model on the same host or a separate host.
**Jev** is an alternative paid hosted inference API. DeciFlow reads the data and
sends events to the selected engine. Laya is the default, with no automatic fallback
to paid Jev. DeciFlow nodes connected to a shared Laya server need no local GPU or
PyTorch. **OAuth2-Proxy** optionally provides Google sign-in and HTTPS.

## Concepts

| Component | Role |
| --- | --- |
| Source | A reusable local, SSH, or HDFS input definition. TEXT uses event chunks; JSONL processes one object per line. |
| Criteria | A named profile defining the decisions, options, instructions, and review rules for an event. |
| Decision | A `choice`, `score`, or `noul` judgment. A profile can combine multiple named decisions in one request. |
| Action | Optional Python code that runs after a classification; outcomes are recorded separately. |
| Task | The Source, Criteria, chunk settings, optional Actions, and execution schedule to use together. |
| Run | One execution of a Task, with frozen settings, progress, results, and history. |
| Review | Typed human corrections stored alongside the original AI predictions. |

The workflow is **Source → Criteria → optional Actions → Task → Results → Review**.
Batch Tasks run manually or on a schedule. Realtime Tasks monitor new events until
stopped. Active runs retain their original settings when definitions are edited.
DeciFlow does not create tickets automatically; follow-up behavior belongs to Actions.

## Architecture

[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/call518/DeciFlow)

![DeciFlow architecture](images/DeciFlow-Architecture.png)

DeciFlow reads an event, applies the Task's Criteria through Laya or Jev, validates
the response, and stores results and Action outcomes in SQLite. Source readers and
inference share bounded concurrency. Multiple SSH Hosts produce unified results
while retaining per-host collection status. The UI can reconnect to a run without
repeating classification; Tasks continue when the browser is closed.

Definitions, run history, original inputs, decisions, and reviews persist in the data
store. Checkpointed Batch and Realtime runs can resume after a server restart;
paused runs remain paused. Recovery validates that the original files still match.
See [Task recovery](docs/tasks.md#recovery-after-a-server-restart) and
[Result Storage](docs/configuration.md#storage) for requirements and limits.

## Capabilities

- **Flexible decisions:** combine category choices, probability-weighted scores, and
  yes/no probabilities. System profiles cover Normal, Warning, Error, Security,
  Other, urgency, and work-ticket probability.
- **Evidence and review:** inspect probabilities, Criteria, raw provider responses,
  format-validation failures, and human corrections. Export complete or reviewed
  results as JSON. Certain does not guarantee accuracy.
- **Investigation and monitoring:** Batch and Realtime Tasks, cron schedules,
  pause/resume, multi-host inputs, and durable history.
- **Result exploration:** charts, whole-run filters, cursor pagination, and shareable
  URLs. Decision filters affect result cards; other filters also update Overview.
  Display choices do not trigger new inference.
- **Measured processing:** run-level elapsed time, throughput, and latency
  percentiles. Filtering and pagination do not change run metrics.
- **Controlled automation:** Python Actions, recorded execution errors, reusable
  settings, reference checks, and confirmation for destructive maintenance.
- **AI-assisted Criteria:** draft or revise profiles with OpenAI after reviewing
  sample data. Authoring is separate from classification and incurs API charges;
  see [Criteria](docs/criteria.md#generate-criteria-with-ai).

## Example Applications

Operational logs are the starting point: access logs, application failures, and
system events. Bundled consultation examples also demonstrate decisions about
inquiry type, handling status, follow-up ownership, urgency, and follow-up need.

| Bundled Example | Purpose |
| --- | --- |
| [Sample VOC Asia Culture Center Consulting QnA](docs/voc.md) | Classify complete customer-agent conversations and review outstanding follow-up. |
| [Sample VOC Central Gov Consulting QnA](docs/voc.md#government-qna-sample) | Distinguish policy explanations, application guidance, referrals, and outstanding agency actions. |
| [Sample VOC Local Gov Consulting QnA](docs/voc.md#local-government-qna-sample) | Classify local-government inquiries and commitments supported by conversation evidence. |

Bundled sample names begin with **Sample**. The consultation Criteria are Korean;
they do not verify current law. Samples demonstrate a workflow, not a measured
accuracy guarantee. Traffic analysis, manufacturing decisions, and image inspection
would require additional integrations and domain validation; image inspection also
requires a vision model.

## Limits and Data Handling

- File reads are incremental, but memory use still depends on active files and
  event size. Automatic multiline event-boundary detection is not implemented.
- Laya and Jev have request budgets and provider-specific limits. Truncated or
  invalid responses are rejected; inspect result warnings and response details.
- Wildcards select matching files, not just text logs. Binary/compressed files and
  both active and rotated copies can cause failures or duplicate analysis. Local
  read/UTF-8 failures stop the run; SSH reader failures are recorded per Source/Host.
- Realtime monitoring waits for complete lines. Rotation leftovers are marked
  `incomplete`; rapid rotation and copy-truncate/regrowth can lose events.
- Higher client concurrency does not guarantee greater inference throughput.
  Engine capacity and admission limits apply.
- Laya receives inputs on your selected server; Jev sends them to TypeSafe and
  incurs charges. Optional AI authoring sends reviewed samples to OpenAI. Result
  storage includes original inputs and Action outcomes. Protect data and backups;
  disk retention is not automatic.

See [Sources](docs/sources.md), [Usage](docs/usage.md), and
[Configuration](docs/configuration.md) for detailed behavior and limits.

## Documentation

| Guide | Contents |
| --- | --- |
| **[Installation and Configuration](INSTALL.md)** | Three complete installation methods, deployment settings, and lifecycle commands |
| [Documentation Index](docs/README.md) | All user guides and technical references |
| [Tasks](docs/tasks.md) | Execution modes, scheduling, history, and recovery |
| [Sources](docs/sources.md) | Input formats, paths, SSH trust, and HDFS |
| [Criteria](docs/criteria.md) | Typed decision profiles and AI-assisted authoring |
| [Python Actions](docs/actions.md) | Follow-up code, environments, and outcomes |
| [Usage](docs/usage.md) | Navigation, charts, filters, review, export, and timing |
| [Result JSON](docs/results.md) | Request/result examples and field reference |
| [Configuration](docs/configuration.md) | Environment reference, operational overrides, logging, and maintenance |
| [Development and Releases](docs/development.md) | Tests, model evaluation, package verification, and publishing |

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)
