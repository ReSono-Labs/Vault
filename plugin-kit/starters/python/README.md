# starter.example

This starter combines one Skill, one saved setting and one MCP tool. Replace the
name and description, then put your tool's logic in `server.py`. It is a
runnable stdlib MCP server (protocol 2026-07-28, with 2025-11-25 for older
clients): start it with `python3 server.py` on `127.0.0.1:8788` before enabling
the plugin in Vault. You can swap it for your preferred MCP Python library.

Vault treats the server as a separate service. It does not execute `server.py`
inside Vault.
