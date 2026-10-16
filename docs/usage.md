# Usage

[English](usage.md) | [한국어](usage.ko.md) | [Documentation](README.md) | [README](../README.md)

On wide screens, the left **40%** shows **Classification Overview → Task Monitor**;
the right **60%** shows **Classification Results**. On wide screens, the left information panel and right results panel scroll independently. Narrow screens stack the panels and use normal page scrolling.
The sidebar identifies the DeciFlow reader host by hostname, detected IPs, and
OS/version. In WSL or containers, these identify that environment, not its host OS;
IPs are not a full interface inventory. Source SSH hosts are selected per Source in Tasks. The status in parentheses after the engine name, e.g. **Laya (Connected)**, reports the last actual request: Not checked
before a request, then Connected, Disconnected, Timed out, or API error. It is not
a continuous health check; local input rejections do not change the status.

### Tasks and criteria

Register inputs in **Sources**, then save their Criteria, Events/Chunk, and Action
assignments in **Tasks**. Main lists all saved Tasks, with running/starting Tasks first and names sorted within each group. Click one to show its current or latest execution;
a fresh page has no selection. Tasks supports manual Batch, cron Batch with a timezone,
and continuous Realtime; there is no Paste input. Saving does not start analysis.
Use the Enabled switch and Run, Stop, View, Edit, History, and Delete from the Task list.
Disabling stops active execution and blocks manual runs, cron, and automatic
restart; enabling does not start a run immediately.
See [Tasks](tasks.md) for scheduling, restart behavior, and storage.

**Reset Selections** in the Task editor selects available sample Sources (or the
first registration), sample criteria, one event per chunk, and Action None.
Saved configuration is server-side; unsaved drafts are browser-only.
Sources are read by DeciFlow, not the browser or Laya server. File access requires
a local/trusted UI Origin and readable UTF-8 regular files.

Batch reads selected files concurrently and interleaves ready chunks, preserving
each file's collection order, profile, and chunk size. Results appear newest
completion first, so parallel requests can finish out of collection order. Engine concurrency limits apply
to the entire run, not separately to each file. A limit of 1 serializes requests.
Remote connections use the same engine and Action flow as local files.

Choose **Criteria** and **Events/Chunk** for each selected Source.
Defaults: **General system**, **1 event per chunk**. Currently, each nonempty line
is one event; multiline boundaries are not yet detected. Every profile uses `choice` with
**Normal, Warning, Error, Security, Other**; only the descriptions and instructions
differ. Laya and Jev use the same selected profile. Type detection is manual;
`score` also evaluates urgency (0–3: Low, Medium, High, Critical), and `noul`
returns the probability that a work ticket is needed, in the same request.
These shared operational questions are fixed across profiles and engines.
Each result shows **Category (Choice)**, **Urgency (Score)** as a continuous 0–3
value, and **Work Ticket (Noul)** as the Yes probability in three cards by default.
The cards stack on narrow panels. All three badges use the same compact size
(132 × 22 px); there is no separate summary or expand/collapse control.
Processing time and category review status follow the cards. Each has its own probability
distribution: category options, urgency levels 0–3, or ticket Yes/No (`No = 1 − Yes`).
These are separate judgments, not a combined probability. Category uncertainty
reasons stay inside the Category card; **Category needs review** applies only to
Choice. Action execution, Source, category criteria, and chunk size are labeled
separately. No ticket is created automatically. Missing or invalid answers fail the whole decision.

| Criteria profile | Focus |
| --- | --- |
| General system | System/service operation and failures |
| Authentication | Authentication/session outcomes, service failures, and abuse |
| HTTP access | Responses, request failures, and suspicious access |
| Application | Application operations, exceptions, and dependencies |
| Network / tcpdump text | Connection/packet evidence in text; binary PCAP is unsupported |

Use **Criteria** in the sidebar to add, edit, or delete profiles.
Result categories remain Normal, Warning, Error, Security, and Other; `general` cannot
be deleted. **Save Changes** applies to new runs; running jobs keep their original
criteria. See [Criteria management](criteria.md) for storage and deletion restrictions on Task references.
Describe outcomes and evidence; keep specific log strings in evaluation samples.

The resulting log chunk is sent as the request `state` string: one event, or
events joined with newlines. Classification instructions are in `questions`, not
state. [Request/result examples](results.md) show all three questions and answers.

Chunks never mix files. Batch flushes remaining events at EOF; Realtime flushes at
the configured size or after one second without a new event, and separates
file rotations. Blank lines are skipped; event boundaries are not automatically
detected. Overlapping local matches with identical settings are deduplicated by resolved
path; conflicting settings are rejected. Chunking does not bypass model budgets. Remote rotation uses size/prefix checks;
see [SSH limitations](sources.md#ssh-configuration).

General system separates routine operation (Normal), recoverable problems
(Warning), explicit failures (Error), and evidenced abuse or policy violations
(Security). A service name, IP address, or security-related topic is not evidence
of an incident. These criteria guide predictions; validate your deployed model
against representative logs before relying on the categories.

Authentication distinguishes unsuccessful individual attempts (Warning), service
or supporting-mechanism failures (Error), and evidence of abuse (Security).
Other means an unrelated or unidentifiable outcome, not merely unknown root cause.
For recognized **single-line classic syslog**, Authentication removes timestamp,
hostname, and PID from model input while preserving service and message contents
(users, IPs, ports). Original logs remain intact; changed `decisionInput` appears
in JSON. Multiline chunks and unrecognized formats are unchanged. Normalization
reduces input variation; it does not guarantee identical predictions or accuracy.

### Results and controls

Each result displays the original input data in bold; JSON and Action code keep
their own formatting.

Newest **completed** chunks appear first, with 50 results per page by default (Settings → Results: 10, 30, 50, or 100); this is
completion order, not log timestamp order. File locations show **File line(s)**
for Batch and **Observed line(s)** for Realtime—the sequence read since monitoring
started or the file rotated. `1 event (max 5)` means one event was submitted
with a configured maximum of five. JSON uses `chunkEvents` for the configured
limit and `eventCount` for actual events. `line`, `lineEnd`, and `lineCount`
retain line locations/counts. Requests and results use `chunkEvents`.

#### Uncertainty and human review

**Uncertain is a DeciFlow feature**, computed from the provider response in
[`classifier.py`](../classifier.py); it is not Laya's own uncertainty flag.
Any of the following conditions sets `uncertain=true`:

| Condition | JSON `reviewReasons` value | Engine |
| --- | --- | --- |
| Selected category probability (`probabilities[choice]`) below 70% | `low_answer_probability` | Laya and Jev |
| Highest minus second-highest category probability below 10 percentage points | `close_probabilities` | Laya and Jev |
| Rendered options lose distinction (`usage.options.category.distinct < total`) | `collapsed_options` | Laya, when this metadata is present |

Exactly 70% or a gap of exactly 10 percentage points does not trigger its
respective condition. The 70% and 10-point thresholds are fixed project
heuristics, not provider requirements or thresholds validated on DeciFlow's
operating data. They are not configurable through `.env`. Category probabilities
are model outputs, not measured correctness rates. Provider `confidence` is
preserved separately and does not determine Uncertain.

The first two checks correspond to **confidence thresholding** and
**margin-based uncertainty**. In active learning, related data-selection methods
are called least-confidence and margin sampling; least confidence normally uses
the maximum probability, matching our selected-category check only when the
provider chooses the highest-probability category. See
[Settles' Active Learning Literature Survey](https://burrsettles.com/pub/settles.activelearning.pdf).
DeciFlow flags results for review while retaining predictions; it does not
implement a formal reject-option classifier or use these flags to train the model.
The third check detects input integrity problems rather than statistical uncertainty.

For example, **Uncertain · Normal** with Normal 42.1% and Error 21.9% means the
provider selected Normal, but its probability is below 70%; it is a provisional
choice, not a confirmed normal event. The original choice and probabilities are
preserved. The UI shows provisional candidates; JSON records `candidates`,
`probabilityMargin`, and `reviewReasons`.

**Needs Review** includes only successfully classified Uncertain or Other chunks.
Failed/rejected requests count as Failed and are excluded from review metrics/filters. Other alone does not set Uncertain. **Certain**
means no Uncertain flag, not verified accuracy. Use labeled logs to evaluate
misclassifications and review workload before treating the thresholds as an
operating policy.

Filter **All results / Needs Review / No review needed**. Both review groups include
only successful classifications. To inspect failures, choose All results and the
Request failed category. Category filtering
and case-insensitive literal search of original log text combine with the review
filter. **Source**, after Search data, filters by an entered path/pattern and shows
completed counts, including failures. Overlapping patterns retain all matches in
`sourcePatterns`; files are still processed once. Filters affect the list only,
not metrics, chart, or JSON export.

**Host** filters the selected run by its saved host identity and combines with Source,
category, review, and log-text filters. It does not change metrics, charts, or export.
Host collection states (Pending, Reading, Completed, Failed, Stopped) are separate
from decision counts: collection can finish while inference is still running.
SSH connect/read failures appear as **Source failed** records, with host details
and no AI probabilities; use All results / Request failed to find them. Other
remote readers continue. See [multi-host execution](tasks.md#multiple-source-hosts).

Main polls only new results for the current Task page approximately once per second
and reuses existing cards. Polling pauses outside Main and in hidden tabs; Tasks
continue. Older pages stay fixed; Latest Results returns to current results.

| Control | Behavior |
| --- | --- |
| Pause Updates / Resume Updates | Freeze/unfreeze the list, including before the first result; analysis, metrics, and chart continue. Filters/pages use the frozen list; the button counts pending results. |
| Stop (Tasks) | Cancel file readers and pending engine requests; retain completed results, discard unsubmitted chunks. Remote inference already running may finish. |
| View JSON | Expand one result, including failures, profile/chunk metadata, and reviewer edits. Expanded state survives list refreshes. Copy inside the JSON panel copies the current result, including reviewer edits. |
| Reviewer category | Record `reviewerCategory`; does not change AI category, review status, chart, or train the model. |
| Export All JSON | Stream all Task results recorded when export starts, including paused or filtered-out rows; available during execution too. |
| Export Reviewed JSON | Export only this run’s successful results with a nonempty reviewer category different from the original AI category. Includes input, original result, and reviewerCategory; ignores display filters. Unchanged reviews and Not reviewed are excluded. |

**Classification Overview** combines AI category counts across all sources,
including uncertain choices. Counts are **chunks**, not raw lines; percentages use
successfully classified chunks. Failed requests are shown separately. Filters and
reviewer edits do not change the chart. Use the **All / Certain / Uncertain** buttons to chart all
classified chunks or just one certainty group; percentages use the selected group.
The buttons always show their counts. All shows the total count; Certain and Uncertain show their counts and shares of
all successfully classified chunks. Category-bar percentages use the selected group.
Certain means no Uncertain flag, not verified accuracy. The failure count always
shows all failed requests, which belong to neither certainty group.
**Truncated** counts responses reporting `usage.truncated=true` across all groups;
these rejected predictions are included in failures, not category bars. Missing
truncation metadata and local byte-budget rejections are not counted as truncated.
This is log/state truncation, not a count of shortened question instructions.

Displayed, copied, and exported result JSON starts with per-result metadata,
including `requestedAt`, engine, source, and processing duration. Timestamps use
ISO 8601 in UTC (`+00:00`); `requestedAt` is request preparation time, not completion.
Result JSON keeps `requestedModel`, UTC `requestedAt`, request size, input budget,
and the question/criteria snapshot. `providerResponse` preserves the returned
model, `routing` (actual checkpoint), `usage` (tokens/truncation), and full answer
metadata, including provider confidence fields and action/abstention when present.
Top-level `answerProbability` is the probability of the selected category;
`confidence` remains the original provider value. `uncertaintyBasis` identifies
the selected-category scale used by the fixed 70% threshold.
HTTP status and available request-ID/inference-time headers are retained;
credentials and authorization headers are excluded. API failures and rejected
predictions retain available diagnostics too. `model` alone may be a generic
Laya name: inspect `providerResponse.routing` for the actual checkpoint.

[Result JSON example and field reference](results.md)

### Refresh and reconnect

Sidebar routes are Main `/`, Source `/#sources`, Criteria `/#criteria`,
Actions `/#actions`, Tasks `/#tasks`, and Settings `/#settings`.
Source, Criteria, Actions, and Tasks are Main submenus. Settings has SSH Keys
`/#settings/ssh-keys` and SSH Hosts `/#settings/ssh-hosts`; selecting one shows
only that section. Settings itself lists links to SSH Keys and SSH Hosts.
Every page uses a title and a short caption above its content cards. Main keeps
the engine connection status at the right; SSH pages have no duplicate section header.
Selecting a sidebar menu always returns to its list and closes any View, Edit, or
History screen. Unsaved editor drafts are discarded; saved settings and running
Tasks are unchanged.
Task executions continue after disconnecting or closing the browser. Refreshing
reconnects to the same execution; History → View Results replays saved results
without repeating classification or Actions. Main follows new executions of the
selected Task; explicitly viewing a historical run keeps that run selected.

Task definitions, run status, settings snapshots, results, and Action outcomes
persist under `DECIFLOW_DATA_DIR` (Task metadata in `tasks/`, results in `results.sqlite3`). A restart marks interrupted executions
Stopped. Batch is not automatically retried; Realtime starts a new run only when
Resume on restart is enabled. See [Tasks](tasks.md).

Use one DeciFlow server process/instance per data directory. Results and reviewer
corrections persist in SQLite; only the current page is loaded in the browser.
Filters, page position, and unsaved drafts remain browser-only. No automatic history
retention limit is applied. See [Result storage](result-storage.md).

The low-level `/api/classify` text API and `/api/file-source` file API remain
available. With `persist: true`, they return a browser-independent **temporary SQLite-backed**
job (HTTP 202), not a saved Task or durable run. `/api/jobs/<jobId>` inspects a run,
`/events` replays/follows NDJSON, and `/stop` stops a live run (POST). Without
`persist: true`, direct APIs stream for the connection lifetime. Trusted-origin
checks still apply; file access requires a local/trusted UI Origin.

### Timing metrics

| Metric | Meaning |
| --- | --- |
| Success / Failed / Total | Valid classifications / failed chunks / total completed chunks (success + failure); failures include connection errors, timeouts, rejected inputs, and invalid responses |
| Action Success / Failed / Total | Completed Action successes / failures / total; excludes unassigned sources and failed decisions; independent of decision counts |
| Needs Review | Successful Uncertain (low probability, close probabilities, or collapsed options) or Other classifications; excludes failed/rejected requests |
| Throughput | Successfully classified chunks/s over the last 5 seconds, including idle time; uses elapsed time during the first 5 seconds; freezes when stopped/completed |
| Total Elapsed Time | Time since the run started, including idle periods |
| Active Processing Time | Time with at least one request in flight, counting overlap once; percentage of total elapsed time |
| Average Processing Time | Mean completed request duration, including failures; per chunk |

Total Elapsed Time, Active Processing Time, and Average Processing Time use
ms, sec, min, hour, or day as appropriate. JSON duration values remain milliseconds.

Action execution failures do not affect classification counts or engine connection status.

Active and average times include network/server wait. Active time excludes idle
periods and stays within 0–100% of elapsed time; it is not CPU/GPU utilization or
pure inference time. Timing refreshes once per second while waiting; stopping or
disconnecting freezes only the browser display; reconnecting restores server
progress. Stopping retains the last snapshot, which may lag by about one second.


Task throughput uses 100 ms buckets over the last 5 seconds and is approximate at bucket boundaries.

All list Delete actions use a shared styled confirmation dialog. Cancel, Escape, or close makes no change. Source, Criteria, and Actions deletions require Save Changes after confirmation; Task, SSH Keys, and SSH Hosts deletions are submitted immediately after confirmation.

Delete first checks current dependencies on the server. In-use items show a blocking dialog listing up to five referring Tasks, SSH Hosts, Sources, or active runs, plus a remaining count; no Delete button is available. Only unused items receive a deletion confirmation. Failed checks also block deletion. The server rechecks dependencies when applying the deletion or saved changes.

List View opens details directly beneath the selected row. Click the same View to collapse it, or another View to move the detail. List refreshes preserve its position beneath the selected item.

All Views use shared compact label/value styling. Short values sit side by side; long values wrap as needed. Read-only input boxes are omitted. Code and public keys preserve their contents in text blocks with a maximum height. Narrow screens stack fields; editing forms are unchanged.

Task Monitor lists all saved Tasks, prioritizing running/starting Tasks. Cards
show the name and Enabled/state badges, Source and distinct Source Host count,
then Type / Mode / Action (None when unset). Running/starting cards use a pale
green background; Stopped cards use a subdued neutral background. Selected cards
retain a left accent. Keep the pointer still for one second or focus a card for complete Source settings and
Host names/SSH addresses in a scrollable tooltip. Click to show its current/latest
results; Tasks without history show an empty result state. Start/stop Tasks in
Tasks. See [Tasks](tasks.md) for scheduling and default Task restoration.

Once visible, the tooltip stays open while the pointer is over the Task card or
tooltip. Move into the tooltip to select/copy text; leaving both closes it.
