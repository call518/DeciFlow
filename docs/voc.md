# VOC Consultation Guide

[English](voc.md) | [한국어](voc.ko.md) | [Documentation](README.md)

This workflow reads **one complete customer-agent conversation** and judges inquiry
type, handling status, and outstanding follow-up at the end of that conversation.
Existing system-log Tasks remain supported; assign Sources and Criteria per Task.

## Government QnA Sample

**Sample VOC Central Gov Consulting QnA** is also added at startup, including to existing
installations. Its Source uses `/host-logs/sample-logs/voc-central-gov-consulting-qna.jsonl`,
JSONL (Line), and Content Field `consulting_content` (3,965 records).
The **Sample VOC Central Gov Consulting QnA** Criteria classify Policy Area,
Response Type, Follow-up Owner, Urgency, and Follow-up Required. They distinguish
rule explanations, application guidance, referrals, completed processing, and
explicitly outstanding agency actions. Referrals and contact footers alone do not
create agency follow-up obligations; the profiles do not verify current law.
The provided **Sample VOC Central Gov Consulting QnA** Task uses Korean Criteria,
Batch / Manual, Events/Chunk 1, and Action None. It starts disabled with Resume on
Restart off. Enable it and click Run to analyze the sample. Saved edits are preserved.

## Local Government QnA Sample

**Sample VOC Local Gov Consulting QnA** Source, Criteria, and Task are added at startup,
including to existing installations; saved edits are preserved. The Source reads
`/host-logs/sample-logs/voc-local-gov-consulting-qna.jsonl` (3,280 records) as
JSONL (Line), with Content Field `상담내용`. Only this field is sent for classification;
`지방자치단체명` and `상담담당부서` remain original record metadata, including empty departments.
The Korean Criteria cover local policy area, response type, follow-up owner, urgency,
and follow-up required. General project schedules and improvement plans alone do not
count as outstanding commitments for an individual inquiry. The Task uses Batch / Manual,
Events/Chunk 1, and Action None, with Enabled and Resume on Restart off. Start
DeciFlow-UI, enable the Task, and click Run. For native execution,
change the Source path to the sample file's actual local path.

## 1. Run the Bundled Sample

1. Start DeciFlow-UI.
2. Find **Sample VOC Asia Culture Center Consulting QnA** under Source.
3. Find **Sample VOC Asia Culture Center Consulting QnA** under Criteria.
4. View the provided **Sample VOC Asia Culture Center Consulting QnA** Task and check its assignments below.
5. Enable the Task, then click **Run**. Enabling or saving does not start it.
6. Select this Task in Main's Task Monitor.

| Setting | Default |
| --- | --- |
| Source Type | Local File |
| Source Path | `/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl` |
| Input Format | JSONL (Line) |
| Content Field | `consulting_content` |
| Task Mode | Batch / Manual |
| Criteria | Sample VOC Asia Culture Center Consulting QnA |
| Events/Chunk | 1 (fixed for JSONL) |
| Action | None |
| Enabled / Resume on Restart | Both off when first provided |

The path assumes the Docker Compose mount. For native execution, change the Source
to the actual file path. Each line contains one JSON object, with the entire
conversation in the `consulting_content` string. Encode conversation line breaks
as JSON string `\n` escapes. All **841 records are independent consultations**,
including repeated content. Blank lines are skipped. Malformed JSON, missing or
empty content, and other invalid records are reported as failures.

`voc-central-gov-consulting-qna.jsonl` is another consultation dataset with Content
Field `consulting_content`. For inputs without responses or processing history,
use inquiry-focused Criteria and do not infer resolution or unfulfilled promises.

Batch reads the file from start to end; Run again creates a new run from the start.
Realtime skips existing content and watches new lines, so use Batch for the initial
file test. Selecting Jev uses the paid API.

## 2. Inspect the Results

- Decision cards: all five decisions, including Follow-up Owner and Urgency, in their configured order.
- **Input**: the full conversation used for the decision.
- **Probabilities and Criteria**: probabilities, instructions, and option definitions.
- **Review**: human corrections; AI originals and charts remain unchanged.
- **Source Hosts Detail**: whole-run success/failure/total counts by host.

After full completion, Success + Failed should equal 841. Stopping early counts
only completed records. Inspect failures with Request Failed. For conversations
that exceed input limits, inspect engine outcomes, failure reasons, and Truncated
status. A JSONL consultation is not automatically split into multiple requests.
Probabilities and Certain are not measured accuracy.

## 3. Customize the Criteria

Run the supplied sample first. To customize it, **Clone** it and save a separate
name. Assign the new profile in the Task, save, then start a new run. Active runs
and historical results retain the Criteria definition captured at their start.

See [Criteria authoring](criteria.md) for field purposes, type selection, and
duplicate ID troubleshooting. The supplied Criteria use Korean instructions and
option names. Historical results retain the option names saved with their run.


## Check the Laya Question Budget

The Criteria editor shows live **Estimated Criteria Tokens**, per-question estimates,
and budget warnings. Input is excluded; this does not replace exact tokenization.

Besides `LAYA_MAX_TOKENS` for state plus one question, Laya applies
`LAYA_HEAD_TOKENS` to each question's instructions and options. Shared Decision
Instructions are repeated per question. A zero state Truncated count does not
prove that the entire instruction text survived.

The full VOC instructions do not fit a 256-token head budget. With the installed
multilingual tokenizer, the sample with Korean options needs at most 471 head
tokens; **`LAYA_HEAD_TOKENS=512` preserves every instruction**. Supplied conversation
states use at most 1,600 tokens, so adding the heads still fits the current 8,192
context limit. These measurements apply to this dataset, sample and tokenizer,
not arbitrary future data.

To use the complete sample instructions with Laya, set `LAYA_HEAD_TOKENS=512` in
`.env`, Restart DeciFlow-UI, and start a new run. Active runs retain previous
settings. Remeasure after changing instructions, options or models. Laya also caps
each option description at 48 tokens internally; increasing the head does not
remove every length limit.

Jev has different limits and a different tokenizer. Do not reuse Laya token counts
for Jev. DeciFlow's Jev byte check is not exact token measurement.

## 4. Complete Form Values

The bundled Criteria are Korean-only. Use the [complete field values in the Korean
guide](voc.ko.md#4-전체-입력값) or the canonical templates:
[Asia Culture Center](../profiles/consultation.json) and
[Central Gov](../profiles/central_gov.json). Copy their labels, instructions, option
keys, and definitions unchanged when reproducing the supplied profiles.

## 5. Validate the Decision Boundaries

These are synthetic checks, not customer records or guaranteed model outputs.

| End-of-conversation situation | Expected interpretation |
| --- | --- |
| Opening hours explained, no further promise | handling_status: guidance_complete / owner: none / organizational follow-up: No |
| Agent promises a callback after checking, with no completion stated | handling_status: staff_pending / owner: agent / organizational follow-up: Yes |
| Only the customer's submission of required documents remains | handling_status: customer_pending / owner: customer / organizational follow-up: No |
| Conversation ends before final status is established | handling_status: unknown / do not invent outstanding actions or ownership |

Start by comparing 10–20 varied records against their full conversations. Identify
missing or overlapping definitions in incorrect cases, revise, and compare a new
run. Check Inquiry Type separately from handling status and follow-up accuracy:
a correct inquiry category can coexist with a mistaken assumption that a promised
callback has already happened.
