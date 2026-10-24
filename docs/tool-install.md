# Install the DeciFlow Command

[한국어](tool-install.ko.md) | [Project README](../README.md)

This is the recommended installation method. Install DeciFlow from PyPI
without cloning the repository or using Docker.
The second choice is [Docker](../README.md#alternative-installation-docker--laya-cpu), followed
by [Git checkout native](native.md). Choose one method for each installation.

**DeciFlow** serves the UI/API and reads your sources. The **Laya server** runs
inference separately; **Jev** is an alternative paid hosted inference API.
Installing DeciFlow does not start Laya or install OAuth2-Proxy.

## Install and Initialize

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.11+
(3.12 recommended), and dependency download access. Linux/WSL2 is the reference
environment. HDFS, SSH, and Actions retain their documented external prerequisites.

Install and initialize:

```bash
uv tool install deciflow
deciflow init
```

If the shell cannot find `deciflow`, run `uv tool update-shell` and open a new shell.

`deciflow init` creates `~/.config/deciflow/.env` with private file permissions
and prepares OAuth2-Proxy templates. It does not test configuration or start a
server. Edit the generated file before starting `deciflow start`.
Existing configuration files are never overwritten. No domain, certificate, or
Google configuration is needed with `OAUTH2_PROXY_ENABLED=false`.
The default path belongs to the user running the command; root uses
`/root/.config/deciflow/.env`. A repository or current-directory `.env` is not
automatically read. See [environment file locations](configuration.md#environment-file-locations)
before switching installation methods.

## Connect an Engine and Start

Choose **one** engine. Start an external Laya server using the
[native Laya guide](native.md) or your existing deployment, then set:

```dotenv
DECISION_ENGINE=laya
LAYA_API_URL=http://127.0.0.1:8000/v1/systemone
LAYA_API_KEY=your-laya-server-key
```

Use the address and key of your actual Laya server. For the paid Jev service:

```dotenv
DECISION_ENGINE=jev
JEV_API_KEY=your-jev-api-key
```

Prepare the default storage directories with write access for the user who will
run DeciFlow. This one-time administrative command creates them if needed:

```bash
sudo install -d -o "$(id -un)" -g "$(id -gn)" \
  /var/lib/deciflow-data /var/log/deciflow
```

Alternatively, set `DECIFLOW_DATA_DIR` and `DECIFLOW_LOG_DIR` to your own writable
directories and create them before startup. Then run:

```bash
deciflow start
```

Open `http://127.0.0.1:4000`. Check the engine status before running a Task.
Every `deciflow start` startup, including UI Restart, first runs the complete
configuration test. The server starts only if all checks pass. A missing Jev key,
an unreachable engine, or another failed prerequisite blocks startup. It never
creates a missing `.env` automatically; use `deciflow init`. There is no automatic
fallback to Jev.

The generated configuration uses loopback HTTP. A blank `DECIFLOW_DATA_DIR` uses
`/var/lib/deciflow-data`; `DECIFLOW_LOG_DIR` defaults to `/var/log/deciflow`, matching
Docker's in-container paths. Missing or unwritable directories stop the installed
command with a short error and a `config test` command; it never switches to a home directory.
An empty `DECIFLOW_LOG_DIR` keeps console logging only.
Relative Source and Action paths resolve from the configuration directory.
Built-in Docker sample Sources use `/host-logs/...`; create or edit a Source to
point to an actual local file for this installation. Ctrl+C stops the application.

## Start, Status, and Stop

CLI process management supports Linux, WSL2, and macOS. Run in the foreground or
choose daemon mode; do not run both for the same configuration:

```bash
deciflow start
deciflow start --daemon
deciflow status
deciflow stop
```

`deciflow` without a command displays help. Foreground execution stops with Ctrl+C.
`--daemon` detaches from the terminal and returns only after the UI and, when
enabled, OAuth2-Proxy are listening. It prints the PID, URL, configuration, and
`DECIFLOW_LOG_DIR/daemon.log`. This file captures startup diagnostics, general console,
and proxy output. Uvicorn server/access records go only to `server.log` and
`access.log`, respectively, without duplication in `daemon.log`; their existing
rotation is retained. The daemon log appends across
runs; configure host log retention as needed. Daemon mode requires a nonempty,
existing, writable `DECIFLOW_LOG_DIR`.
See [Logging](configuration.md#logging) for the three log files, troubleshooting, and recording limits.

A configuration directory can have only one CLI-managed process. `status` and
`stop` use a private local control socket, not a saved PID to signal. They do not
require valid engine credentials or a reachable engine. `status` returns exit code
`0` for an active/starting process and `3` when stopped. `stop` is idempotent and
waits up to 30 seconds for graceful shutdown; a timeout reports failure without
force-killing an arbitrary process. Data and recovery checkpoints are preserved.
UI Restart keeps the managed process and its daemon mode.

When `OAUTH2_PROXY_ENABLED=true`, both run modes start the installed OAuth2-Proxy
binary and stop it with DeciFlow. Laya is a separate service and is never stopped
by these commands. Docker containers and directly launched `server.py` processes
are not managed by this CLI. A daemon is not an installed OS service: there is
no automatic start on boot or restart after a crash.

For a custom configuration, pass the same directory to each command:

```bash
deciflow start --daemon --config-dir /path/to/deciflow-config
deciflow status --config-dir /path/to/deciflow-config
deciflow stop --config-dir /path/to/deciflow-config
```

## Configuration and Storage

To select another configuration directory, use the same option for all commands:

```bash
deciflow init --config-dir /path/to/deciflow-config
deciflow config list --config-dir /path/to/deciflow-config
deciflow config test --config-dir /path/to/deciflow-config
deciflow start --config-dir /path/to/deciflow-config
```

That directory holds `.env` and `oauth2-proxy/`; data and logs use their configured
storage paths independently of `--config-dir`.
The command does not automatically load `.env` from your current shell directory
or a separate Git checkout. To use an existing native checkout's configuration,
explicitly select it with `--config-dir /path/to/DeciFlow`.

`DECIFLOW_DATA_DIR` controls database, Actions, and SSH key storage;
`DECIFLOW_LOG_DIR` controls server/access logs. Preserve these directories and
credentials when replacing or upgrading the installed application. They are
separate from the tool's installed package and are not removed by uninstalling it.
Environment and saved UI override precedence follows [Configuration](configuration.md).

## Check the Configuration

Run before starting DeciFlow, with the same configuration directory:

```bash
deciflow config test
deciflow config test --config-dir /path/to/deciflow-config
```

Choose the command matching your installation. Checks continue after individual
failures and end with **Config Test Passed** or **Config Test Failed**. Terminal
output uses green **Passed** and bright red **Failed**; redirected output is plain
text, and `NO_COLOR` disables colors. Exit status is `0` for success and `1` for failure.

Use `init` to create templates, `config test` to diagnose readiness, and
`deciflow start` to validate and start. `init`, `config test`, `config list`, and help do
not start the server; only server startup requires the full readiness check.

The check covers `.env` syntax, bundled UI resources, data/log write permissions,
existing database access and saved UI overrides, engine settings and non-inference
health/authentication requests, the `uv` executable, and available UI ports.
When OAuth2-Proxy is enabled, it also checks the executable, credentials, cookie
key format, HTTPS origin, policy, email allow-list, matching TLS files, certificate
dates/hostname, and HTTPS listener port. Disabled authentication needs no TLS files.

It does not create templates or databases, start servers, install dependencies,
or submit inference. Permission checks use temporary files that are immediately
removed. It uses the same saved UI overrides as startup. An already running
DeciFlow can cause the port checks to fail; stop it before this pre-start check.
Google client registration, public DNS/NAT reachability, certificate-chain trust,
real inference/model availability, and individual Source/Action requirements still
need runtime verification. Startup performs the same checks but prints only their
overall result; use `config test` for individual results and preparation guidance.
Failures discovered after the check give a short error and point to `config test`.

## List Effective Settings

```bash
deciflow config list
deciflow config list --config-dir /path/to/deciflow-config
```

Choose the command for your installation. The listing shows known application
settings and their source: **UI Override**, **Environment** (including `.env`),
**Default**, or **OAuth2-Proxy** for the protected browser origin. The data path is
resolved even when the environment entry is blank. API keys and secrets are
redacted; URL credentials, query values, and fragments are hidden. It does not
probe engines, initialize a database, or require all readiness checks to pass.

## Optional Google Sign-In

Follow [native authentication](native.md#optional-native-https-with-oauth2-proxy) and
[DNS/TLS preparation](dns-tls.md). Follow [binary installation](oauth2-proxy-install.md)
to install and verify the OAuth2-Proxy executable on PATH,
configure Google credentials and `OAUTH2_PROXY_PUBLIC_URL`, and prepare:

```text
<workspace>/oauth2-proxy/oauth2-proxy.cfg
<workspace>/oauth2-proxy/allowed-emails.txt
<workspace>/oauth2-proxy/tls/fullchain.pem
<workspace>/oauth2-proxy/tls/privkey.pem
```

The command seeds the policy and `allowed-emails.example.txt`; copy the email
template to `allowed-emails.txt` and edit it. Set `OAUTH2_PROXY_ENABLED=true` only
after completing setup. Missing binaries, credentials, certificates, or allow-list
files stop startup with an error and a `config test` command. It does not fall back to
an unprotected HTTP listener.

## Update or Remove

```bash
uv tool upgrade deciflow
uv tool uninstall deciflow
```

## Publish from a Git Tag

Maintainers publish with `.github/workflows/pypi-publish.yml`. A pushed tag starts
Python 3.12 tests, builds an sdist and wheel, verifies their versions against the
tag, and tests the installed wheel. The same artifacts are uploaded to **TestPyPI
first**, then **PyPI** only after TestPyPI succeeds. Normal branch pushes do not
publish packages; the separate pytest workflow checks Python 3.11 and 3.12.

`pyproject.toml` uses `dynamic = ["version"]` and Hatch's `hatch-vcs` plugin
(backed by `setuptools-scm`). A clean `0.5.7` or `v0.5.7` tag produces package
version `0.5.7`; these are examples, not a selected release version. Canonical
prerelease tags such as `0.5.7rc1` are also accepted and publish to both indexes.
Commits after a tag or a modified checkout produce development versions. CI fetches
full Git history so version detection works. No manual version edit or API token
is needed. Install Git when building from a checkout; published sdists retain
version metadata so wheel builds from an sdist do not need Git history.

Before the first tag push:

1. On GitHub, configure repository **Settings → Environments** named `testpypi`
   and `pypi`. Ensure any deployment restrictions allow release tags. Required
   reviewers, if configured, pause the corresponding publishing job for approval.
2. On **each** index, register a Trusted Publisher with project name `deciflow`,
   owner `call518`, repository `DeciFlow`, workflow `pypi-publish.yml`, and its
   matching environment (`testpypi` or `pypi`). A Pending Publisher creates the
   project on the first successful upload; it does not reserve the project name.
3. Commit the release changes, including this workflow, and create and push the
   chosen version tag on that commit. Pushing an old commit without this workflow
   does not use the new release process.

Publishing uses GitHub OIDC with `id-token: write` only in the publishing jobs.
The workflow does not create tags, commits, or GitHub Releases. Existing package
versions cannot be overwritten. If TestPyPI succeeds but PyPI fails, fix the cause
and rerun the failed job in the same workflow run to reuse its artifacts.
Installing or running local checks does not upload anything.

## Verify a Distribution

From the Git checkout, build an sdist and wheel, then test the wheel:

```bash
uv build
uv run python scripts/check_distribution.py dist/*.whl
```

Use an output directory containing only the wheel being tested. The check creates
an isolated temporary uv tool installation outside the checkout, verifies bundled
UI resources and private-file exclusion, and starts, restarts, and stops the installed server.
It requires dependency download access and makes no inference requests. GitHub
Actions runs this check after pytest on both Python 3.11 and 3.12.
