# Install the OAuth2-Proxy Binary

[한국어](oauth2-proxy-install.ko.md) | [uv tool Installation](tool-install.md) | [Native Installation](native.md)

**OAuth2-Proxy** provides Google sign-in and the HTTPS entry point for DeciFlow.
This guide applies to **uv tool and Git checkout native installations** with
`OAUTH2_PROXY_ENABLED=true`. Docker Compose uses its own OAuth2-Proxy image and
does not need a host binary. Unauthenticated HTTP mode needs no OAuth2-Proxy.

## Download, Verify, and Install

Run as the account that will start DeciFlow. Requires `curl`, `tar`, `install`,
and `sha256sum` (Linux) or `shasum` (macOS), plus GitHub download access.
The commands install the pinned **v7.15.5** release in `~/.local/bin`; no system
service is installed. Checksums match the
[official release](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.5).
Linux/WSL2 and macOS on amd64/arm64 are covered.

```bash
(
  set -eu
  proxy_version=7.15.5
  case "$(uname -s)" in
    Linux) proxy_os=linux ;;
    Darwin) proxy_os=darwin ;;
    *) echo "Use Linux/WSL2 or macOS for this guide" >&2; exit 1 ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) proxy_arch=amd64 ;;
    aarch64|arm64) proxy_arch=arm64 ;;
    *) echo "Unsupported CPU architecture" >&2; exit 1 ;;
  esac
  case "$proxy_os-$proxy_arch" in
    linux-amd64) proxy_sha256=f63f94bf72c5f46ab002a0a275aa8b3cf19b4d828aed08a13978cb9a62c3a1fd ;;
    linux-arm64) proxy_sha256=ebef73d06a05f76a03b0b2f95aa8424c10201228bd64621a2a7d375ce44dd637 ;;
    darwin-amd64) proxy_sha256=ad0a6bec165f6c88749ab94833a14c7be0e8ebcad07987eb080de78892d732bb ;;
    darwin-arm64) proxy_sha256=b8c9c86e5ad35808753c724e2a64af59ae066f31664973fd68f85bd0a7911ee3 ;;
  esac
  proxy_stem="oauth2-proxy-v$proxy_version.$proxy_os-$proxy_arch"
  proxy_temporary="$(mktemp -d)"
  trap 'rm -rf "$proxy_temporary"' EXIT
  cd "$proxy_temporary"
  curl --fail --location --retry 3 \
    "https://github.com/oauth2-proxy/oauth2-proxy/releases/download/v$proxy_version/$proxy_stem.tar.gz" \
    --output "$proxy_stem.tar.gz"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$proxy_sha256" "$proxy_stem.tar.gz" | sha256sum --check -
  else
    printf '%s  %s\n' "$proxy_sha256" "$proxy_stem.tar.gz" | shasum -a 256 --check -
  fi
  tar -xzf "$proxy_stem.tar.gz"
  install -d "$HOME/.local/bin"
  install -m 755 "$proxy_stem/oauth2-proxy" "$HOME/.local/bin/oauth2-proxy"
)
export PATH="$HOME/.local/bin:$PATH"
command -v oauth2-proxy
oauth2-proxy --version
```

Persist `export PATH="$HOME/.local/bin:$PATH"` in the startup file used by your
shell, such as `~/.bashrc` or `~/.zshrc`, and open a new terminal. A host service
manager must also receive this PATH or otherwise find the executable. The
`OAUTH2_PROXY_BINARY` variable used by pytest does not select the runtime binary;
DeciFlow locates `oauth2-proxy` on PATH.

## Configure and Check DeciFlow

The binary alone does not enable authentication. Prepare Google credentials,
the approved email list, a domain, and matching TLS certificate/private key:

- **uv tool:** use `~/.config/deciflow/.env` and `~/.config/deciflow/oauth2-proxy/`,
  or the directory selected by `--config-dir`; follow [Google sign-in](tool-install.md#optional-google-sign-in).
- **Git checkout native:** use `<checkout>/.env` and `<checkout>/oauth2-proxy/`;
  follow [native authentication](native.md#optional-native-https-with-oauth2-proxy).
- Follow [DNS/TLS preparation](dns-tls.md) for certificate issuance. Its Docker
  deployment hook and UID instructions do not apply to a native process.

Set `OAUTH2_PROXY_ENABLED=true` only after preparing the required files and values.
For uv tool:

```bash
deciflow config test
deciflow run --daemon
deciflow status
deciflow stop
```

Use `uv run deciflow` with `--config-dir "$PWD"` from a Git checkout instead.
DeciFlow starts and supervises the binary automatically in both foreground and
daemon mode. Stop and start DeciFlow after replacing the binary or certificates.
It does not automatically install or upgrade OAuth2-Proxy.
