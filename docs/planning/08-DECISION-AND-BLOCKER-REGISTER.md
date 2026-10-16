# Decision and Blocker Register

| ID | Decision/question | State | Result |
|---|---|---|---|
| D-01 | Local standalone authority | CONTINUE | No required ReSono service |
| D-02 | UI visual authority | SUPERSEDED (D-14) | Exact Browser Voice port; superseded 2026-10-15 for the redesign |
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
| D-14 | UI redesign | CONTINUE | Owner approved 2026-10-15; direction design/mockups (see 2026-10-15-genui-presentation-feedback-plan.md) |
| D-15 | Generative UI cards | CONTINUE | Server-validated catalog, display-only |
| D-16 | Presentation feedback capture | CONTINUE | Thumbs + "How can I do better?" previews |
| D-17 | Explicit layout choice authority | CONTINUE | User's stated preference; also linked feedback for decision review |
| D-18 | Presentation tuner | CONTINUE | Bounded, versioned, shown with Keep/Undo; presentation config only |
| D-19 | Beta feedback sharing | CONTINUE | User-initiated export with preview; text opt-in; no background transmission |

No hardware-device deployment is planned. D-07 blocks public release, not local
development, desktop/local packaging research, or evidence collection.

Current release audit: the Vault target and primary Voice donor contain no
root LICENSE/COPYING/NOTICE file. R1 has a license, but it cannot authorize the
copied Voice Vault/Browser Voice code. D-07 therefore remains a real external
licensor decision and no public artifact may be labeled open source yet.
