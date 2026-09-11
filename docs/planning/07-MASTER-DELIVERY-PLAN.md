# Master Delivery Plan

Status: frozen candidate v1

| Phase | Outcome | Depends on |
|---|---|---|
| 0 | Grounding, donors, license boundary and clean repository controls | none |
| 1 | Extract Voice Vault runtime skeleton; subtract mandatory cloud bootstrap | 0 |
| 2 | Local users, sessions, workspaces and isolation | 1 |
| 2D | Concurrent users and donor-derived fixed-agent/capability sandbox | 2 |
| 3 | Voice Vault sessions/memory with required R1 v2 memory merge | 2 |
| 4 | Voice Vault Voice Agent/providers/tools plus one R1-derived fixed Background Agent | 3 |
| 4C | Mandatory updated-R1 memory/learning production integration for both fixed agents | corrected 3 and 4 component evidence |
| 5 | R1 Plugins, Skills and MCP under scoped authority | 4C |
| 6 | Exact Browser Voice app and minimal onboarding | 2–5 |
| 7 | Linux desktop/local installer, backup/restore, recovery and release audit | 6 |
| 8 | Windows/macOS desktop/local packaging | accepted Linux evidence |
| 9 | Optional Link/Tailscale and remote management | released core |
| 10 | Agent Plugins 1.0 corrections plus optional Hermes/OpenClaw shared-memory adapters | scoped memory service; exact adapter donors |
| 11 | Optional more users and parental controls | explicit owner activation |
| 12 | Optional edge-device hotspot | selected hardware and device contract |

Each phase begins by rereading `GROUNDING.md`, `INDEX.MD`, `SKILLS.MD`, the
anti-drift protocol, donor map and its build contract. Each exit repeats that
review. Newly discovered scope enters the index and decision gate before work.

Phase 4C is a correction gate discovered after the original Phase 3/4 exits.
It does not add a feature: it makes the already required memory/learning system
real in production. Release readiness is blocked until 4C exits, even though
later component work may already exist in the repository.

Phase 2D is a current correction gate. Logical user/workspace scoping remains
valid evidence, but release readiness now also requires simultaneous four-user
workloads and the Voice donor sandbox adapted without Agent Package identities.

Phases 7 and 8 cover desktop/local packaging only. They must not add device
images, firmware, flashing, fastboot, USB/udev flows, or physical-device gates.
