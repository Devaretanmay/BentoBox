"""CredentialProxy — local HTTP proxy that injects API credentials into upstream requests.

The compartment connects to this proxy via HTTP (not HTTPS), and the proxy
makes a fresh HTTPS connection upstream, injecting the real credential.
This avoids needing MITM certificate generation entirely.
"""

import http.server
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

_logger = logging.getLogger("bentoworks.proxy")

# Hop-by-hop headers that must not be forwarded.
_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})


@dataclass
class RouteConfig:
    """Defines a single credential injection rule.

    The proxy matches ``prefix`` against the incoming request path and,
    on a match, injects ``header`` with ``format`` (where ``{credential}``
    is replaced by the resolved value) before forwarding to ``upstream``.

    Parameters
    ----------
    prefix : str
        Path prefix to match, e.g. ``"/openai"``.
    upstream : str
        Base URL to forward to, e.g. ``"https://api.openai.com"``.
    header : str
        HTTP header name to inject, e.g. ``"Authorization"``.
    format : str
        Header value template with ``{credential}`` placeholder,
        e.g. ``"Bearer {credential}"``.
    credential_source : str
        How to resolve the credential.  Currently supports
        ``"env:VAR_NAME"`` (read from environment variable).
    """
    prefix: str
    upstream: str
    header: str = "Authorization"
    format: str = "Bearer {credential}"
    credential_source: str = ""

    def resolve_credential(self) -> str:
        if self.credential_source.startswith("env:"):
            var_name = self.credential_source[4:]
            val = os.environ.get(var_name, "")
            if not val:
                _logger.warning("Credential source '%s' is empty", self.credential_source)
            return val
        _logger.warning("Unknown credential_source: %s", self.credential_source)
        return ""

    def matches(self, path: str) -> bool:
        return path.startswith(self.prefix)

    def rewrite_path(self, path: str) -> str:
        """Strip the prefix and prepend upstream base."""
        relative = path[len(self.prefix):]
        if not relative.startswith("/"):
            relative = "/" + relative
        return f"{self.upstream.rstrip('/')}{relative}"


class _CredentialProxyHandler(http.server.BaseHTTPRequestHandler):
    """Request handler that proxies HTTP requests and injects credentials."""

    # Set by the factory — avoids passing args through the HTTPServer API.
    routes: list[RouteConfig] = []
    server: "CredentialProxy" = None  # type: ignore

    protocol_version = "HTTP/1.1"

    def do_GET(self):     self._proxy("GET")
    def do_POST(self):    self._proxy("POST")
    def do_PUT(self):     self._proxy("PUT")
    def do_DELETE(self):  self._proxy("DELETE")
    def do_PATCH(self):   self._proxy("PATCH")
    def do_HEAD(self):    self._proxy("HEAD")
    def do_OPTIONS(self): self._proxy("OPTIONS")

    def do_CONNECT(self):
        self.send_error(501, "CONNECT not supported — use HTTP to reach the proxy")

    def _proxy(self, method: str) -> None:
        target_url = self.path
        route = self._match_route(target_url)
        if route is not None:
            target_url = route.rewrite_path(target_url)

        body = self._read_body()
        headers = self._clean_headers(route)

        if route is not None:
            credential = route.resolve_credential()
            if credential:
                value = route.format.replace("{credential}", credential)
                headers[route.header] = value

        req = urllib.request.Request(
            target_url, data=body, headers=headers, method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                self._respond(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as exc:
            self._respond(exc.code, exc.headers, exc.read())
        except urllib.error.URLError as exc:
            self.send_error(502, f"Proxy upstream error: {exc.reason}")
        except Exception as exc:
            _logger.exception("Proxy error for %s", target_url)
            self.send_error(500, f"Proxy internal error: {exc}")

    def _match_route(self, path: str) -> Optional[RouteConfig]:
        for r in self.routes:
            if r.matches(path):
                return r
        return None

    def _read_body(self) -> Optional[bytes]:
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length)
        return None

    def _clean_headers(self, route: Optional[RouteConfig]) -> dict[str, str]:
        headers = {}
        strip_host = route is not None  # let urllib set the correct Host
        for key, val in self.headers.items():
            if key.lower() in _HOP_BY_HOP:
                continue
            if strip_host and key.lower() == "host":
                continue
            headers[key] = val
        return headers

    def _respond(self, status: int, resp_headers: Any, body: bytes) -> None:
        self.send_response(status)
        for key, val in resp_headers.items():
            if key.lower() in _HOP_BY_HOP:
                continue
            self.send_header(key, val)
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        _logger.debug("proxy: %s", fmt % args)


class CredentialProxy:
    """Local HTTP proxy for credential injection.

    Usage::

        proxy = CredentialProxy(routes=[RouteConfig(...)])
        proxy.start()
        # ... run compartment ...
        proxy.stop()
    """

    def __init__(
        self,
        routes: list[RouteConfig],
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        self.routes = list(routes)
        self.host = host
        self.port = port
        self._server: Optional[http.server.HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._saved_env: dict[str, Optional[str]] = {}

    def start(self) -> None:
        if self._server is not None:
            return

        # Create an instance-specific handler class so class-level state
        # is never shared across multiple proxies in the same process.
        handler = type(
            "_CredentialProxyHandler",
            (_CredentialProxyHandler,),
            {"routes": self.routes, "proxy": self},
        )

        self._server = http.server.HTTPServer((self.host, 0), handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()
        _logger.info("CredentialProxy started on http://%s:%d", self.host, self.port)

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        _logger.info("CredentialProxy stopped")

    def set_env(self) -> None:
        """Set ``HTTP_PROXY`` / ``HTTPS_PROXY`` to route through this proxy."""
        proxy_url = f"http://{self.host}:{self.port}"
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            self._saved_env[var] = os.environ.get(var)
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url

    def restore_env(self) -> None:
        """Restore environment variables to pre-proxy state."""
        for var, val in self._saved_env.items():
            if val is not None:
                os.environ[var] = val
            else:
                os.environ.pop(var, None)
        self._saved_env.clear()

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def proxy_url(self) -> str:
        return f"http://{self.host}:{self.port}"
