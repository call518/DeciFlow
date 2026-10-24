# OAuth2-Proxy 바이너리 설치

[English](oauth2-proxy-install.md) | [uv tool 설치](tool-install.ko.md) | [네이티브 설치](native.ko.md)

**OAuth2-Proxy**는 DeciFlow의 Google 로그인과 HTTPS 진입점을 제공합니다.
이 안내는 `OAUTH2_PROXY_ENABLED=true`를 사용하는 **uv tool·Git 복제 기반 네이티브 설치**에
적용됩니다. Docker Compose는 전용 OAuth2-Proxy 이미지를 사용하므로 호스트 바이너리가
필요하지 않습니다. 인증 없는 HTTP 모드에도 OAuth2-Proxy는 필요하지 않습니다.

## 다운로드·검증·설치

DeciFlow를 실행할 계정으로 진행하세요. `curl`, `tar`, `install`,
`sha256sum`(Linux) 또는 `shasum`(macOS)과 GitHub 다운로드 연결이 필요합니다.
아래 명령은 고정 버전 **v7.15.5**를 `~/.local/bin`에 설치하며 OS 서비스는 등록하지 않습니다.
체크섬은 [공식 릴리즈](https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.5)와
일치합니다. Linux/WSL2·macOS의 amd64·arm64를 지원합니다.

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

`export PATH="$HOME/.local/bin:$PATH"`를 사용하는 셸의 시작 파일
(`~/.bashrc` 또는 `~/.zshrc` 등)에 추가하고 새 터미널을 여세요.
호스트 서비스 관리자를 사용한다면 해당 서비스에서도 실행 파일을 찾도록 PATH를 설정해야 합니다.
pytest용 `OAUTH2_PROXY_BINARY` 변수는 런타임 실행 파일을 지정하지 않습니다.
DeciFlow는 PATH의 `oauth2-proxy`를 사용합니다.

## DeciFlow 설정과 확인

바이너리 설치만으로 인증이 활성화되지는 않습니다. Google 인증 정보, 이메일 허용 목록,
도메인과 일치하는 TLS 인증서·개인 키를 준비하세요.

- **uv tool:** `~/.config/deciflow/.env`와 `~/.config/deciflow/oauth2-proxy/`,
  또는 `--config-dir`로 지정한 디렉터리를 사용합니다. [Google 로그인](tool-install.ko.md#선택적-google-로그인)을 따르세요.
- **Git 복제 기반 네이티브:** `<checkout>/.env`와 `<checkout>/oauth2-proxy/`를 사용합니다.
  [네이티브 인증 설정](native.ko.md#선택-oauth2-proxy를-통한-네이티브-https)을 따르세요.
- 인증서 발급은 [DNS/TLS 준비](dns-tls.ko.md)를 참고하세요. 해당 문서의 Docker 배포
  hook과 UID 지침은 네이티브 프로세스에 적용하지 않습니다.

필요한 파일과 설정값을 준비한 뒤에만 `OAUTH2_PROXY_ENABLED=true`로 설정합니다.
uv tool 설치에서는 다음 명령을 사용하세요.

```bash
deciflow config test
deciflow start --daemon
deciflow status
deciflow stop
```

Git 저장소에서는 `uv run deciflow`와 `--config-dir "$PWD"`를 사용합니다.
DeciFlow가 포그라운드·데몬 모드 모두에서 바이너리를 자동으로 기동하고 관리합니다.
바이너리나 인증서를 교체한 뒤에는 DeciFlow를 종료하고 다시 기동하세요.
OAuth2-Proxy를 자동으로 설치하거나 업그레이드하지는 않습니다.
