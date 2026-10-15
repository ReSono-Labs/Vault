from __future__ import annotations

import socket

import pytest

from app.vault_runtime.extensions.runtime_port_forwarder import (
    RuntimePortForwarder,
    runtime_port_publish_enabled,
)


def test_runtime_port_publish_enabled_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "0")
    assert runtime_port_publish_enabled() is False
    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "1")
    assert runtime_port_publish_enabled() is True


def test_runtime_port_forwarder_publishes_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "1")
    forwarder = RuntimePortForwarder(bind_host="127.0.0.1")
    host_port = 18091
    forwarder.publish(host_port=host_port, target_port=18092, identity="demo.plugin")
    try:
        probe = socket.create_connection(("127.0.0.1", host_port), timeout=1.0)
        probe.close()
        assert forwarder.routes()[0].host_port == host_port
    finally:
        forwarder.unpublish(host_port=host_port)


def test_unpublish_during_select_exits_listener_cleanly(monkeypatch):
    from threading import Event
    stopped=Event()
    def close_during_select(*args):
        stopped.set()
        raise OSError(9,"Bad file descriptor")
    monkeypatch.setattr("app.vault_runtime.extensions.runtime_port_forwarder.select.select",close_during_select)
    RuntimePortForwarder._accept_loop(object(),18092,stopped)
