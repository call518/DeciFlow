# Sources

The list’s **Manage → Ref.** button and Edit’s **References** link open a
reference dialog. View displays the same details directly above its configuration
under **References**. Task assignments, active executions, and recoverable runs
show only type, name, and ID. Available ID links open details in a new tab;
references are fetched when opened.


[English](sources.md) | [한국어](sources.ko.md) | [Documentation](README.md) | [README](../README.md)

Use **Source** in the sidebar to register reusable data inputs. Choose
**Add Source**, enter Name, Type, File Path / Pattern, and Input Format, then **Save Changes**. Search by name,
or path; use View, Edit, or Delete to manage entries. Deletion takes effect
when saved and does not delete log files, SSH Hosts, SSH Keys, or known_hosts files.
For Remote File, enter a reusable remote path; choose source **SSH Hosts** per
Source in Tasks, using searchable checkboxes, Select all shown, and Clear.
connection credentials are managed in **Settings → SSH Hosts**.

| Type | Location and requirements |
| --- | --- |
| Local File | Readable UTF-8 regular files on the DeciFlow node; relative paths start at its working directory |
| Remote File (SSH) | UTF-8 regular files on an SSH/SFTP host; absolute POSIX paths, key authentication, and host-key verification |
| HDFS (Native) | Native Hadoop client; Batch-only UTF-8 TEXT/JSONL with absolute HDFS paths |
| HDFS (WebHDFS) | HTTP(S) WebHDFS client; the same Batch formats and path rules |

Local and SSH paths accept `*`, `?`, `[abc]`, and recursive `**` patterns. A registration can
match multiple files. Initial examples are Sample System Messages, Sample HTTP access,
and Sample SSH authentication; edit them for your environment. Registered names
and IDs must be unique. Renaming preserves the ID.

**File Path / Pattern** accepts one path or pattern per line for both Local File
and Remote File. Blank lines and duplicate entries are removed on save. All
entries share the Task row's Criteria, chunk size, Action, and Source Hosts.
Overlapping matches within a Source are read once; SSH reuses one connection per
Source/Host. Batch fails if an entry matches no regular files; Realtime keeps
watching for new matches.

## Input Format

Select **Input Format** independently of Local File or Remote File (SSH).
Existing Sources default to **TEXT (Chunk)**: nonempty lines are grouped using
Task Events/Chunk. **JSONL (Line)** reads one JSON object per nonempty line and
requires a **Content Field**, a literal top-level key containing nonempty text.
The Task fixes Events/Chunk to 1 for JSONL. Escaped newlines remain inside one
record, and repeated records are processed independently without deduplication.

For the supplied consultation sample, use
`/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl` and `consulting_content`;
for the other consultation sample, use `/host-logs/sample-logs/voc-central-gov-consulting-qna.jsonl` and
`consulting_content`. These paths assume the Compose host sample mount.

Local and SSH use the same parser in Batch and Realtime. Malformed objects,
missing/nontext fields, and incomplete records at rotation become individual
failures; subsequent records continue. Results retain canonical `log`, remaining `inputRecord` metadata on success,
`inputContentInLog: true`, and `recordNumber` (file line or
observed line in Realtime). Malformed raw input is preserved as `rawInput`. Blank lines are skipped. Nested field paths, JSON
arrays, multiline JSON objects, and CSV are not supported in this version.

## Select sources in Tasks

In Batch or Realtime, add a selection row and choose a registered Source from
the dropdown. Source and Action dropdowns always show all available entries in
alphabetical/Korean name order, including when an entry is already selected.
The selected file path or pattern appears below Source; option tooltips include
its type and path. Select None for no Action. Text filtering is not used.

Choose Criteria, Events/Chunk, and Action per row. These are saved in the Task, not the
source registration. Batch reads matching files to EOF; Realtime skips existing
content, follows new lines, and discovers new matching files from their beginning.
Main lists enabled Tasks, with running/starting Tasks first. Click one for its
current/latest results; open older runs through Tasks → History → View Results. There is no Paste input mode.
**Reset Selections** selects available sample sources (or the first registered
source) with one event per chunk and Action None. Save the Task to retain these settings on the server.

Local overlapping matches with identical settings are deduplicated; conflicting
settings are rejected. Remote registrations are read independently, so avoid
selecting overlapping remote registrations in the same run. Chunks never mix
files. Local and remote inputs use the same Laya/Jev classification and Action flow.

## SSH configuration

In Settings, **SSH Hosts** follows **SSH Keys**. Use Add Host to save a name,
address, port, SSH User, and key. The searchable list provides View, Edit, and
Delete controls. Multiple Sources can share a Host and use different file paths.
Task Source selections store `hostIds`; connection details are resolved and frozen
for each new run. Host edits apply to new runs, while running jobs keep their snapshots.
Deletion requires confirmation and is blocked while a saved Task or running job
references the Host. A key referenced by any saved Host cannot be deleted.

These fields belong to a Host in Settings:

| Field | Meaning |
| --- | --- |
| Host | Hostname or IP, without ssh:// or username |
| Port | SSH Port, default 22 |
| SSH User | Account with read permission on the remote logs and access to the SFTP subsystem |
| SSH Key | Select a key registered in Settings; existing file-path registrations remain supported |

Use a key which can be loaded without a passphrase prompt. Password authentication,
agent authentication, interactive login prompts, and disabling host verification are not
supported. Add the matching public key to the remote account's authorized_keys.
Use Test Connection to review and approve an unknown server fingerprint through a
trusted channel. Approvals are stored in `DECIFLOW_DATA_DIR/ssh-hosts/known_hosts`
and shared by connection testing and Remote File reads. DeciFlow does not read or modify
`~/.ssh/known_hosts` or `/etc/ssh/ssh_known_hosts`. CLI approvals are separate. Nonstandard ports use `[hostname]:port`. Changed or revoked
keys are rejected; verify the host and repair the relevant known_hosts entry.


DeciFlow uses SFTP, not remote shell commands, and never stores key contents or
passwords in the registry. SSH/SFTP failures record a Source/Host error while other
hosts continue; there is no automatic reconnect. Stop closes the SFTP session and pending reads.

Remote Realtime detects truncation and replacement using file size and a leading
byte comparison. A replacement with the same leading bytes and size at least the
previous offset can be missed. Confirm rotation behavior for your log writer.

### Test Connection

Use **Test Connection** on each SSH Hosts row or in Add/Edit before saving.
The test checks SSH Key authentication, host verification, and SFTP access with a
15-second overall timeout. It closes the connection, reads no logs, and does not
save draft settings. Unknown fingerprints require confirmation before retrying;
only the explicitly approved key is trusted and persisted after SSH authentication.
It uses the same settings as Remote File.
The list shows Not checked, Checking, Connected, or Failed with the last check time
and error. Each visit to SSH Hosts checks hosts sequentially once in name order.
View, list redraws, and periodic timers do not repeat completed checks. Returning
through the sidebar starts a new pass; Test Connection always permits a manual
check. Leaving Settings, opening an editor, or hiding the browser tab pauses
remaining checks after the current request.
Automatic checks never approve unknown fingerprints or open dialogs: use manual
Test Connection to approve a new key. Results reset when the page reloads. Changing connection details invalidates the displayed
result. A successful test does not verify any particular log path or file permissions.

`POST /api/ssh-hosts/test` accepts `{ "id": "saved-host-id" }` or complete
unsaved host fields, using the same trusted-origin checks as host management.
It returns `connected`, `checkedAt`, `elapsedMs`, and `error` on connection failure.
An unknown key also returns `hostKey` with its public key and SHA256 fingerprint.
After verifying it, repeat the request with `trustedHostKey` set to that public key.


## SSH Keys in Settings

Open **Settings → SSH Keys** in the sidebar (`/#settings/ssh-keys`). Enter a key name
(letters, digits, spaces, underscores, or hyphens) and select one registration method.
The default view is a searchable list of names, private-key paths, and management
buttons. **Add Key** opens the registration form; **View** opens details; **Edit**
renames the key without replacing key material. Names must remain unique.

- **Upload Private Key:** select a file from the computer running your browser.
- **Private Key File Path:** enter a file path accessible to the DeciFlow process
  (inside the container when using Docker). The file is copied into managed storage.
- **Paste Private Key:** paste the complete private key, including header/footer
  lines. The input is masked and cleared after each submission.

All three methods accept a dedicated private key without a passphrase, up to
64 KiB, and automatically derive its public key. Original files are unchanged.
Select the registered key in an **SSH Host**, then select that Host in the Task's
Remote File Source row.

Pairs persist under `DECIFLOW_DATA_DIR/ssh-keys/<key-id>/` in the `deciflow-data`
volume: `private_key` (0600) and `public_key.pub` (0644), in a directory with 0700
permissions. UUID and Name metadata are stored in SQLite. SSH Hosts persist `keyId`;
key paths are resolved at execution time. Renaming never moves files or changes
Host references. Settings shows the private key's path with its contents masked as
`****`, and the public key's path and contents. It never returns private key
contents. Deleting a pair requires a
confirmation and is rejected while a saved SSH Host or running job references it.
Remove or change those references first. Deletion permanently removes both files.

For an existing key on the DeciFlow host, use the file-path method; for a key on
your browser computer, use upload or paste. SSH Hosts select registered keys by UUID. Settings only manages pairs in `ssh-keys`;
it does not automatically scan or delete keys elsewhere on the host.

Keys are stored without encryption at rest. Protect access to Settings, the host,
and volume backups; Python Actions run with DeciFlow permissions and can access
these files. The volume backup includes private keys. Browser uploads should use
HTTPS when accessing DeciFlow over a network.

Host verification uses only `DECIFLOW_DATA_DIR/ssh-hosts/known_hosts`
(default `/var/lib/deciflow-data/ssh-hosts/known_hosts`). No user SSH-file mount is
needed. Test Connection opens an in-app fingerprint dialog with Cancel and Trust & Connect.
It stores approved keys here; the same key reconnects without another prompt.
Scheduled/background Tasks cannot show a prompt: approve a new Host with Test
Connection before running a Task. Existing approved keys remain across restarts.
No SSH executable is required; AsyncSSH is a project dependency.


### Remote File polling

Realtime reuses file attributes from each SFTP directory/glob scan and resolves
regular-file parent paths once per directory. Changed files wake their readers;
unchanged files are not reopened on every scan. Discovery scans still run at
250 ms intervals after each scan completes, subject to network/server latency.
A one-second prefix check also detects same-size replacements when SFTP timestamp
precision hides a change. File offsets, partial-line handling, host fairness,
chunking, and the shared engine concurrency limit are unchanged. Very rapid
rotation between checks can still lose events.

## HDFS

Choose **HDFS (Native)** or **HDFS (WebHDFS)** in Source Type. Both support Batch
reading, connection tests, and AI Criteria sample previews. DeciFlow uses the selected
transport and never automatically switches between them.

### Native

Use `call518/deciflow-ui:0.0.2` for native Hadoop Batch reads. Native DeciFlow
installations need PyArrow, Java, `libhdfs`, and the Hadoop environment variables
shown in the Dockerfile. Shell commands are not used for application reads.

The image supplies Hadoop's standard `etc/hadoop` templates in `/etc/hadoop/conf`,
including `core-site.xml`, `hdfs-site.xml`, `hadoop-env.sh`, policies, metrics, and
SSL examples. Set your cluster-specific properties or mount your cluster files.
A directory mount replaces the image's entire configuration directory; mount
individual XML files to retain the other bundled defaults. Templates contain no
cluster address or credentials; `fs.defaultFS` still needs an HDFS URI when using
`default`.

For **File Path / Pattern**, enter HDFS paths such as `/warehouse/events/part-*.jsonl`,
without an `hdfs://` prefix; connection settings are separate.

Register HDFS (Native) with one **Endpoint**, optional **User**, and optional
**Kerberos Ticket Cache**:

- `hdfs://namenode.example.test:8020`: explicit NameNode and RPC port.
- `hdfs://nameservice1`: logical HA nameservice; cluster XML configuration is required.
- `default`: use `fs.defaultFS` from XML files in `HADOOP_CONF_DIR`
  (image default: `/etc/hadoop/conf`). The configured default filesystem must use `hdfs://`.

Ports omitted from a URI use Hadoop defaults or HA configuration. File paths belong
in **File Path / Pattern**, not in Endpoint. DeciFlow parses the URI into the host
and port required by the native client. Mount the configuration
in the UI container, for example with these additional `services.ui.volumes` entries:

```yaml
- /path/to/core-site.xml:/etc/hadoop/conf/core-site.xml:ro
- /path/to/hdfs-site.xml:/etc/hadoop/conf/hdfs-site.xml:ro
- /path/to/krb5.conf:/etc/krb5.conf:ro
- /path/to/ticket-cache:/run/hdfs-ticket:ro
```

For Kerberos, enter `/run/hdfs-ticket` as the cache path. Provision and renew tickets
externally; DeciFlow does not store passwords, run `kinit`, or renew tickets. User is
optional for Hadoop simple authentication. The UI container must resolve and reach
both the NameNode and advertised DataNode addresses. **Test Connection** lists files
and reads one byte from the first file; saving and opening Views never connect.

The image also includes `hdfs` and `hadoop` for manual diagnostics. With the
cluster XML configuration mounted, list the HDFS root from the UI container:

```bash
docker compose exec ui hdfs dfs -ls /
```

Without `fs.defaultFS` configured, specify the endpoint explicitly:

```bash
docker compose exec ui hdfs dfs -fs hdfs://namenode.example.test:8020 -ls /
```

Source settings in SQLite are not automatically applied to CLI commands. CLI
simple authentication uses the process user or `HADOOP_USER_NAME`; Kerberos can
use `KRB5CCNAME` for the mounted ticket cache. Without cluster configuration or
an explicit `-fs`, Hadoop defaults to the local filesystem, so `/` may be local.

### WebHDFS

Set **Endpoint** to the NameNode or HttpFS base URL, for example
`http://namenode.example.test:9870` or `https://gateway.example.test:14000`.
An optional `/webhdfs/v1` suffix is accepted. Set HDFS paths separately in
**File Path / Pattern**. Hadoop XML files and the native JVM client are not used.
DeciFlow must reach both the endpoint and the DataNode HTTP addresses returned by
OPEN redirects. HTTPS-to-HTTP redirects are rejected.

**User** optionally supplies Hadoop simple authentication. For secured clusters,
mount a file containing an externally issued WebHDFS delegation token and set
**Delegation Token File** to its absolute path inside DeciFlow. The token takes
precedence over User; its contents are not stored in Source settings or results.
DeciFlow does not issue or renew tokens, and direct Kerberos SPNEGO is unsupported.
Only use trusted endpoints, since the token is sent to the configured service.
HTTPS certificate verification is always enabled; optionally mount a PEM CA bundle
and set **Trusted CA File** for a private CA. Token and CA files must remain
available for active runs and recovery. Never place tokens in the endpoint URL.

### Shared Behavior

Use absolute file paths, directories (recursive reads), or component patterns
`*`, `?`, `[abc]`, one per line. Use a directory instead of `**`. Only uncompressed
UTF-8 TEXT and JSONL are supported; Parquet and ORC are unsupported. Physical lines
are limited to 16 MiB. JSONL parsing, Criteria, and Actions use the shared pipeline.

Batch freezes its file list, removes overlapping matches, and rejects conflicting
assignments for the same URI. Up to four HDFS files are read concurrently with
bounded buffers; classification uses the engine concurrency limit. Keep files
unchanged during execution. Recovery retains the file list and checks file metadata
and checkpoint prefixes before resuming. Changed or missing files produce failures;
new files are excluded. New runs read from the beginning again. Exactly-once external
Actions across crashes are not guaranteed.

Sample preview retains the whole-Source scan, 20-second deadline, and byte budget;
large Sources may time out, requiring narrower preview paths. Only edited samples
are sent for AI Criteria generation. Realtime and distributed workers are outside
this implementation. `POST /api/sources/hdfs-test` tests a draft Source with the same
trusted-origin policy as Source management.

## Storage and API

SSH Host listing, registration/editing, and deletion use `POST`, `PUT`, and
`DELETE` on `/api/ssh-hosts`. Hosts persist in
`DECIFLOW_DATA_DIR/deciflow.sqlite3`.
SSH Key listing, import, rename, and deletion use `POST`, `PUT`, `PATCH`, and `DELETE` on
`/api/ssh-keys` with the same trusted file-access origins as Sources.

Definitions are stored as individual records in `DECIFLOW_DATA_DIR/deciflow.sqlite3`.
Compose's `deciflow-data` volume already covers this database. Saving applies to
new runs; active jobs retain their source snapshots.

Management uses `POST /api/sources` to read and `PUT /api/sources` to replace the
list. Both require the same local/trusted UI Origin as file access. Saving validates
the Source name, type, and path without connecting to SSH.
Tasks saves source IDs and hostIds with execution settings. Remote File example
for `POST /api/file-source` (Local File omits hostIds):

```json
{
  "mode": "batch",
  "sources": [
    {"sourceId": "<registered-source-id>", "profile": "4e6d5417-611e-49e0-8e23-2444a0f49ee4", "chunkEvents": 1, "actionId": "", "hostIds": ["<ssh-host-id>"]}
  ],
  "persist": true
}
```

The server resolves IDs from the registry; supplied connection/path overrides are
ignored. The file API also supports explicit local paths for programmatic clients.
Results include `sourceId`, `sourceName`, and `sourceType` for registered inputs.
Remote results and Action input also include `hostId`, `hostName`, `hostAddress`,
`hostPort`, and `chunkSequence`. Host filtering does not repeat inference.
Remote `source` and `sourcePatterns` use `ssh://user@host:port/path` to distinguish
hosts. Credentials and SSH Key Paths are not added to classification requests or
result records. See [request/result JSON](results.md).

**Sample VOC Asia Culture Center Consulting QnA** is provided automatically at startup with Local File,
JSONL (Line), `/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl`, and Content
Field `consulting_content`. Existing registrations are preserved; an equivalent
local path is reused. A disabled manual VOC Task is also provided; it never starts automatically. The path assumes
the Compose sample mount; adjust it for other installations.

Sources remain editable, including Type, while Tasks reference or use them. The
editor shows usage; current runs keep their resolved Source snapshots and new runs
use saved edits. Review Task host assignments after changing Type: SSH requires
SSH Hosts, while other Types do not accept them. Validation blocks invalid starts.
Deletion remains blocked by saved references, starting/active runs, and persisted
recoverable runs.

The government sample also provides a Source, Korean Criteria, and a disabled
Batch Task at startup. See [Sample VOC Central Gov Consulting QnA](voc.md#government-qna-sample).
