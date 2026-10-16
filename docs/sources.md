# Sources

[English](sources.md) | [한국어](sources.ko.md) | [Documentation](README.md) | [README](../README.md)

Use **Sources** below Main in the sidebar to register reusable log inputs. Choose
**Add source**, enter a name, type, and path, then **Save changes**. Search by name,
path, or host; use View, Edit, or Delete to manage entries. Deletion takes effect
when saved and does not delete log files, SSH hosts, SSH keys, or known_hosts files.
For Remote File, select a saved **SSH host** and enter the remote file path;
connection credentials are managed in **Settings → SSH Hosts**.

| Type | Location and requirements |
| --- | --- |
| Local File | Readable UTF-8 regular files on the DeciFlow node; relative paths start at its working directory |
| Remote File (SSH) | UTF-8 regular files on an SSH/SFTP host; absolute POSIX paths, key authentication, and host-key verification |

Paths accept `*`, `?`, `[abc]`, and recursive `**` patterns. A registration can
match multiple files. Initial examples are System messages, Sample HTTP access,
and Sample SSH authentication; edit them for your environment. Registered names
and IDs must be unique. Renaming preserves the ID.

## Select sources in Main

In Batch or Realtime, add a selection row and type a registered Source name to
filter suggestions. Suggestions include its type, path, and SSH host. Select an
existing entry; free text does not create a source. The selected file path or
pattern is displayed below the Source selector. Action selection uses the same
searchable suggestions; leave it empty for None. Unknown Action names are rejected.

Choose Criteria, Events/chunk, and Action per row. These belong to the run, not the
source registration. Batch reads matching files to EOF; Realtime skips existing
content, follows new lines, and discovers new matching files from their beginning.
Paste remains direct text input and does not need a registered source.
**Reset selections** selects available sample sources (or the first registered
source) with one event per chunk and Action None. Criteria/chunk preferences are
stored by source ID in browser storage; Action selections last for the page session.

Local overlapping matches with identical settings are deduplicated; conflicting
settings are rejected. Remote registrations are read independently, so avoid
selecting overlapping remote registrations in the same run. Chunks never mix
files. Local and remote inputs use the same Laya/Jev classification and Action flow.

## SSH configuration

In Settings, **SSH Hosts** follows **SSH Keys**. Use Add host to save a name,
address, port, SSH user, and key. The searchable list provides View, Edit, and
Delete controls. Multiple Sources can share a Host and use different file paths.
Sources store a `hostId` reference; connection details are resolved for each new
run. Host edits apply to new runs, while running jobs keep their snapshots.
Deletion requires confirmation and is blocked while a saved Source or running job
references the Host. A key referenced by any saved Host cannot be deleted.
Existing inline SSH Source settings are automatically moved into Host entries;
identical connections share one Host and Source IDs are preserved.

These fields belong to a Host in Settings:

| Field | Meaning |
| --- | --- |
| Host | Hostname or IP, without ssh:// or username |
| Port | SSH port, default 22 |
| SSH user | Account with read permission on the remote logs and access to the SFTP subsystem |
| SSH key | Select a key registered in Settings; existing file-path registrations remain supported |

Use a key which can be loaded without a passphrase prompt. Password authentication,
agent authentication, interactive prompts, and disabling host verification are not
supported. Add the matching public key to the remote account's authorized_keys.
Verify the server's host-key fingerprint through a trusted channel and prepare the
known_hosts entry in `~/.ssh/known_hosts` for the DeciFlow process user before running. For nonstandard ports, the entry uses
`[hostname]:port`. Unknown or mismatched host keys fail the connection.

DeciFlow uses SFTP, not remote shell commands, and never stores key contents or
passwords in the registry. SSH/SFTP failures stop the run with an error; there is
no automatic reconnect. Stop closes the SFTP session and pending reads.

Remote Realtime detects truncation and replacement using file size and a leading
byte comparison. A replacement with the same leading bytes and size at least the
previous offset can be missed. Confirm rotation behavior for your log writer.

## SSH keys in Settings

Open **Settings** at the bottom of the sidebar (`/#settings`). Enter a key name
(letters, digits, spaces, underscores, or hyphens) and select one registration method.
The default view is a searchable list of names, private-key paths, and management
buttons. **Add key** opens the registration form; **View** opens details.

- **Upload private key:** select a file from the computer running your browser.
- **Private key file path:** enter a file path accessible to the DeciFlow process
  (inside the container when using Docker). The file is copied into managed storage.
- **Paste private key:** paste the complete private key, including header/footer
  lines. The input is masked and cleared after each submission.

All three methods accept a dedicated private key without a passphrase, up to
64 KiB, and automatically derive its public key. Original files are unchanged.
Select the registered key in a Remote File Source's **SSH key** field.

Pairs persist under `DECIFLOW_DATA_DIR/ssh-keys/<name>/` in the `deciflow-data`
volume: `private_key` (0600) and `public_key.pub` (0644), in a directory with 0700
permissions. Settings shows the private key's path with its contents masked as
`****`, and the public key's path and contents. It never returns private key
contents. Deleting a pair requires a
confirmation and is rejected while a saved Source or running job references it.
Remove or change those references first. Deletion permanently removes both files.

For an existing key on the DeciFlow host, use the file-path method; for a key on
your browser computer, use upload or paste. An existing Source referencing a
mounted key path continues to work. Settings only manages pairs in `ssh-keys`;
it does not automatically scan or delete keys elsewhere on the host.

Keys are stored without encryption at rest. Protect access to Settings, the host,
and volume backups; Python Actions run with DeciFlow permissions and can access
these files. The volume backup includes private keys. Browser uploads should use
HTTPS when accessing DeciFlow over a network.

Host verification still uses the DeciFlow process user's `~/.ssh/known_hosts`.
For the default root-based Docker image, mount a prepared file read-only by adding
this entry under `services.ui.volumes` in `docker-compose.yml`:

```yaml
      - /opt/deciflow-ssh/known_hosts:/root/.ssh/known_hosts:ro
```

Create this host file first, verify server fingerprints through a trusted channel,
then run `docker compose up -d ui`. Adjust the container path if changing the
process user. No SSH executable is required; AsyncSSH is a project dependency.

## Storage and API

SSH Host listing, registration/editing, and deletion use `POST`, `PUT`, and
`DELETE` on `/api/ssh-hosts`. Hosts persist in
`DECIFLOW_DATA_DIR/ssh-hosts/hosts.json`.
SSH key listing, import, and deletion use `POST`, `PUT`, and `DELETE` on
`/api/ssh-keys` with the same trusted file-access origins as Sources.

Definitions are stored in `DECIFLOW_DATA_DIR/sources/sources.json` (default
`/var/lib/deciflow-data/sources/sources.json`). Compose's `deciflow-data` volume
already covers this directory. Saving applies to new runs; active jobs retain
their source settings even if the registration is edited or deleted.

Management uses `POST /api/sources` to read and `PUT /api/sources` to replace the
list. Both require the same local/trusted UI Origin as file access. Saving validates
fields and the SSH Host reference without connecting to the SSH host.
Main sends source IDs with per-run settings to `POST /api/file-source`:

```json
{
  "mode": "batch",
  "sources": [
    {"sourceId": "<registered-source-id>", "profile": "general", "chunkEvents": 1, "action": ""}
  ],
  "persist": true
}
```

The server resolves IDs from the registry; supplied connection/path overrides are
ignored. The file API also supports explicit local paths for programmatic clients.
Results include `sourceId`, `sourceName`, and `sourceType` for registered inputs.
Remote `source` and `sourcePatterns` use `ssh://user@host:port/path` to distinguish
hosts. Credentials and SSH key paths are not added to classification requests or
result records. See [request/result JSON](results.md).
