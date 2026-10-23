"""WebHDFS transport for the shared immutable HDFS Batch reader."""

import io
import posixpath
import ssl
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import httpx

from deciflow.classifier import Result


class WebHDFSFileSystem:
    """Expose the file operations consumed by the shared HDFS reader."""

    def __init__(self, spec: Result) -> None:
        self.endpoint = spec["endpoint"]
        self.params = {}
        try:
            if spec.get("tokenFile"):
                token = Path(spec["tokenFile"]).read_text().strip()
                if not token or any(char.isspace() for char in token):
                    raise ValueError("Invalid WebHDFS delegation token file.")
                self.params["delegation"] = token
            elif spec.get("username"):
                self.params["user.name"] = spec["username"]
            verify = ssl.create_default_context(cafile=spec.get("caFile") or None)
        except (OSError, ValueError) as error:
            raise ValueError(
                "Cannot load the WebHDFS token or trusted CA file."
            ) from error
        self.client = httpx.Client(
            verify=verify, timeout=15, follow_redirects=False, trust_env=False
        )

    def close(self) -> None:
        """Release pooled HTTP connections after the reader finishes."""
        self.client.close()

    def _request(self, path: str, op: str, **params: Any) -> httpx.Response:
        url = f"{self.endpoint}/webhdfs/v1{quote(path, safe='/')}"
        try:
            request = self.client.build_request(
                "GET", url, params={**self.params, "op": op, **params}
            )
            response = self.client.send(request, stream=True)
            if op == "OPEN" and response.status_code == 307:
                target = urljoin(
                    str(response.url), response.headers.get("location", "")
                )
                response.close()
                parsed = urlsplit(target)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username is not None
                    or parsed.password is not None
                    or (urlsplit(url).scheme == "https" and parsed.scheme != "https")
                ):
                    raise ValueError("Unsafe WebHDFS DataNode redirect.")
                response = self.client.send(
                    self.client.build_request("GET", target), stream=True
                )
            if response.status_code != 200:
                status = response.status_code
                response.close()
                raise ValueError(
                    f"WebHDFS {op} failed (HTTP {status}). "
                    "Check the endpoint, file permissions, authentication, and DataNode access."
                )
            return response
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            # HTTP exceptions contain URLs, which may include delegation tokens.
            raise ValueError(
                f"WebHDFS {op} connection failed ({type(error).__name__})."
            ) from error

    def _json(self, path: str, op: str) -> dict[str, Any]:
        response = self._request(path, op)
        try:
            response.read()
            value = response.json()
            if not isinstance(value, dict):
                raise TypeError("Expected an object.")
            return value
        except (TypeError, ValueError, httpx.HTTPError) as error:
            raise ValueError(f"Invalid WebHDFS {op} response.") from error
        finally:
            response.close()

    def get_file_info(self, path: Any) -> Any:
        """Read file status or list one directory for shared glob expansion."""
        from pyarrow.fs import FileType

        def info(base: str, value: dict[str, Any]) -> Any:
            kind = value["type"]
            suffix = value.get("pathSuffix", "")
            if not isinstance(suffix, str) or "/" in suffix or suffix in {".", ".."}:
                raise ValueError("Invalid directory entry.")
            size, modified = value["length"], value["modificationTime"]
            if type(size) is not int or size < 0 or type(modified) is not int:
                raise ValueError("Invalid file status.")
            return SimpleNamespace(
                path=posixpath.join(base, suffix) if suffix else base,
                size=size,
                mtime_ns=modified * 1_000_000,
                type={"FILE": FileType.File, "DIRECTORY": FileType.Directory}.get(
                    kind, FileType.Unknown
                ),
            )

        try:
            if isinstance(path, str):
                return info(path, self._json(path, "GETFILESTATUS")["FileStatus"])
            values = self._json(path.base_dir, "LISTSTATUS")["FileStatuses"][
                "FileStatus"
            ]
            return [info(path.base_dir, value) for value in values]
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ValueError) and str(error).startswith("WebHDFS"):
                raise
            raise ValueError("Invalid WebHDFS file status response.") from error

    def open_input_file(self, path: str) -> "WebHDFSReader":
        """Open a seekable stream; seeks issue a new offset-based OPEN request."""
        return WebHDFSReader(self, path, self.get_file_info(path).size)

    open_input_stream = open_input_file


class WebHDFSReader(io.RawIOBase):
    """Bounded streaming reader compatible with io.BufferedReader."""

    def __init__(self, filesystem: WebHDFSFileSystem, path: str, size: int) -> None:
        super().__init__()
        self.filesystem, self.path, self.size = filesystem, path, size
        self.offset = 0
        self.response: httpx.Response | None = None
        self.chunks = iter(())
        self.pending = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.offset

    def seek(self, offset: int, whence: int = 0) -> int:
        offset += self.offset if whence == 1 else self.size if whence == 2 else 0
        if whence not in {0, 1, 2} or offset < 0:
            raise ValueError("Invalid WebHDFS seek offset.")
        if offset != self.offset:
            if self.response is not None:
                self.response.close()
            self.response = None
            self.pending = b""
            self.offset = offset
        return offset

    def readinto(self, buffer: Any) -> int:
        if self.closed:
            raise ValueError("Read of closed WebHDFS file.")
        if self.offset >= self.size or not len(buffer):
            return 0
        if self.response is None:
            self.response = self.filesystem._request(
                self.path, "OPEN", offset=self.offset
            )
            self.chunks = self.response.iter_bytes(chunk_size=65536)
        try:
            while not self.pending:
                self.pending = next(self.chunks)
            count = min(len(buffer), len(self.pending), self.size - self.offset)
            buffer[:count] = self.pending[:count]
            self.pending = self.pending[count:]
            self.offset += count
            return count
        except StopIteration as error:
            raise ValueError("WebHDFS file ended before its recorded size.") from error
        except httpx.HTTPError as error:
            raise ValueError(
                f"WebHDFS read failed ({type(error).__name__})."
            ) from error

    def close(self) -> None:
        if self.response is not None:
            self.response.close()
        super().close()
