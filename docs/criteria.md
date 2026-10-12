# Criteria management

[English](criteria.md) | [한국어](criteria.ko.md) | [README](../README.md)

Manage decision profiles under **Criteria** in the sidebar. Both Laya and Jev use them.

| Task | Steps |
| --- | --- |
| List/search | Inspect names and profile IDs; filter with Search by Name |
| View | Inspect the current configuration, instructions, and five definitions read-only; Close dismisses it |
| Add | Add profile → enter ID, name, instructions, and five definitions → Save changes |
| Edit | Edit → change criteria → Save changes. Existing IDs stay unchanged |
| Cancel | Cancel edit discards the current editor draft |
| Delete | Delete → Save changes. Deletion is pending until saved |

- Categories stay fixed at **Normal, Warning, Error, Security, and Other**.
  Only `choice` decisions are supported; other decision types/custom categories are unavailable.
- IDs start with a lowercase letter and use lowercase letters, digits, `_`, or `-`,
  up to 64 characters. Names, instructions, and every definition must be nonempty.
- `general` is the default API profile. It can be edited but cannot be deleted.
- Saved changes apply to new runs. Running jobs retain their original criteria even
  after edits/deletion; result JSON `question` records the criteria actually used.
- Select replacement profiles for sources assigned to deleted profiles. Refresh the
  page to load changes saved in another browser. Switching views preserves editor drafts.
- Describe observed outcomes and evidence. Keep specific log strings in evaluation
  samples and validate model accuracy separately.

View and Edit are never displayed together. Edit/Add closes View; viewing hides
the editor/cancel button and disables saving. Close restores any existing draft.

## Storage and access

Initial profiles come from JSON in [`profiles/`](../profiles/). After the first save,
`DECIFLOW_DATA_DIR/criteria/criteria.json` replaces the complete list, preserving deletions.
The default path is `/var/lib/deciflow-data/criteria/criteria.json`. Once saved criteria
exist, editing bundled JSON no longer changes the active criteria.

The Docker launch script shares the `deciflow-data` volume with Actions; no additional
mount is needed. Direct host startup needs write permission in the shared directory,
or set `DECIFLOW_DATA_DIR` in `.env` to a writable directory. `DECIFLOW_ACTIONS_DIR`
overrides only Actions storage and does not affect Criteria. Changing directories
does not migrate existing data automatically.

The management API reads profiles with `POST /api/criteria` and replaces the list with
`PUT /api/criteria`. It applies the same local/trusted UI origin checks as Actions.
For a remote UI, configure `DECIFLOW_CSRF_TRUSTED_ORIGINS` and protect access with
proxy authentication.
