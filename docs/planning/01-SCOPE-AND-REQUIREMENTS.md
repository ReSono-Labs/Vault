# Scope and Requirements

Status: frozen candidate v1

## Release-one outcome

One person can install Vault on a Linux desktop/server environment, open the
exact Browser Voice web app, create up to four local accounts, use the fixed
Voice and Background Agents, retain complete updated R1 memory/learning, and
manage extensions without a ReSono account or required ReSono service. Optional
Hermes/OpenClaw memory or credential access is an additional use case and does
not redefine this platform. No hardware-device image, flashing, or
physical-device deployment is required.

## Requirements

| ID | Requirement | Authority |
|---|---|---|
| V-001 | Operate locally without required ReSono infrastructure | Owner grounding |
| V-002 | Exact Browser Voice visual system | Owner grounding |
| V-003 | One easy desktop/local installer; Linux first | Owner grounding |
| V-004 | Web onboarding asks only name and interaction style | Owner grounding |
| V-005 | Support up to four local accounts and private workspaces | Owner grounding |
| V-006 | Enforce user/workspace scope below the UI | Security grounding |
| V-007 | Port R1 memory taxonomy, evidence, versions and retrieval | Owner + donor evidence |
| V-008 | Port R1 Plugin, Skill, MCP and tool lifecycles | Owner + donor evidence |
| V-009 | Use donor code and never modify donor repositories | Owner decision |
| V-010 | Keep secrets out of manifests, logs and model context | Security grounding |
| V-011 | Bind management to loopback by default | Security grounding |
| V-012 | Preserve backup, restore, migration and clean removal paths | Owner grounding |
| V-013 | Use Voice Vault runtime and Browser Voice as primary code donors | Owner correction |
| V-014 | Remove all ReSono cloud authentication/control-plane requirements | Owner correction |
| V-015 | Merge the complete updated R1 domain-memory system and all labels into existing Voice Vault memory | Owner decision |
| V-016 | Retain exactly one Voice Agent and one Background Agent | Owner decision |
| V-017 | Remove all non-system agents; no Build Agent or Agent Foundry | Owner decision |
| V-018 | Built-in personal capabilities are Mail, Contacts and Calendar only; Mail is a multi-account client | Owner decision |
| V-019 | Exclude External AI, social posts, recipes, local events and other donor signal/tool families from core | Owner decision |
| V-020 | Optional Hermes/OpenClaw use may consume explicitly granted Vault memory and credentials without changing the existing Vault + Voice platform | Owner correction |

## Deferred, not release-one scope

Hardware-device deployment, Windows/macOS installers, Link/Tailscale routing,
remote management, and Hermes/OpenClaw memory adapters. Existing Voice Vault features must be preserved or
explicitly classified rather than treated as unenumerated new scope.

Explicitly removed: Agent Foundry, Build Agent, Agent Hub coordinator,
specialist/package agents, public/private developer agents, agent templates,
agent creation/publication and package-agent delegation.

## Failure criteria

Any cloud dependency for basic use, cross-user data access, visual drift,
direct external writes to canonical memory, donor mutation, untraceable copied
code, or installer behavior requiring manual developer setup fails the release.
Any ReSono-issued login/session/device credential or hosted approval required
for basic operation also fails the release.

## Missing-feature rule

A discovered feature does not enter implementation automatically. Classify it
against grounding, inspect its donor, add it to `INDEX.MD` and the donor map,
run the material-decision gate, then place it in a phase or explicitly defer it.
Features may not be invented merely because they are common or useful.
