# Decision and Blocker Register

| ID | Decision/question | State | Result |
|---|---|---|---|
| D-01 | Local standalone authority | CONTINUE | No required ReSono service |
| D-02 | UI visual authority | CONTINUE | Exact Browser Voice port |
| D-03 | Existing feature implementation | CONTINUE | Copy bounded donor code; donors read-only |
| D-04 | Runtime authority | CONTINUE | Voice Vault runtime + Browser Voice are primary; R1 secondary only |
| D-10 | Cloud authentication | CONTINUE | Remove ReSono cloud auth; preserve local authentication |
| D-11 | System-agent count | CONTINUE | Exactly Voice Agent and Background Agent |
| D-12 | Non-system/build agents | CONTINUE | Remove all; no Build Agent or Agent Foundry |
| D-13 | Extension identity boundary | CONTINUE | Plugins, Skills, MCP servers and tools are capabilities only; they cannot create a third agent identity |
| D-05 | Multi-user scope | CONTINUE | New wrapper at repository/service boundary |
| D-06 | First desktop/local packaging target | CONTINUE | Linux first; no hardware-device deployment |
| D-07 | Public license | CONDITIONAL | Owner/licensor confirmation required before public release |
| D-08 | Remote connectivity/management | DEFERRED | Not core release |
| D-09 | External shared-memory agents | CONTINUE | Loopback-only scoped service complete; Hermes package installed but credential activation remains; OpenClaw v2026.8.1 donor frozen and native adapter package built, with live installation proof still open |

No hardware-device deployment is planned. D-07 blocks public release, not local
development, desktop/local packaging research, or evidence collection.

Current release audit: the Vault target and primary Voice donor contain no
root LICENSE/COPYING/NOTICE file. R1 has a license, but it cannot authorize the
copied Voice Vault/Browser Voice code. D-07 therefore remains a real external
licensor decision and no public artifact may be labeled open source yet.
