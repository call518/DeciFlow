# Criteria management

[English](criteria.md) | [한국어](criteria.ko.md) | [Documentation](README.md) | [README](../README.md)

Manage decision profiles under **Criteria** in the sidebar. Both Laya and Jev use them.

| Task | Steps |
| --- | --- |
| List/search | Inspect names and profile IDs; filter with Search by Name |
| View | Inspect the current configuration, instructions, and five definitions read-only; Cancel dismisses it |
| Add | Add profile → enter ID, name, instructions, and five definitions → Save changes |
| Edit | Edit → change criteria → Save changes. Existing IDs stay unchanged |
| Cancel | Cancel edit discards the current editor draft |
| Delete | Delete → Save changes. Deletion is pending until saved |

- Categories stay fixed at **Normal, Warning, Error, Security, and Other**.
  Profiles customize `choice` only; urgency (`score`) and work-ticket need (`noul`)
  use fixed shared questions. Custom categories are unavailable.
- IDs start with a lowercase letter and use lowercase letters, digits, `_`, or `-`,
  up to 64 characters. Names, instructions, and every definition must be nonempty.
- `general` is the default API profile. It appears separately under **Default Criteria**
  above the list, with **View** only. Edit/Delete controls are omitted.
- Saved changes apply to new runs. Running jobs retain their original criteria even
  after edits; result JSON `questions.category` records the criteria actually used.
- Deletion is blocked while saved Tasks reference a profile; update those Tasks first.
  Refresh to load changes saved in another browser. Re-entering Criteria from the
  sidebar opens the list and discards unsaved drafts.
- Describe observed outcomes and evidence. Keep specific log strings in evaluation
  samples and validate model accuracy separately.

View and Edit are never displayed together. Edit/Add closes View; viewing hides
the editor/cancel button and disables saving. Cancel restores any existing draft.

Add/Edit hides the list and shows only the form. Saving or Cancel edit returns to the list.

## Storage and access

At startup, if `DECIFLOW_DATA_DIR/criteria/criteria.json` is missing, DeciFlow writes
the defaults loaded from [`profiles/`](../profiles/). No UI save is needed. If the file
exists, DeciFlow loads its complete list without overwriting edits or deletions.
The default path is `/var/lib/deciflow-data/criteria/criteria.json`. Once saved criteria
exist, editing bundled JSON no longer changes the active criteria.

Docker Compose shares the `deciflow-data` volume with Actions; no additional
mount is needed. Direct host startup needs write permission in the shared directory,
or set `DECIFLOW_DATA_DIR` in `.env` to a writable directory. Changing directories
does not migrate existing data automatically.

The management API reads profiles with `POST /api/criteria` and replaces the list with
`PUT /api/criteria`. It applies the same local/trusted UI origin checks as Actions.
For a remote UI, configure `DECIFLOW_CSRF_TRUSTED_ORIGINS` and protect access with
proxy authentication.
