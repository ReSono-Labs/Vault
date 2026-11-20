from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
from pathlib import Path
import ssl
import threading
from typing import Any
from urllib.parse import unquote, urlsplit

from app.vault_runtime.local_api.app import LocalApiResponse, VaultLocalApiApp
from app.vault_runtime.local_api.config import VaultLocalApiConfig


class VaultLocalHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args: Any, tls_context: ssl.SSLContext | None = None, **kwargs: Any) -> None:
        self.tls_context = tls_context
        super().__init__(*args, **kwargs)

    def get_request(self):
        connection, address = super().get_request()
        if self.tls_context is None:
            return connection, address
        # A TLS handshake on the listening socket blocks the accept loop. Browsers
        # routinely open speculative connections, so defer each handshake to the
        # request thread instead of allowing one idle client to stall the server.
        return (
            self.tls_context.wrap_socket(
                connection, server_side=True, do_handshake_on_connect=False,
            ),
            address,
        )


class VaultLocalServer:
    def __init__(self, *, config: VaultLocalApiConfig, app: VaultLocalApiApp) -> None:
        self._config = config
        self._app = app
        self._server: VaultLocalHttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None:
            raise RuntimeError("Vault local server is not started.")
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> tuple[str, int]:
        if self._server is not None:
            return self.address
        server = VaultLocalHttpServer(
            (self._config.host, self._config.port),
            _handler_for(
                self._app, self._config.max_body_bytes, self._config.web_root,
                _local_ca_path(self._config),
            ),
        )
        self._enable_tls(server)
        thread = threading.Thread(target=server.serve_forever, name="resono-vault-local-api", daemon=True)
        self._server = server
        self._thread = thread
        thread.start()
        logging.getLogger(__name__).info("vault local API listening on %s:%s", *self.address)
        return self.address

    def stop(self) -> None:
        server, thread = self._server, self._thread
        if server is None:
            return
        self._server = None
        self._thread = None
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        self._app.close()

    def serve_forever(self) -> None:
        server = VaultLocalHttpServer(
            (self._config.host, self._config.port),
            _handler_for(
                self._app, self._config.max_body_bytes, self._config.web_root,
                _local_ca_path(self._config),
            ),
        )
        self._enable_tls(server)
        self._server = server
        try:
            logging.getLogger(__name__).info("vault local API listening on %s:%s", *self.address)
            server.serve_forever()
        finally:
            server.server_close()
            self._server = None
            self._app.close()

    def _enable_tls(self, server: VaultLocalHttpServer) -> None:
        certificate = self._config.tls_certificate_file
        private_key = self._config.tls_private_key_file
        if not certificate or not private_key:
            return
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=certificate, keyfile=private_key)
        server.tls_context = context


def serve(config: VaultLocalApiConfig, app: VaultLocalApiApp) -> None:
    VaultLocalServer(config=config, app=app).serve_forever()


def _local_ca_path(config: VaultLocalApiConfig) -> Path | None:
    if not config.tls_certificate_file:
        return None
    candidate = Path(config.tls_certificate_file).parent / "vault-local-ca.crt"
    return candidate if candidate.is_file() else None


def _handler_for(
    app: VaultLocalApiApp, max_body_bytes: int, web_root: str | None = None,
    local_ca_path: Path | None = None,
):
    static_root = Path(web_root).resolve() if web_root else None

    class VaultLocalApiRequestHandler(BaseHTTPRequestHandler):
        server_version = "ReSonoVaultLocalAPI/0.1"

        def do_GET(self) -> None:
            self._handle_request()

        def do_POST(self) -> None:
            self._handle_request()

        def do_DELETE(self) -> None:
            self._handle_request()

        def do_PUT(self) -> None:
            self._handle_request()

        def log_message(self, format: str, *args: Any) -> None:
            logging.getLogger(__name__).info("vault local api: " + format, *args)

        def _handle_request(self) -> None:
            if self.command == "GET" and urlsplit(self.path).path == "/vault-local-ca.crt":
                if local_ca_path is None or not local_ca_path.is_file():
                    self._send(LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}}))
                    return
                payload = local_ca_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-x509-ca-cert")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Disposition", 'attachment; filename="resono-vault-local-ca.crt"')
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.command == "GET" and static_root is not None and self._send_static(static_root):
                return
            body = self._read_body()
            if body is None:
                self._send(LocalApiResponse(413, {"error": {
                    "code": "request_too_large",
                    "message": "Request body exceeds the local API limit.",
                }}))
                return
            request_headers = dict(self.headers.items())
            external_scheme = request_headers.get("X-ReSono-External-Scheme", "").lower()
            request_headers["X-ReSono-Request-Secure"] = (
                "0" if external_scheme == "http" else "1" if self.server.tls_context is not None else "0"
            )
            self._send(app.handle(method=self.command, target=self.path, headers=request_headers, body=body))

        def _send_static(self, root: Path) -> bool:
            request_path = unquote(urlsplit(self.path).path)
            relative = "browser-voice.html" if request_path in {"/", "/browser-voice.html"} else request_path.lstrip("/")
            candidate = (root / relative).resolve()
            if candidate != root and root not in candidate.parents:
                self._send(LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}}))
                return True
            if not candidate.is_file():
                return False
            payload = candidate.read_bytes()
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
            self.send_header("Cache-Control", "no-store" if candidate.suffix == ".html" else "public, max-age=31536000, immutable")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self' https://api.openai.com wss://api.x.ai wss://generativelanguage.googleapis.com; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return True

        def _read_body(self) -> bytes | None:
            try:
                length = int(self.headers.get("content-length") or "0")
            except ValueError:
                return None
            if length < 0 or length > max_body_bytes:
                return None
            return self.rfile.read(length) if length > 0 else b""

        def _send(self, response: LocalApiResponse) -> None:
            if response.stream is not None:
                self.send_response(response.status_code)
                self.send_header("Content-Type",response.content_type or "text/event-stream")
                self.send_header("Cache-Control","no-store")
                self.send_header("X-Accel-Buffering","no")
                self.send_header("Connection","close")
                self.end_headers()
                self.close_connection = True
                try:
                    for chunk in response.stream:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except Exception:
                    # Disconnect/revocation ends viewing only; never replay or
                    # cancel a model/tool run as a side effect of socket loss.
                    pass
                finally:
                    close = getattr(response.stream,"close",None)
                    if close is not None:
                        close()
                return
            if response.body is not None:
                payload = response.body
                content_type = response.content_type or "application/octet-stream"
            else:
                payload = json.dumps(response.payload, separators=(",", ":")).encode("utf-8")
                content_type = response.content_type or "application/json"
            self.send_response(response.status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            for name, value in response.headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return VaultLocalApiRequestHandler
