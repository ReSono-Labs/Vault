# Architecture and Data Boundaries

Status: frozen candidate v1

```text
existing Browser Voice -> locally authoritative authenticated API -> existing Voice Vault runtime
  -> existing scoped datastore and workspace boundaries
  -> provider adapters / extension adapters / optional Link adapters
```

Hermes, OpenClaw and MCP may later consume explicitly granted memory or
credentials through adapters. That is an additional use case at the existing
service boundary, not a replacement architecture or reason to reorganize the
Vault + Voice platform.

Preserve the Voice Vault runtime's Python structure, datastore contracts and
Browser Voice React/Vite structure. Do not prescribe SQLite, a new service
layout, or renamed domain architecture. Replace only hosted authentication and
control-plane edges. R1 may fill a demonstrated missing local behavior.

Every request carries a principal (`user`, `integration`, or `system`) and an
active workspace. Repositories require that scope as input. UI filtering is not
authorization. Memory, transcripts, summaries, evidence, embeddings, files,
extensions, credentials and audit events carry explicit ownership/scope.

Vault services own rules. HTTP and MCP translate contracts. External agents
never access the canonical datastore or workspace paths. Provider failure cannot prevent local
management, canonical writes, lexical memory lookup, export, or deletion.

Canonical top-level code ownership is defined by `INDEX.MD`; implementation
must update it in the same change as structural movement.
