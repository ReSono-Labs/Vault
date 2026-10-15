"""Publish supervised plugin ports from inside the Vault container to the host boundary."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import select
import socket
import threading


class RuntimePortForwarderError(OSError):
    pass


@dataclass(frozen=True, slots=True)
class PublishedRoute:
    host_port: int
    target_port: int
    identity: str


@dataclass(slots=True)
class _ForwardListener:
    listener: socket.socket
    thread: threading.Thread
    stop_event: threading.Event


class RuntimePortForwarder:
    def __init__(self, *, bind_host: str = "0.0.0.0") -> None:
        self._bind_host = bind_host
        self._lock = threading.RLock()
        self._routes: dict[int, PublishedRoute] = {}
        self._servers: dict[int, _ForwardListener] = {}

    def publish(self, *, host_port: int, target_port: int, identity: str) -> None:
        if host_port <= 0 or target_port <= 0:
            raise RuntimePortForwarderError("Published ports must be positive")
        if not runtime_port_publish_enabled():
            return
        with self._lock:
            existing = self._routes.get(host_port)
            if existing is not None and existing.target_port == target_port and existing.identity == identity:
                return
            self.unpublish(host_port=host_port)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind((self._bind_host, host_port))
            except OSError as exc:
                listener.close()
                raise RuntimePortForwarderError(
                    f"Could not publish supervised port {host_port} for {identity}"
                ) from exc
            listener.listen(32)
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._accept_loop,
                args=(listener, target_port, stop_event),
                name=f"runtime-port-{host_port}",
                daemon=True,
            )
            thread.start()
            self._routes[host_port] = PublishedRoute(host_port, target_port, identity)
            self._servers[host_port] = _ForwardListener(listener, thread, stop_event)

    def unpublish(self, *, host_port: int) -> None:
        with self._lock:
            server = self._servers.pop(host_port, None)
            self._routes.pop(host_port, None)
            if server is None:
                return
            server.stop_event.set()
            try:
                probe = socket.create_connection((self._bind_host, host_port), timeout=0.2)
                probe.close()
            except OSError:
                pass
            server.listener.close()

    def routes(self) -> tuple[PublishedRoute, ...]:
        with self._lock:
            return tuple(self._routes[port] for port in sorted(self._routes))

    @staticmethod
    def _accept_loop(
        listener: socket.socket, target_port: int, stop_event: threading.Event,
    ) -> None:
        while not stop_event.is_set():
            try:
                readable, _, _ = select.select([listener], [], [], 0.5)
            except (OSError,ValueError):
                if stop_event.is_set():
                    break  # Unpublish may close the descriptor during select.
                raise
            if not readable:
                continue
            try:
                client, _address = listener.accept()
            except OSError:
                break
            threading.Thread(
                target=_relay,
                args=(client, target_port),
                name="runtime-port-relay",
                daemon=True,
            ).start()


def _relay(client: socket.socket, target_port: int) -> None:
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        upstream.connect(("127.0.0.1", target_port))
    except OSError:
        client.close()
        upstream.close()
        return
    sockets = [client, upstream]
    try:
        while True:
            readable, _, errored = select.select(sockets, [], sockets, 60.0)
            if errored or not readable:
                break
            for source in readable:
                chunk = source.recv(65536)
                if not chunk:
                    return
                destination = upstream if source is client else client
                destination.sendall(chunk)
    finally:
        client.close()
        upstream.close()


def runtime_port_publish_enabled() -> bool:
    value = os.environ.get("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return Path("/.dockerenv").is_file()
