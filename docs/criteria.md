# Criteria management

[English](criteria.md) | [한국어](criteria.ko.md) | [Documentation](README.md) | [README](../README.md)

Manage decision profiles under **Criteria** in the sidebar. Both Laya and Jev use them.

**Registered Criteria** lists editable profiles. First startup/reset provides
**Sample Application**, **Sample Authentication**, **Sample HTTP access**, and
**Sample Network / tcpdump text**. The Sample prefix identifies bundled examples;
profile IDs and decision definitions are unchanged. Default Criteria remains separate.

| Task | Steps |
| --- | --- |
| List/search | Inspect names; filter with Search by Name |
| View | Inspect the current configuration, instructions, and five definitions read-only beneath the selected row; View toggles it closed |
| Add | Add Profile → enter name, instructions, and five definitions → Save Changes |
| Clone | Clone opens Add Profile with the original instructions and definitions, preserving normalization. Name defaults to `Original Name (Clone)`; an internal UUID is generated automatically; select Save Changes. Cancel leaves the original unchanged |
| Edit | Edit → change criteria → Save Changes. Internal IDs stay unchanged |
| Cancel | Cancel Edit discards the current editor draft |
| Delete | Delete → Save Changes. Deletion is pending until saved |

- Categories stay fixed at **Normal, Warning, Error, Security, and Other**.
  Profiles customize `choice` only; urgency (`score`) and work-ticket need (`noul`)
  use fixed shared questions. Custom categories are unavailable.
- Names, instructions, and every definition must be nonempty.
- `general` is the default API profile. It appears separately under **Default Criteria**
  above the list, with **View** and **Clone**. Edit/Delete controls are omitted.
- Saved changes apply to new runs. Running jobs retain their original criteria even
  after edits; result JSON `questions.category` records the criteria actually used.
- Deletion is blocked while saved Tasks reference a profile; update those Tasks first.
  Refresh to load changes saved in another browser. Re-entering Criteria from the
  sidebar opens the list and discards unsaved drafts.
- Describe observed outcomes and evidence. Keep specific log strings in evaluation
  samples and validate model accuracy separately.

View and Edit are never displayed together. Edit/Add closes View; viewing hides
the editor/cancel button and disables saving. Cancel restores any existing draft.

Add/Edit hides the list and shows only the form. Saving or Cancel Edit returns to the list.

## Storage and access

At startup, the database initializes missing Criteria from bundled definitions in
[`profiles/`](../profiles/). Saved edits and deletions are preserved. Configuration
is stored in `DECIFLOW_DATA_DIR/deciflow.sqlite3`, not a separate JSON registry.
Bundled JSON supplies initial defaults only; editing it does not replace saved profiles.

Docker Compose shares the `deciflow-data` volume with Actions; no additional
mount is needed. Direct host startup needs write permission in the shared directory,
or set `DECIFLOW_DATA_DIR` in `.env` to a writable directory. Changing directories
does not migrate existing data automatically.

The management API reads profiles with `POST /api/criteria` and replaces the list with
`PUT /api/criteria`. It applies the same local/trusted UI origin checks as Actions.
For a remote UI, configure `DECIFLOW_CSRF_TRUSTED_ORIGINS` and protect access with
proxy authentication.

New profiles and clones receive an internal UUID, independent of Name. IDs are hidden in lists, Views, and forms. Existing IDs remain unchanged to preserve Task and history references. Duplicate names (ignoring case and surrounding whitespace) are reported immediately in red and block saving without discarding the draft. Names may contain non-Latin characters. The server enforces the same duplicate-name rule.
