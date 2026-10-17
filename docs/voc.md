# VOC Consultation Guide

[English](voc.md) | [한국어](voc.ko.md) | [Documentation](README.md)

This workflow reads **one complete customer-agent conversation** and judges inquiry
type, handling status, and outstanding follow-up at the end of that conversation.
Existing system-log Tasks remain supported; assign Sources and Criteria per Task.

## 1. Run the Bundled Sample

1. Apply the new code and restart DeciFlow-UI. No Reset is required.
2. Find **VOC Consultations** under Source.
3. Find **VOC Consultation Review (KOR)** and **VOC Consultation Review (ENG)** under Criteria.
4. View the provided **VOC Consultation Review (KOR)** Task and check its assignments below.
5. Enable the Task, then click **Run**. Enabling or saving does not start it.
6. Select this Task in Main's Task Monitor.

| Setting | Default |
| --- | --- |
| Source Type | Local File |
| Source Path | `/host-logs/sample-logs/voc-consulting_content.jsonl` |
| Input Format | JSONL (Line) |
| Content Field | `consulting_content` |
| Task Mode | Batch / Manual |
| Criteria | VOC Consultation Review (KOR) |
| Events/Chunk | 1 (fixed for JSONL) |
| Action | None |
| Enabled / Resume on Restart | Both off when first provided |

The path assumes the Docker Compose mount. For native execution, change the Source
to the actual file path. Each line contains one JSON object, with the entire
conversation in the `consulting_content` string. Encode conversation line breaks
as JSON string `\n` escapes. All **2,817 records are independent consultations**,
including repeated content. Blank lines are skipped. Malformed JSON, missing or
empty content, and other invalid records are reported as failures.

`voc-instruction.jsonl` is a separate question-only dataset with Content Field
`instruction`. Without responses or processing history, do not infer resolution or
unfulfilled promises. Use a separate inquiry-focused Criteria profile for it.

Batch reads the file from start to end; Run again creates a new run from the start.
Realtime skips existing content and watches new lines, so use Batch for the initial
file test. Selecting Jev uses the paid API.

## 2. Inspect the Results

- Summary cards: Inquiry Type, Handling Status, and Follow-up Required.
- **All Decision Results**: all five decisions, including Follow-up Owner and Urgency.
- **Input Text**: the full conversation used for the decision.
- **Probabilities and Criteria**: probabilities, instructions, and option definitions.
- **Review Decisions**: human corrections; AI originals and charts remain unchanged.
- **Source Hosts Detail**: whole-run success/failure/total counts by host.

After full completion, Success + Failed should equal 2,817. Stopping early counts
only completed records. Inspect failures with Request Failed. For conversations
that exceed input limits, inspect engine outcomes, failure reasons, and Truncated
status. A JSONL consultation is not automatically split into multiple requests.
Probabilities and Certain are not measured accuracy.

## 3. Customize the Criteria

Run the supplied sample first. To customize it, **Clone** it and save a separate
name. Assign the new profile in the Task, save, then start a new run. Active runs
and historical results retain the Criteria definition captured at their start.

See [Criteria authoring](criteria.md) for field purposes, type selection, and
duplicate ID troubleshooting. The complete ENG sample values follow. ENG is the
translation of the KOR reference, with the same decision IDs, types, option
meanings, level counts, and summary settings. KOR Choice keys use Korean; ENG
keys use English. This does not configure automatic input translation. Historical
results retain the option names saved with their run.


## Check the Laya Question Budget

The Criteria editor shows live **Estimated Criteria Tokens**, per-question estimates,
and budget warnings. Input is excluded; this does not replace exact tokenization.

Besides `LAYA_MAX_TOKENS` for state plus one question, Laya applies
`LAYA_HEAD_TOKENS` to each question's instructions and options. Shared Decision
Instructions are repeated per question. A zero state Truncated count does not
prove that the entire instruction text survived.

The full VOC instructions do not fit a 256-token head budget. With the installed
multilingual tokenizer, the KOR sample with Korean options needs at most 471 head
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

| Field | Value |
| --- | --- |
| Name | VOC Consultation Review (ENG) |
| Primary Classification | Inquiry Type |

**Decision Instructions**

```text
Read the entire conversation between the customer and agent and judge the situation at the end of the conversation.

Use only facts explicitly stated in the conversation; do not infer omitted or masked information.
Distinguish completed guidance from completed business processing.
A promised callback, document dispatch or departmental check remains outstanding unless completion is established.
A customer's intention to book or visit later does not by itself create an organizational follow-up obligation.
When evidence is insufficient, use the option corresponding to other or unknown for each decision.
```

### Decision 1: Inquiry Type

| Field | Value |
| --- | --- |
| Decision ID | `inquiry_type` |
| Display Name | Inquiry Type |
| Type | Choice |
| Show in Result Summary | Checked |

**Instructions**

```text
Select the main purpose of the customer's inquiry in this consultation.
If several topics appear, use the request at the center of the consultation.
Classify cancellation, changes or refunds of an existing booking as cancellation, and inquiries about prices or discount conditions as discount.
Select other if no category applies or the main purpose cannot be established.
```

| Option ID | Option Definition |
| --- | --- |
| `booking` | Inquiries about booking availability, new bookings or group bookings. |
| `cancellation` | Inquiries about cancellation, changes or refunds of an existing booking. |
| `discount` | Inquiries about prices, discount conditions, membership benefits or discount application. |
| `facility` | Inquiries about facilities, programs, opening hours, visiting procedures or transport and access. |
| `other` | An inquiry outside the listed categories, or insufficient evidence to establish its main purpose. |

### Decision 2: Handling Status

| Field | Value |
| --- | --- |
| Decision ID | `handling_status` |
| Display Name | Handling Status |
| Type | Choice |
| Show in Result Summary | Checked |

**Instructions**

```text
Select the request handling status at the end of the consultation.
Prioritize staff_pending if a specific organizational action remains outstanding.
Select customer_pending if no organizational action is outstanding and only a specific customer action is awaited.
Select guidance_complete if the necessary guidance or processing is complete and no further action remains.
Select unknown if the final status cannot be determined.
```

| Option ID | Option Definition |
| --- | --- |
| `guidance_complete` | Necessary guidance or processing is complete, with no specific follow-up action outstanding. |
| `customer_pending` | No organizational action is outstanding; a specific customer action such as submitting documents, checking or applying is awaited. |
| `staff_pending` | An agent or department still owes a callback, check, document dispatch or processing action. |
| `unknown` | The handling status at the end of the consultation cannot be established from the conversation. |

### Decision 3: Follow-up Owner

| Field | Value |
| --- | --- |
| Decision ID | `follow_up_owner` |
| Display Name | Follow-up Owner |
| Type | Choice |
| Show in Result Summary | Unchecked |

**Instructions**

```text
Select who must perform the next outstanding action at the end of the consultation.
If an organizational action remains, select the agent or department responsible for performing it.
Select customer if only a customer action remains and no organizational action is outstanding.
Select none if no action remains, or unknown if responsibility is unclear.
```

| Option ID | Option Definition |
| --- | --- |
| `customer` | The customer must next submit documents, check information or apply. |
| `agent` | The consultation agent must next check, call back or dispatch documents. |
| `department` | A department other than the consultation agent must next check, contact or process the request. |
| `none` | No further action is required. |
| `unknown` | Follow-up is required, but the responsible party cannot be established. |

### Decision 4: Urgency

| Field | Value |
| --- | --- |
| Decision ID | `urgency` |
| Display Name | Urgency |
| Type | Score |
| Show in Result Summary | Unchecked |

**Instructions**

```text
Judge intervention urgency using harm and time constraints explicitly stated in the conversation.
Do not increase urgency solely because of a complaint or missing information.
The need for follow-up alone does not justify high urgency.
```

| Level | Definition |
| --- | --- |
| 0 | Low: routine guidance, with no urgent harm or imminent deadline established. |
| 1 | Medium: follow-up is required, but no immediate harm or imminent deadline exists. |
| 2 | High: an imminent deadline or significant harm is explicitly stated, requiring prompt intervention. |
| 3 | Critical: an immediate safety threat or severe ongoing harm requires immediate intervention. |

### Decision 5: Follow-up Required

| Field | Value |
| --- | --- |
| Decision ID | `follow_up_required` |
| Display Name | Follow-up Required |
| Type | Noul |
| Show in Result Summary | Checked |

**Instructions**

```text
At the end of the consultation, does an organizational follow-up action remain outstanding?

Yes means an agent or department still owes a promised callback, document dispatch, fact check or business processing action.
Do not treat an action as outstanding if the conversation establishes that it has been completed.
No applies when only a customer action such as booking, visiting or submitting documents remains.
Do not infer an outstanding organizational action without evidence.
```

Do not add options or levels. The result is the Yes probability.

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
