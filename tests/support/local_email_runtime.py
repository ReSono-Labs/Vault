"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations


def _credentials(address: str, suffix: str) -> dict[str, object]:
    return {
        "emailAddress": address,
        "imap": {"host": "imap.example.com", "port": 993, "username": address, "password": f"imap-{suffix}", "useTls": True},
        "smtp": {"host": "smtp.example.com", "port": 465, "username": address, "password": f"smtp-{suffix}", "useTls": True},
    }
