#!/usr/bin/env bash
# Install the pinned native proxy without changing DeciFlow settings or services.
set -euo pipefail
proxy_version=7.15.5

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: bash scripts/install_oauth2_proxy.sh [INSTALL_DIR]"
  echo "Install OAuth2-Proxy $proxy_version; default: \$HOME/.local/bin."
  exit 0
fi
if [[ $# -gt 1 ]]; then
  echo "Expected at most one installation directory." >&2
  exit 2
fi
proxy_install_dir="${1:-$HOME/.local/bin}"
if [[ "$proxy_install_dir" != /* ]]; then
  echo "Use an absolute installation directory." >&2
  exit 2
fi
for proxy_tool in curl tar install mktemp uname; do
  command -v "$proxy_tool" >/dev/null || {
    echo "Required command not found: $proxy_tool" >&2
    exit 1
  }
done
if command -v sha256sum >/dev/null 2>&1; then
  proxy_checksum=(sha256sum --check -)
elif command -v shasum >/dev/null 2>&1; then
  proxy_checksum=(shasum -a 256 --check -)
else
  echo "Install sha256sum or shasum before continuing." >&2
  exit 1
fi

case "$(uname -s)" in
  Linux) proxy_os=linux ;;
  Darwin) proxy_os=darwin ;;
  *) echo "Supported platforms: Linux/WSL2 and macOS." >&2; exit 1 ;;
esac
case "$(uname -m)" in
  x86_64|amd64) proxy_arch=amd64 ;;
  aarch64|arm64) proxy_arch=arm64 ;;
  *) echo "Unsupported CPU architecture." >&2; exit 1 ;;
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
printf '%s  %s\n' "$proxy_sha256" "$proxy_stem.tar.gz" | "${proxy_checksum[@]}"
tar -xzf "$proxy_stem.tar.gz"
install -d "$proxy_install_dir"
install -m 755 "$proxy_stem/oauth2-proxy" "$proxy_install_dir/oauth2-proxy"
printf 'Installed: %s\n' "$proxy_install_dir/oauth2-proxy"
"$proxy_install_dir/oauth2-proxy" --version
