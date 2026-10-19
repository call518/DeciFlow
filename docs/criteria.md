# Criteria Management

[English](criteria.md) | [한국어](criteria.ko.md) | [Documentation](README.md) | [README](../README.md)

Manage decision profiles under **Criteria**. Laya and Jev use the same definitions
and response validation. A profile contains a name, shared instructions, ordered
named decisions, and one **Default Chart Decision** of any type for the initial chart.
There is no fixed three-decision limit; provider input and runtime limits still apply.

Default Chart Decision selects exactly one existing decision of any type. It is only a
display preference and does not change AI answers, uncertainty, or filters. Every
decision is available in Overview regardless of `summary`. Use **Set as Default** in
Overview or change it in the Criteria editor. Score charts round weighted scores to
the nearest level (half up); Noul charts show Yes probability ranges.

For each Choice option, **Needs Review** explicitly marks selections requiring human
review, such as unknown/other. The saved `reviewOptions` list contains those option
IDs. An empty list disables selection-based review; it does not disable uncertainty.
Existing profiles without this field retain known legacy unknown/other option IDs.
ChatGPT generation uses the same `defaultDecision` and `reviewOptions` validation.

## Generate Criteria With AI

In **Add Profile**, expand **Generate With AI**. Configure `OPENAI_API_KEY` and
`OPENAI_CRITERIA_MODEL` (default `gpt-5.6-terra`, requires Responses API Structured
Outputs) in DeciFlow's `.env` and restart DeciFlow. The key stays on the backend.


AI generation is optional assistance for authoring the core rules that shape
classification quality. No OpenAI key is needed to create, edit, or save Criteria
manually using this guide. The default model balances intelligence and cost;
review generated rules against representative samples. `.env.example` lists
representative model names and links to the official catalog for availability.

1. Select a registered Source; select one SSH Host for a Remote File Source.
2. Set Events Per Sample for TEXT input, then select **Preview Source Samples**.
   JSONL shows a read-only explanation: one record is one sample, using the configured content field.
3. Review, edit, or remove the samples. Preview reads up to 8 complete inputs,
   totaling at most 24,000 UTF-8 bytes; it does not send them to OpenAI.
4. Leave **Analysis Purpose Mode** on **Automatic (ChatGPT)** (the default) to
   infer a purpose from the samples, or choose **Manual** and enter your purpose.
   Select **Generate Criteria**. The shown samples, mode, manual purpose (if any),
   and application authoring rules are sent to OpenAI.
   Remove sensitive content first. Generation incurs OpenAI API charges.
5. Review **Suggested Analysis Purpose** in automatic mode, or **Analysis Purpose**
   in manual mode, plus the populated Name, shared instructions, Decisions, options or
   levels, Default Chart Decision, and token estimates.
6. Select **Save Changes** to persist the complete profile. Assign it to a Task
   separately and check representative classification results.

**Events Per Sample** controls how many TEXT events form each preview sample;
for example, 5 groups five events into one sample. Match the grouping you plan to
use in the Task. This field does not update Task settings. For JSONL, this input
is hidden: each record is one complete sample, using the Source's content field.
The format rule applies equally to local and remote Sources.

**Analysis Purpose Mode** defaults to **Automatic (ChatGPT)**. No purpose input
is required: AI suggests an objective supported by the samples and generates the
complete Criteria in the same request. Review the suggestion before saving; samples
do not establish your actual business requirements. The purpose is included in the
profile's shared instructions so it remains part of saved Criteria.

Choose **Manual** when you know your objective. **Analysis Purpose** then tells AI
what decisions to design. In plain language, describe the
input, desired questions or categories, judgment time, priority rules, exclusions,
and how to handle missing evidence. Mention the desired language for labels and
rules if needed. JSON and field-by-field Criteria definitions are unnecessary.

Example: “For customer consultations, classify inquiry type, urgency, and whether
staff owe a follow-up at the end of the conversation. Count promised callbacks as
outstanding work; exclude actions owed only by the customer. Use Unknown when
evidence is insufficient. Write labels and rules in Korean.”

Generation replaces the current new-profile draft. Invalid, duplicate, refused,
or incomplete responses do not populate the editor or change saved Criteria.
Generation failure preserves the draft and sample edits so you can retry.
Validation checks structure and required fields, not business-rule accuracy.
Samples come from the beginning of matched inputs and may miss rare cases.
OpenAI drafts Criteria only; actual classification still uses Laya or Jev with no
provider fallback. Existing profiles can be cloned before generating a new draft.

## Understand the Three Parts First

- **Source** defines what to read. Configure the JSONL content field there.
- A **Criteria profile** defines what to judge and the rules for answering.
- A **Task** connects Source and Criteria and determines when to run.

One profile contains multiple **Decisions**. A single request can judge inquiry type
(Choice), handling status (Choice), urgency (Score), and follow-up need (Noul).
Adding a decision does not require another Source or custom UI code.

Start by **Cloning** a sample, changing its name, and editing only the relevant
questions. The [VOC walkthrough and complete form values](voc.md) use the provided
Source and Task.

## Profile Settings: Shared Configuration

| Field | Purpose | What to enter |
| --- | --- | --- |
| Start From Template | Starting definition for a new draft | Use a VOC consultation template for full conversations. Custom Decisions starts a custom configuration. Choosing another template replaces the current draft. |
| Name | Profile name selected by a Task | `VOC Follow-up Test`. Use a name different from existing profiles. |
| Default Chart Decision | Default decision for the Overview chart | Exactly one Choice, Score or Noul. All decisions still run; filters and AI answers are unchanged. |
| Decision Instructions | Rules shared by every decision | Judgment time, evidence to use, prohibited assumptions, and missing-evidence policy. Define individual options within each Decision. |

**Shared instructions example**

```text
Read the entire consultation and judge its state at the end of the conversation.
Use only explicitly stated facts; do not infer masked content.
Distinguish promised actions from completed actions.
Use each decision's other or unknown option when evidence is insufficient.
```

## Decision: One Question and Its Answer Type

The header `Decision 2 · Handling Status · Choice` identifies the second decision.
Its number is display order, not its unique ID. Headers update when names, types,
or order change.

| Field | Purpose | Example and rules |
| --- | --- | --- |
| Decision ID | Key identifying the decision in stored results | `handling_status`. Unique within the profile. Start with a lowercase letter; use lowercase letters, digits and underscores, at most 64 characters. |
| Display Name | Human-readable result heading | `Handling Status`. Korean is also supported. It need not repeat the ID. |
| Type | Expected answer format | Choice for categories, Score for ordered levels, Noul for Yes probability. |
| Instructions | Question and rules for this decision only | `Distinguish outstanding organizational actions at the end of the conversation.` Keep shared principles in the upper section. |

**Distinguish the names:** Profile Name identifies the whole bundle selected by a
Task; Decision ID is a result field key; Display Name is that field's visible
heading. A Choice's Option ID is the code for a possible answer to that question.

| Decision Type | Configuration | Output |
| --- | --- | --- |
| Choice | 2–255 unique option IDs and definitions | One choice and option probabilities |
| Score | 2–10 ordered level definitions, numbered from zero | Probability-weighted score and level probabilities |
| Noul | A yes/no question | Yes probability from 0 to 1 |

### Choice: Classify Into One Option

The left field in each option row is **Option ID**; the right is **Option
Definition**. IDs must be unique within that Decision only. Reusing `unknown`
in a different Decision is valid. `all` and `failed` are reserved.

For example, set Decision ID to `handling_status`, Display Name to `Handling
Status`, Type to Choice, and enter:

**Instructions**

```text
Select the handling status at the end of the conversation.
Choose staff_pending if an organizational action remains outstanding.
Choose complete if processing is finished and no action remains, or unknown if evidence is insufficient.
```

| Option ID | Option Definition |
| --- | --- |
| `complete` | Necessary guidance or processing is finished, with no action outstanding. |
| `staff_pending` | A specific check, callback, dispatch or other action is still owed by an agent or department. |
| `unknown` | The end-of-conversation status cannot be established from the conversation. |

Result and chart option names are derived from Option IDs, such as `booking` →
Booking. The right-hand definition is a decision rule, not a separate option display
name. Choice Option IDs may use Korean. The sample uses names such as 예약 and
고객 조치 대기. Decision IDs remain stable.

Explain **when to select the answer**, rather than providing only a category name.
State precedence when definitions overlap. Use `other` for an uncategorized answer
and `unknown` for missing evidence; these selections are also flagged for review.

### Score: Evaluate Ordered Levels

Write level definitions only. Positions become **0, 1, 2, ...**, so enter levels
from lowest to highest. Provide 2–10 levels.

| Level | Example definition |
| --- | --- |
| 0 | Low: routine guidance, with no imminent deadline or harm. |
| 1 | Medium: follow-up is needed, without an imminent deadline or harm. |
| 2 | High: an explicitly stated imminent deadline or harm requires prompt action. |

The result is a probability-weighted score. `1.4 / 2` is valid; the model need not
return an integer level. Explain level boundaries and evidence in Instructions.

### Noul: Probability That Yes Is True

Do not add options or levels. In Instructions, write a **Yes/No question** and
conditions that count as Yes.

```text
At the end of the consultation, does an organizational follow-up action remain outstanding?
Yes means an agent or department still owes a promised callback, check or dispatch.
No applies when only a customer action remains. Do not treat a promise as completion.
```

85% means Yes probability, not 85% task completion or an instruction to perform an
Action. External effects are determined by the Task's Action assignment and script.


## Live Token Estimates While Authoring

**Estimated Criteria Tokens** appears beneath Add Profile and Edit Profile. It
updates for instructions, options, types, additions and removals before saving,
without calling an external API or tokenizer server.

- **Total** estimates the entire Criteria, including shared instructions repeated for every question.
- **Largest Question** estimates the largest combined instruction and option block.
- **Per-Decision Estimates** expands to show each question's estimate.
- **Laya** shows the server's current question head budget and context per question
  including input. It warns about possible head overflow and the separate
  48-token option-description cap.
- **Jev** compares against the server's request and per-question budgets. Adding
  input consumes additional room in both.

Name and Display Name are not counted as decision instructions.

These are **rough character-based estimates**, not exact model tokenizer counts or
billing. They account for question formatting, options and the app's shared safety
instructions, but actual tokenizer results vary. **Input conversations are excluded.**
Being below the displayed limit therefore does not guarantee that the full request
fits or instructions remain intact. Limits show N/A until server settings load.
Warnings do not prevent saving.

## Author, Save, and Assign

1. Clone or Add Profile. If using a template, select it first.
2. Enter Name and shared Decision Instructions.
3. Give each Decision a unique ID, display name, type, and instructions.
4. Write Choice options or Score levels.
5. Select one decision of any type as Default Chart Decision.
6. Save Changes. Cancel Edit discards the unsaved draft.
7. Edit the Task, choose the new Criteria for its Source row, and save.
8. Compare source conversations with answers in a new run. Saving Criteria does not automatically assign it to a Task.

Add Decision creates a question. Add Option / Level creates an answer option or
level **inside the current Decision**. Remove deletes that option/level; Remove
Decision deletes the entire question. Move Up / Down changes decision display order.

## Resolve Save Errors

| Message or symptom | What to check |
| --- | --- |
| Name is required. | Enter the upper profile Name. |
| Decision IDs must be unique. | Use different IDs for different decisions, such as inquiry_type and handling_status. |
| Option IDs must be unique. | Distinguish the left-hand IDs within one Choice. Changing only the right-hand definition does not resolve duplicate IDs. |
| Choice requires 2–255… | Check option count, empty IDs, and reserved IDs all/failed. |
| Score requires 2–10… | Provide 2–10 level definitions. |
| No Default Chart Decision is available | Add a decision and select it as the default. |
| Empty name/instructions/definition errors | Fill required profile and decision fields and every option/level definition. |

Do not confuse Decision ID with Display Name. Two different display names cannot
be saved if both Decision IDs are `category`.

**View** displays the saved definition read-only beneath its selected row.
Re-entering Criteria discards unsaved drafts. Profile deletion applies on Save
Changes and is blocked while Tasks reference the profile.

## Existing System Profiles

All profiles appear in one searchable **Criteria** list with View, Edit, Clone, and
Delete. **Sample General System** (`general`) is an ordinary optional profile: edit
it directly, or update its Task assignments before deleting it. Deletion survives
restart; a template remains available through **Start From Template**. A new profile
can be written manually or generated with AI even when no profiles are saved.
Existing saved profiles retain their five categories and fixed operational questions until edited.
Editing or cloning uses the typed editor and saves the full decision definitions.
Existing Task references remain valid. System results retain legacy category,
urgency, and ticket fields for existing Actions.

First initialization provides the system examples and **Sample VOC Asia Culture Center Consulting QnA**. On every startup, existing installations also receive the consultation
sample if neither its ID nor its name exists. Saved profiles are never overwritten;
deleting this required sample causes it to return on the next startup. Other
examples remain available through **Start From Template** without a data reset.
Consultation status describes the end of the conversation, not later business
completion. Question-only inputs need inquiry criteria rather than unsupported
judgments about resolution or promised follow-up.

## Results, Review, and Storage

All decisions appear on each result in their configured order; **Probabilities and Criteria** shows its distribution and definitions.
**Review Decisions** accepts Choice options, bounded Score values, and Noul
probabilities. Clear a correction to return to Not Reviewed. AI answers and charts
remain unchanged. Export Reviewed JSON includes results with any changed decision.

Every Choice answer is checked for selected probability below 70%, top-two gap
below 10 percentage points, and Laya option collapse when reported. Other/Unknown
selections require review when listed in `reviewOptions`. Chart certainty refers to
the selected Choice; any decision or record-level issue can require review. These heuristics
are not measured accuracy and do not evaluate Score or Noul confidence.

Running jobs keep frozen profiles. Results retain `decisionDefinitions`,
`primaryQuestion`, `decisions`, and `questions`, so subsequent edits do not relabel
past answers. The current saved default only changes the initial chart selection.
`primaryQuestion` remains a frozen compatibility projection for Actions and old JSON.
New chart identities exclude the default selection; different decision definitions
remain separate. Profiles containing only Score/Noul are supported without a Choice.

Profiles are stored in `DECIFLOW_DATA_DIR/deciflow.sqlite3`; bundled JSON files are
initial defaults and templates. Criteria management requires a trusted UI origin.

The VOC samples are Korean-only. Missing samples are added at startup.
Saved default English profiles are removed and their Task assignments switch to
the corresponding Korean profiles. Historical results and custom clones are preserved.
The `(KOR)` suffix is removed from unchanged default names; custom names are kept.

Laya has a separate head budget for question instructions and options. Instructions
can be cut even when the state fits. See [VOC question budgets](voc.md#check-the-laya-question-budget).

The government sample also provides a Source, Korean Criteria, and a disabled
Batch Task at startup. See [Sample VOC Central Gov Consulting QnA](voc.md#government-qna-sample).
