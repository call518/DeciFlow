# Usage

[English](usage.md) | [한국어](usage.ko.md) | [README](../README.md)

On wide screens, the left **40%** shows **Classification overview → Log input**;
the right **60%** shows **Classification results**. Narrow screens stack the panels.
The sidebar identifies the DeciFlow log source host by hostname, detected IPs, and
OS/version. In WSL or containers, these identify that environment, not its host OS;
IPs are not a full interface inventory. The status in parentheses after the engine name, e.g. **Laya (Connected)**, reports the last actual request: Not checked
before a request, then Connected, Disconnected, Timed out, or API error. It is not
a continuous health check; local input rejections do not change the status.

### Input and criteria

**Reset sources**, beside Add source, restores the current Batch/Realtime sample
paths, General system criteria, one event per chunk, and Action None. It is disabled
during processing.

**Batch** is selected by default. Each mode starts with editable examples.

| Mode | What DeciFlow reads |
| --- | --- |
| Realtime | New lines after existing files' end; new/replacement files from the beginning |
| Batch | Matching files from the beginning to EOF |
| Paste | Pasted text grouped into chunks |

Mode identifiers in the UI and exported JSON are `realtime`, `batch`, and `paste`.
The file API also accepts legacy `follow` and returns `realtime`.

File sources are on the **DeciFlow node**, not the Laya host. They require local
browser access (`localhost`/`127.0.0.1`) and readable UTF-8 regular files. Enter one
path or pattern in each source row. Three sample sources are prefilled; use
**Remove** to discard one or **Add source** to add another. The **Path** label and
input share one line. Each row includes its Criteria, Events/chunk, and Action.
Edited source paths are retained separately for Batch and Realtime during the
page session. Enter a path for every source before starting analysis. Absolute paths, multiple directories, `*`, `?`, `[abc]`,
and recursive `**` are supported. Relative paths start at DeciFlow's working
directory. Batch needs matching files; Realtime can wait for new matches.
Batch reads selected files concurrently and interleaves ready chunks, preserving
each file’s line order, profile, and chunk size. Engine concurrency limits apply
to the entire run, not separately to each file; a limit of 1 serializes requests.

Choose **Criteria** and **Events/chunk** for each path/pattern or for Paste.
Defaults: **General system**, **1 event per chunk**. Currently, each nonempty line
is one event; multiline boundaries are not yet detected. Every profile uses `choice` with
**Normal, Warning, Error, Security, Other**; only the descriptions and instructions
differ. Laya and Jev use the same selected profile. Type detection is manual;
`score` and `noul` are not used.

| Criteria profile | Focus |
| --- | --- |
| General system | System/service operation and failures |
| Authentication | Authentication/session outcomes, service failures, and abuse |
| HTTP access | Responses, request failures, and suspicious access |
| Application | Application operations, exceptions, and dependencies |
| Network / tcpdump text | Connection/packet evidence in text; binary PCAP is unsupported |

Use **Criteria** in the sidebar to add, edit, or delete profiles.
Result categories remain Normal, Warning, Error, Security, and Other; `general` cannot
be deleted. **Save changes** applies to new runs; running jobs keep their original
criteria. See [Criteria management](criteria.md) for storage and source reassignment.
Describe outcomes and evidence; keep specific log strings in evaluation samples.

Chunks never mix files. Batch flushes remaining events at EOF; Realtime flushes at
the configured size or after one second without a new event, and separates
file rotations. Blank lines are skipped; event boundaries are not automatically
detected. Overlapping matches with identical settings are deduplicated by resolved
path; conflicting settings are rejected. Chunking does not bypass model budgets.

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

Newest **completed** chunks appear first, with 100 results per page; this is
completion order, not log timestamp order. File locations show **File line(s)**
for Batch and **Observed line(s)** for Realtime—the sequence read since monitoring
started or the file rotated. `1 event (max 5)` means one event was submitted
with a configured maximum of five. JSON uses `chunkEvents` for the configured
limit and `eventCount` for actual events. `line`, `lineEnd`, and `lineCount`
retain line locations/counts. Legacy API input `chunkLines` remains accepted;
new requests and results use `chunkEvents`.

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

**Needs review** includes only successfully classified Uncertain or Other chunks.
Failed/rejected requests count as Failed and are excluded from review metrics/filters. Other alone does not set Uncertain. **Certain**
means no Uncertain flag, not verified accuracy. Use labeled logs to evaluate
misclassifications and review workload before treating the thresholds as an
operating policy.

Filter **All results / Needs review / No review needed**. Both review groups include
only successful classifications. To inspect failures, choose All results and the
Request failed category. Category filtering
and case-insensitive literal search of original log text combine with the review
filter. **Source**, after Search logs, filters by an entered path/pattern and shows
completed counts, including failures. Overlapping patterns retain all matches in
`sourcePatterns`; files are still processed once. Filters affect the list only,
not metrics, chart, or JSON export.

| Control | Behavior |
| --- | --- |
| Pause updates / Resume updates | Freeze/unfreeze the list, including before the first result; analysis, metrics, and chart continue. Filters/pages use the frozen list; the button counts pending results. |
| Stop | Cancel file readers and pending engine requests; retain completed results, discard unsubmitted chunks. Remote inference already running may finish. |
| View JSON | Expand one result, including failures, profile/chunk metadata, and reviewer edits. Expanded state survives list refreshes. Copy inside the JSON panel copies the current result, including reviewer edits. |
| Reviewer category | Record `reviewerCategory`; does not change AI category, review status, chart, or train the model. |
| Export JSON | After processing finishes or stops, export all received results—including those not displayed while paused. |

**Classification overview** combines AI category counts across all sources,
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

Sidebar routes are Main `/`, Criteria `/#criteria`, and Actions `/#actions`.
Reloading opens the view specified by the URL; browser back/forward also switches
views. Unsaved editor drafts do not survive a reload.

UI runs (Batch, Realtime, and Paste) continue in **server memory** when the browser
refreshes or disconnects. Each browser tab remembers its latest job ID in session
storage. Refreshing the same tab restores its source settings and completed results,
then follows new results without repeating classification or Actions. Completed and
stopped jobs can also be restored while the same server process is running.
**Stop** explicitly cancels the server job and retains completed results. After a
connection failure, **Reconnect** attaches to the same job rather than starting one.
Closing a tab does not stop its job; stop it before leaving if it should not continue.
Reopening a closed tab is not a supported recovery mechanism.

No DB or disk history is used. Server/container restart loses all jobs; the UI
reports that the previous job is unavailable. Use one server worker. Results from
all jobs remain in RAM until server shutdown; large batches and long Realtime runs
increase memory use. Timing ticks keep only their latest snapshot. Reviewer edits,
filters, pagination, and unsaved editor drafts remain browser-only and are not
restored. Export to preserve results beyond a server restart. No job-history browser
or JSON import is provided.

API clients can send `persist: true` to `/api/classify` or `/api/file-source` to
receive HTTP 202 with `jobId`, `state`, and validated `settings`. POST
`/api/jobs/<jobId>` inspects the job, `/api/jobs/<jobId>/events` replays and follows
NDJSON, and `/api/jobs/<jobId>/stop` stops it. These requests use the same origin
checks as analysis; file jobs also require a local/trusted UI origin. Without
`persist: true`, existing APIs retain their connection-scoped streaming behavior.

### Timing metrics

| Metric | Meaning |
| --- | --- |
| Success / Failed / Total | Valid classifications / failed chunks / total completed chunks (success + failure); failures include connection errors, timeouts, rejected inputs, and invalid responses |
| Action Success / Failed / Total | Completed Action successes / failures / total; excludes unassigned sources and failed decisions; independent of decision counts |
| Needs review | Successful Uncertain (low probability, close probabilities, or collapsed options) or Other classifications; excludes failed/rejected requests |
| Throughput | Successfully classified chunks/s over the last 5 seconds, including idle time; uses elapsed time during the first 5 seconds; freezes when stopped/completed |
| Total elapsed time | Time since the run started, including idle periods |
| Active processing time | Time with at least one request in flight, counting overlap once; percentage of total elapsed time |
| Average processing time | Mean completed request duration, including failures; per chunk |

Total elapsed time, Active processing time, and Average processing time use
ms, sec, min, hour, or day as appropriate. JSON duration values remain milliseconds.

Action execution failures do not affect classification counts or engine connection status.

Active and average times include network/server wait. Active time excludes idle
periods and stays within 0–100% of elapsed time; it is not CPU/GPU utilization or
pure inference time. Timing refreshes once per second while waiting; stopping or
disconnecting freezes only the browser display; reconnecting restores server
progress. Stopping retains the last snapshot, which may lag by about one second.

