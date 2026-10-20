# Usage

[English](usage.md) | [한국어](usage.ko.md) | [Documentation](README.md) | [README](../README.md)

On wide screens, the left **40%** shows **Classification Overview → Task Monitor**;
the right **60%** shows **Classification Results**. On wide screens, the left information panel and right results panel scroll independently. Narrow screens stack the panels and use normal page scrolling.
The sidebar identifies the DeciFlow reader host by hostname, detected IPs, and
OS/version. In WSL or containers, these identify that environment, not its host OS;
IPs are not a full interface inventory. Source SSH hosts are selected per Source in Tasks. The engine status starts with Checking… on each page load or refresh. DeciFlow checks Laya `GET /health` or Jev `GET /v1/models` once on the backend, without inference. A successful HTTP check shows Reachable; it does not guarantee model readiness or authentication on Laya versions with public health endpoints. New classification requests then show Operational, Unreachable, Timed Out, Auth Error, or API Error. The tooltip includes the check basis and time. Historical results and local input rejections do not change the status; view changes do not repeat the HTTP check. A late HTTP check cannot overwrite an actual request result. This is not continuous monitoring. A missing DeciFlow check endpoint shows Check Unavailable (restart the UI server); a failed check request shows Check Failed, distinct from an engine API Error.

### Tasks and criteria

Register inputs in **Sources**, then save their Criteria, Events/Chunk, and Action
assignments in **Tasks**. Main lists enabled Tasks, with running/starting Tasks first and names sorted within each group. Click one to show its current or latest execution;
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

Choose **Criteria** and **Events/Chunk** per Source. TEXT groups nonempty lines;
JSONL extracts the configured text field and always handles one object per line.
Criteria defines any number of named Choice, Score, and Noul decisions. Existing
system profiles retain Category, Urgency, and Work Ticket. New profiles configure
their own options and levels. See [Criteria](criteria.md).

All decisions appear in compact cards in their configured order; **Probabilities and Criteria** expands its distribution and definitions.
**Review** records typed corrections. Choice uncertainty is shown per
item; Needs Review can come from any decision, while chart certainty refers to the
selected Choice. These are separate judgments, not one combined probability.
No ticket is created automatically. Missing or invalid answers fail the whole request.

| Criteria profile | Focus |
| --- | --- |
| Sample General System | System/service operation and failures |
| Sample Authentication | Authentication/session outcomes, service failures, and abuse |
| Sample HTTP access | Responses, request failures, and suspicious access |
| Sample Application | Application operations, exceptions, and dependencies |
| Sample Network / tcpdump text | Connection/packet evidence in text; binary PCAP is unsupported |

Use **Criteria** in the sidebar to add, edit, or delete profiles.
System profiles retain Normal, Warning, Error, Security, and Other; custom
profiles choose their own options. **Sample General System** follows the same editing and deletion
rules as every other profile. **Save Changes** applies to new runs; running jobs keep their original
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

Sample General System separates routine operation (Normal), recoverable problems
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

Show Decisions and review/host controls sit above the full-width result filters.
Filter types appear in this order: Search Text, Processing Status, Source, Host, Review Status.
Search Text is selected initially.

Choose **Filter Type** on the left and set its value on the right. Review Status,
Processing Status, Host, and Source use a dropdown; Search Text uses a text field. Switching
types preserves applied conditions and does not refresh results. Conditions combine
with AND and appear as removable buttons below the toolbar. Use **Clear All** to reset
them. Long Source values are shortened on the button; its tooltip keeps the full path.

Processing Status offers **All Statuses**, **Successful**, and **Failed**. Failed includes source, input, engine request, and
response-validation failures; Action execution has a separate status. Filters apply
to the entire stored run; Clear All leaves display settings unchanged.

**Show Decisions** is a separate display setting. Open it and select one or more
checkboxes to choose the decisions shown in each card; **Show All** restores every
decision. Click outside the menu or press Escape to close it. Multiple Criteria have
separate group headings. Display changes do not
filter cards, change counts or pages, fetch results, or run inference. Failed cards
remain visible; cards with no selected decisions show a short message. Review,
Response, Result JSON, and exports retain the complete result. Chart selections
remain independent. A newly opened run starts with all decisions shown.

Each result displays the original input data in bold; JSON and Action code keep
their own formatting.

Newest **completed** chunks appear first, with 30 results per page by default (Settings → Configurations: 10, 30, 50, or 100); this is
completion order, not log timestamp order. File locations show **File line(s)**
for Batch and **Observed line(s)** for Realtime—the sequence read since monitoring
started or the file rotated. `1 event (max 5)` means one event was submitted
with a configured maximum of five. JSON uses `chunkEvents` for the configured
limit and `eventCount` for actual events. `line`, `lineEnd`, and `lineCount`
retain line locations/counts. Requests and results use `chunkEvents`.

#### Uncertainty and human review

**Uncertain is a DeciFlow feature**, computed from the provider response in
[`classifier.py`](../classifier.py); it is not Laya's own uncertainty flag.
For each Choice, any of the following conditions sets its
`decisionAssessments[id].uncertain=true`:

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

**Needs Review** counts successful chunks once when any decision is Uncertain, a
selected option is listed in `reviewOptions`, or instructions were shortened.
Failed/rejected requests count as Failed and are excluded from review metrics/filters. Other alone does not set Uncertain. **Certain**
means no Uncertain flag, not verified accuracy. Use labeled logs to evaluate
misclassifications and review workload before treating the thresholds as an
operating policy.

Filter **All Results / Needs Review / No Review Needed**. Both review groups include
only successful classifications. Dropdown counts cover the entire run, independent
of filters and pages; All Results also includes failures. To inspect failures, choose All Results and **Processing Status → Failed**. Processing status
and case-insensitive literal search of original log text combine with the review
filter. **Source**, after Search data, filters by an entered path/pattern and shows
completed counts, including failures. Overlapping patterns retain all matches in
`sourcePatterns`; files are still processed once. Filters affect the list only,
not metrics, chart, or JSON export.

**Host** filters the selected run by its saved host identity and combines with Source,
processing status, review, and log-text filters. It does not change metrics, charts, or export.
**Source Hosts Detail** opens a scrollable dialog with each host’s collection status
and Success / Failed / Total counts for the entire selected run, including hosts
with no completed records. Opening it does not reconnect to hosts.

Host collection states (Pending, Reading, Completed, Failed, Stopped) are separate
from decision counts: collection can finish while inference is still running.
SSH connect/read failures appear as **Source failed** records, with host details
and no AI probabilities; use Processing Status → Failed to find them. Other
remote readers continue. See [multi-host execution](tasks.md#multiple-source-hosts).

Main polls only new results for the current Task page approximately once per second
and reuses existing cards. Polling pauses outside Main and in hidden tabs; Tasks
continue. Older pages stay fixed; Latest Results returns to current results.

| Control | Behavior |
| --- | --- |
| Pause Display Updates / Resume Display Updates | Freeze/unfreeze the list, including before the first result; analysis, metrics, and chart continue. Filters/pages use the frozen list; the button counts pending results. |
| Stop (Tasks) | Cancel file readers and pending engine requests; retain completed results, discard unsubmitted chunks. Remote inference already running may finish. |
| ▲ / ▼ | Floating buttons at the lower right of Classification Results scroll to the top/bottom of the displayed result area. They do not change pages or start analysis. On narrow screens they scroll the page to the result section boundaries. |
| Details | Expand Action execution, source/host/record location, and Criteria/chunk metadata. Collapsed initially; Action failures remain visible on the card. Expanded state survives list refreshes and pagination. Full metadata remains in View Result JSON. |
| Response | Expand the Laya or Jev response, HTTP status, and validation diagnostics with the same disclosure style as Review. Copy copies the response details; non-JSON and unavailable responses are identified. |
| View Result JSON | Expand one result, including failures, profile/chunk metadata, and reviewer edits. Expanded state survives list refreshes. Copy inside the JSON panel copies the current result, including reviewer edits. |
| Review | Record typed corrections per decision; AI predictions, review flags, charts, and model weights remain unchanged. |
| Export All JSON | Stream all Task results recorded when export starts, including paused or filtered-out rows; available during execution too. |
| Export Reviewed JSON | Export successful results with any human correction different from its AI value, including original answers and reviewerDecisions. Cleared and unchanged corrections are excluded; display filters are ignored. |

Use **Criteria** to select a classification scheme when several are present, then
**Decision** to chart any of its decisions. A single Criteria is shown as bold text. Decision always uses a dropdown with bold selected values, including a single item. Default Chart Decision is selected initially; **Set as Default** saves a new preference without inference. Choice counts selected options; Score
rounds weighted scores to the nearest level (half up); Noul groups Yes probabilities in
[0%, 25%), [25%, 50%), [50%, 75%), and [75%, 100%]. Missing answers and failures are
excluded. All / Certain / Uncertain refers to the selected Choice. Missing evidence is
**Not Assessed**, never Certain. Score and Noul have no certainty groups. Switching decisions uses stored results without inference.

**Classification Overview** separates Criteria and decisions; select a
decision to see its AI counts across sources,
including uncertain choices. Counts are **chunks**, not raw lines; percentages use
successfully classified chunks. Failed requests are shown separately. Filters and
reviewer edits do not change the chart. Use the **All / Certain / Uncertain** buttons to chart all
classified chunks or just one certainty group; percentages use the selected group.
Choice buttons show their counts; Not Assessed appears when needed. All shows the total count; Certain and Uncertain show their counts and shares of
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
persist under `DECIFLOW_DATA_DIR` (configurations and results in `deciflow.sqlite3`).
Checkpoint-enabled Running executions recover under the same run ID after restart;
Paused/Pausing executions recover as Paused. Older executions without checkpoints
become Stopped. The optional Realtime startup setting starts a new run only when
no execution is recoverable. See [Tasks](tasks.md).

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
| Needs Review | Successful chunks with any decision/record review reason; counted once per chunk; failures excluded |
| Throughput | All successful results divided by Active Processing Time in seconds; excludes idle time and Action delivery, counts overlapping request time once, and shows zero before active processing |
| Total Elapsed Time | Time since the run started, including idle periods |
| Active Processing Time | Time with at least one request in flight, counting overlap once; percentage of total elapsed time |
| Processing Time | One compact card, the same size as the other metrics, showing Avg, Min, Max, P(50), P(95), and P(99) with small inline labels. All completed record durations, including failures; Action time excluded. Avg is the arithmetic mean; P(50) averages the central values; P(95)/P(99) use nearest rank. |

Total Elapsed Time, Active Processing Time, and the values in Processing Time use
ms, sec, min, hour, or day as appropriate. JSON duration values remain milliseconds.

Action execution failures do not affect classification counts or engine connection status.

Active and average times include network/server wait. Active time excludes idle
periods and stays within 0–100% of elapsed time; it is not CPU/GPU utilization or
pure inference time. Timing refreshes once per second while waiting; stopping or
disconnecting freezes only the browser display; reconnecting restores server
progress. Stopping retains the last snapshot, which may lag by about one second.

Timing metrics cover the entire selected run regardless of filters, pages, or
paused list updates. Throughput uses three decimal places; positive rates below
0.001 are displayed as `<0.001 chunks/s`. It is observed output rate, not maximum
engine capacity. P(50)/P(95)/P(99) are N/A before any records complete;
small samples can have P(95)/P(99) equal to their maximum duration.

Duration counts are updated incrementally in SQLite. Percentiles scan these
counts in duration order without re-reading or sorting original results. An older
run builds its histogram once on first access; that initial pass is proportional
to its history size. Later reads reuse the histogram. No approximate sampling or
extra dependency is used.

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

Settings includes **Configurations** for maintenance. **Reset DeciFlow** opens a
destructive warning and requires **Yes, Reset DeciFlow**; Cancel changes nothing.
See [reset scope and restart](configuration.md#reset-deciflow) before using it.

Uncertain Choice results show a separate small status badge beside the decision
heading. The prediction value keeps its category color and wraps to show long
values in both summary and detailed decision cards.


## Token Warnings

Affected results show an amber warning above their contents, including in saved runs:

- **Input Token Limit**: the provider reports `usage.truncated=true`. New partial predictions are rejected and original input is preserved. This applies to Laya and Jev when reported.
- **Criteria Shortened**: the provider reports `usage.criteria_tokens_dropped` by question ID. Predictions are retained and marked Needs Review. The local `laya_server.py` adapter measures discarded instruction/option tokens with the served tokenizer, including option-description caps. Increase `LAYA_HEAD_TOKENS` within the model window or shorten Criteria; longer questions leave less input room.
- **Request Size Limit**: Jev's local byte budget rejects the request before sending it. This is not token truncation and is excluded from Truncated counts.

The standard Compose Laya server and external providers may not report shortened
Criteria; absence of a warning does not prove full preservation. Output truncation
is not inferred from token counts or malformed answers: the current provider
contract has no separate output-truncation signal. Invalid answers still fail validation.

## Shareable URLs

Navigation uses clean paths instead of hash-only addresses. Copy the browser address,
open a navigation link in a new tab, reload it, or use Back/Forward to restore it.
Existing `/#tasks` and `/#settings/...` links are converted automatically.

| Target | Path |
| --- | --- |
| Tasks | `/tasks` |
| Task details / history / editor | `/tasks/{id}`, `/tasks/{id}/history`, `/tasks/{id}/edit` |
| Sources, Criteria, Actions | `/sources/{id}`, `/criteria/{id}`, `/actions/{id}` |
| SSH Key / Host | `/settings/ssh-keys/{id}`, `/settings/ssh-hosts/{id}` |
| Add / edit a registered item | Append `/new` to its list path, or `/edit` to its item path |
| Configurations | `/settings/configuration` |
| A specific execution | `/runs/{run-id}` |

Execution URLs retain chart Decision/Criteria selection, chart certainty, Show Decisions,
the active filter control, result filters, cursor pages, and an expanded result section
using query parameters (`review`, `processing`, `host`, `source`, `search`, `cursors`,
`through`, `result`, `detail`, `chart`, `certainty`, `show`, `filter`). Source Hosts Detail uses `dialog=hosts`.
Automatic polling replaces the current URL rather than creating a history entry
for every update. Run, Stop, Pause/Resume, Delete, Save, and Export remain explicit
commands: visiting a link never runs those commands. Unsaved form contents and
credentials are not encoded in URLs. A deleted item or run is reported unavailable.

Restart the DeciFlow UI server/container once to enable direct clean-path requests;
no proxy rewrite is needed when all paths are forwarded to DeciFlow. URL sharing
uses the same access/origin rules as the application and does not preserve unsaved
drafts or create permanent archives of deleted Tasks.

List search text for Sources, Criteria, Actions, Tasks, SSH Keys, and SSH Hosts
is retained across reloads in the same browser tab. Unsaved editor fields are not
restored. Opening another run starts with its own chart defaults unless its URL
includes display selections.
