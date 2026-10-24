"""Report startup prerequisites without initializing the application or inference."""

import asyncio
import base64
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import ssl
import sys
import tomllib
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from cryptography import x509
from dotenv.parser import parse_stream

from deciflow.cli import GUIDE, check_storage_directory, storage_directories
from deciflow.config import Engine, get_engine, load_startup_settings
from deciflow.config_store import get_data_directory, get_database_path
from deciflow.native_proxy import proxy_enabled, proxy_origin
from deciflow.paths import RESOURCE_ROOT
from deciflow.runtime_config import FIELDS, effective_values
from deciflow.server import ASSETS, DEFAULT_LOG_DIR, _check_engine_connection


def list_configuration(directory: Path) -> None:
    """List known effective settings without inference, DB creation, or secret values."""
    original = Path.cwd()
    try:
        os.chdir(directory)
        read_environment(directory / ".env")
        overrides = read_overrides()
        effective = effective_values(overrides)
        defaults = {
            **{key: str(field[2]) for key, field in FIELDS.items()},
            "PORT": "4000",
            "DECIFLOW_BIND_HOST": "127.0.0.1",
            "DECIFLOW_DATA_DIR": "",
            "DECIFLOW_LOG_DIR": DEFAULT_LOG_DIR,
            "DECIFLOW_CSRF_TRUSTED_ORIGINS": "",
            "OAUTH2_PROXY_ENABLED": "false",
            "OAUTH2_PROXY_PUBLIC_URL": "",
            "OAUTH2_PROXY_CLIENT_ID": "",
            "OAUTH2_PROXY_CLIENT_SECRET": "",
            "OAUTH2_PROXY_COOKIE_SECRET": "",
            "LAYA_API_KEY": "changeme",
            "JEV_API_KEY": "",
            "OPENAI_API_KEY": "",
        }
        print(f"DeciFlow Configuration · {directory / '.env'}")
        for key, default in defaults.items():
            source = (
                "UI Override"
                if key in overrides and key in FIELDS
                else "Environment"
                if key in os.environ
                else "Default"
            )
            value = effective.get(key, os.getenv(key, default))
            if key == "DECIFLOW_DATA_DIR":
                value = str(get_data_directory())
                if not os.getenv(key, "").strip():
                    source = "Default"
            elif (
                key == "DECIFLOW_CSRF_TRUSTED_ORIGINS"
                and os.getenv("OAUTH2_PROXY_ENABLED") == "true"
            ):
                value = os.getenv("OAUTH2_PROXY_PUBLIC_URL", "")
                source = "OAuth2-Proxy"
            if key.endswith(("_KEY", "_SECRET")):
                value = "[Redacted]" if value else "(Not Set)"
            elif "URL" in key or key == "DECIFLOW_CSRF_TRUSTED_ORIGINS":
                value = ", ".join(
                    redact_url(part.strip())
                    for part in value.split(",")
                    if part.strip()
                )
            print(f"{key}={value or '(Empty)'} [{source}]")
    finally:
        os.chdir(original)


def redact_url(value: str) -> str:
    """Keep endpoint information while hiding URL credentials, queries, and fragments."""
    try:
        url = urlsplit(value)
    except ValueError:
        return "[Invalid URL]"
    return urlunsplit(
        (
            url.scheme,
            url.netloc.rsplit("@", 1)[-1],
            url.path,
            "[Redacted]" if url.query else "",
            "",
        )
    )


def check_resources() -> None:
    """Verify the UI assets and reference files needed by installed features."""
    paths = [RESOURCE_ROOT / "public" / name for name, _ in ASSETS.values()]
    paths.extend(
        [RESOURCE_ROOT / ".env.example", RESOURCE_ROOT / "docs" / "criteria.md"]
    )
    for path in paths:
        with path.open("rb"):
            pass


def read_environment(path: Path) -> bool:
    """Reject malformed lines without printing their potentially secret values."""
    with path.open() as source:
        for binding in parse_stream(source):
            if binding.error:
                raise ValueError(
                    f"Invalid .env syntax at line {binding.original.line}."
                )
    load_startup_settings(path)
    return True


def read_overrides() -> dict[str, str]:
    """Read existing UI overrides without creating a database or schema."""
    path = get_database_path()
    if not path.exists():
        return {}
    with path.open("r+b"):
        pass
    with closing(
        sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=2)
    ) as db:
        table = db.execute(
            "SELECT name FROM sqlite_master WHERE name='configuration_records'"
        ).fetchone()
        if table is None:
            return {}
        row = db.execute(
            "SELECT payload FROM configuration_records WHERE kind='settings' AND id='application'"
        ).fetchone()
    settings = json.loads(row[0]) if row else {}
    if not isinstance(settings, dict):
        raise TypeError("Saved application settings must be an object.")
    overrides = settings.get("runtimeOverrides", {})
    if not isinstance(overrides, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in overrides.items()
    ):
        raise ValueError("Saved runtime overrides must contain string settings.")
    return overrides


def check_listener(host: str, port: int) -> None:
    """Test binding without opening a listener or leaving a socket behind."""
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    for family, kind, protocol, _, address in addresses:
        with socket.socket(family, kind, protocol) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(address)


async def probe_engine(engine: Engine) -> None:
    """Reuse the UI's bounded, non-inference provider health check."""
    async with httpx.AsyncClient(timeout=5) as client:
        state = await _check_engine_connection(engine, client)
    if state != "connected":
        raise ValueError(
            f"Engine connection: {state}. Check the server address and credentials."
        )


def check_engine(overrides: dict[str, str]) -> Engine:
    """Validate the actual engine selected by saved UI overrides and environment."""
    engine = get_engine(effective_values(overrides))
    if engine.name == "jev" and not engine.api_key.strip():
        raise ValueError("Set JEV_API_KEY before using Jev.")
    return engine


def validate_proxy_setting(key: str) -> None:
    """Validate a required proxy setting without returning its value."""
    value = os.getenv(key, "").strip()
    if not value:
        raise ValueError(f"Set {key}.")
    if key == "OAUTH2_PROXY_COOKIE_SECRET":
        try:
            decoded = base64.b64decode(
                value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
            )
        except ValueError:
            raise ValueError(
                "Cookie secret must be a Base64-encoded 16, 24, or 32-byte key."
            ) from None
        if len(decoded) not in {16, 24, 32}:
            raise ValueError("Cookie secret must decode to 16, 24, or 32 bytes.")


def check_emails(path: Path) -> None:
    """Verify an explicit nonempty email allow-list without printing addresses."""
    emails = [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not emails or any(
        not re.fullmatch(r"[^@\s*]+@[^@\s*]+\.[^@\s*]+", email) for email in emails
    ):
        raise ValueError(
            "Add approved email addresses to allowed-emails.txt; comments start with #."
        )


def check_tls(directory: Path) -> None:
    """Check readable, matching TLS files and certificate validity dates."""
    cert = directory / "tls" / "fullchain.pem"
    key = directory / "tls" / "privkey.pem"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key, password=lambda: "")
    leaf = x509.load_pem_x509_certificate(cert.read_bytes())
    if not leaf.not_valid_before_utc <= datetime.now(UTC) < leaf.not_valid_after_utc:
        raise ValueError("TLS certificate is expired or not yet valid; renew it.")
    hostname = (urlsplit(proxy_origin()).hostname or "").encode("idna").decode("ascii")
    try:
        names = leaf.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound:
        raise ValueError(
            "TLS certificate requires Subject Alternative Names."
        ) from None
    matches = [str(address) for address in names.get_values_for_type(x509.IPAddress)]
    for name in names.get_values_for_type(x509.DNSName):
        name = name.lower()
        if name == hostname or (
            name.startswith("*.")
            and hostname.endswith(name[1:])
            and hostname.count(".") == name.count(".")
        ):
            matches.append(hostname)
    if hostname not in matches:
        raise ValueError("TLS certificate does not match OAUTH2_PROXY_PUBLIC_URL.")


def read_proxy_policy(path: Path) -> dict[str, Any]:
    """Read the native proxy policy without starting OAuth2-Proxy."""
    with path.open("rb") as source:
        policy = tomllib.load(source)
    if policy.get("provider") != "google" or policy.get("email_domains"):
        raise ValueError(
            "Use the Google provider with the project's email allow-list policy."
        )
    address = urlsplit("https://" + policy.get("https_address", "0.0.0.0:4443"))
    if not address.hostname or not address.port:
        raise ValueError("Set a valid https_address in oauth2-proxy.cfg.")
    if address.port == int(os.getenv("PORT") or "4000"):
        raise ValueError("OAuth2-Proxy and the UI require different listening ports.")
    return policy


def run_config_test(directory: Path, *, detailed: bool = True) -> int:
    """Run independent checks to completion; return zero only when all pass."""
    passed = failed = 0
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def check(label: str, action: Callable[[], Any], hint: str = "") -> Any:
        nonlocal passed, failed
        try:
            result = action()
        except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error):
            failed += 1
            mark = "\033[91mFailed\033[0m" if color else "Failed"
            if detailed:
                # Exception messages can contain configuration values or credentials.
                print(f"[{mark}] {label}", flush=True)
            if detailed and hint:
                print(f"         {hint}", flush=True)
            return None
        passed += 1
        mark = "\033[32mPassed\033[0m" if color else "Passed"
        if detailed:
            print(f"[{mark}] {label}", flush=True)
        return result

    if detailed:
        print(f"DeciFlow Config Test · {directory / '.env'}", flush=True)
    if not directory.is_dir():
        check("Configuration Directory", lambda: list(directory.iterdir()))
        if detailed:
            print(
                "Run: "
                + shlex.join(["deciflow", "init", "--config-dir", str(directory)])
            )
        mark = "\033[91mFailed\033[0m" if color else "Failed"
        print(f"\nConfig Test {mark}: 0 passed, 1 failed.")
        return 1
    original_directory = Path.cwd()
    try:
        os.chdir(directory)
        ready = check(
            "Environment File",
            lambda: read_environment(directory / ".env"),
            "Edit .env; use deciflow init with this --config-dir if the template is missing.",
        )
        check("Application Resources", check_resources)
        directories = check("Storage Settings", storage_directories)
        for key, path in directories or []:
            check(
                key,
                lambda key=key, path=path: check_storage_directory(key, path),
                "Create this directory and grant write access, or change its path in .env.",
            )
        overrides = check("Saved UI Settings", read_overrides)
        engine = (
            check("Engine Settings", lambda: check_engine(overrides))
            if ready and overrides is not None
            else None
        )
        if engine is not None:
            check(
                f"{engine.name.title()} Connection",
                lambda: asyncio.run(probe_engine(engine)),
            )
        check("uv for Action Environments", lambda: require_executable("uv"))
        mode = os.getenv("OAUTH2_PROXY_ENABLED", "false")
        label = {"false": "OAuth2-Proxy Disabled", "true": "OAuth2-Proxy Enabled"}.get(
            mode, "OAuth2-Proxy Mode"
        )
        protected = check(label, proxy_enabled)
        if protected is not None:
            host = (
                "127.0.0.1"
                if protected
                else os.getenv("DECIFLOW_BIND_HOST", "127.0.0.1")
            )
            check(
                "UI Listener",
                lambda: check_listener(host, int(os.getenv("PORT") or "4000")),
                "Stop an existing instance or choose another address/port.",
            )
        if protected:
            check("OAuth2-Proxy Executable", lambda: require_executable("oauth2-proxy"))
            for label, key in (
                ("OAuth2-Proxy Client ID", "OAUTH2_PROXY_CLIENT_ID"),
                ("OAuth2-Proxy Client Secret", "OAUTH2_PROXY_CLIENT_SECRET"),
                ("OAuth2-Proxy Cookie Secret", "OAUTH2_PROXY_COOKIE_SECRET"),
            ):
                check(
                    label,
                    lambda key=key: validate_proxy_setting(key),
                    "Set the corresponding credential in .env; the cookie secret must "
                    "be a Base64-encoded 16, 24, or 32-byte key.",
                )
            check("Public HTTPS Origin", proxy_origin)
            proxy = directory / "oauth2-proxy"
            policy = check(
                "OAuth2-Proxy Policy",
                lambda: read_proxy_policy(proxy / "oauth2-proxy.cfg"),
            )
            check(
                "Email Allow-List", lambda: check_emails(proxy / "allowed-emails.txt")
            )
            check("TLS Certificate and Key", lambda: check_tls(proxy))
            if policy is not None:
                address = urlsplit(
                    "https://" + policy.get("https_address", "0.0.0.0:4443")
                )
                check(
                    "HTTPS Listener",
                    lambda: check_listener(
                        address.hostname or "0.0.0.0", address.port or 443
                    ),
                )
    finally:
        os.chdir(original_directory)
    mark = "Passed" if not failed else "Failed"
    if color:
        mark = f"\033[{'32' if not failed else '91'}m{mark}\033[0m"
    print(f"\nConfig Test {mark}: {passed} passed, {failed} failed.")
    if failed and detailed:
        print(f"Setup guide: {GUIDE}")
    elif detailed:
        print("Ready to start DeciFlow.")
    return int(bool(failed))


def require_executable(name: str) -> None:
    """Check executable discovery without installing or launching processes."""
    if not shutil.which(name):
        raise ValueError(f"Install {name} on PATH.")
