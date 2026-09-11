# Phase 2D Voice Sandbox and Concurrent Users Inventory

Date: 2026-08-29  
Status: donor inventory; current correction gate

## Decision

Sandboxing and simultaneous multi-user operation are required now. Voice is the
primary donor. Sandbox primitives may be adapted for the fixed Voice and
Background system agents and imported capabilities, but donor Agent Package,
delegation, Foundry and additional-agent identities remain prohibited.

## Exact donor cut points

Root: `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

| Donor file | SHA-256 | Accepted contribution |
|---|---|---|
| `app/vault_runtime/agent_packages/sandbox_backend.py` | `b8a33aeee9a56a6f378aa7ef9c7e8541d913b876c64ef39900776e65c5f4e121` | Backend errors, handles and fail-closed lifecycle primitives only |
| `app/vault_runtime/agent_packages/sandbox_policy.py` | `abbf97ec4e76fccb07a96eddee223de78b871250cea5a30a8f41c05f6652d0af` | Secret/DB/mount/network/resource policy validation, stripped of package identity |
| `app/vault_runtime/agent_packages/sandbox_backends/bubblewrap.py` | `f96aa94e9ff37f6b232e28856f6caa9de0e53e1abb3b16eafc5504e5fc9e23a0` | Linux namespace, mount, network, environment and rlimit enforcement |
| `app/vault_runtime/agent_packages/sandbox_cgroups.py` | `26a6310dfe32b593c7b878dd371e51aa2a01408bea0a9bf57ec5a53597dc586f` | Optional delegated cgroup v2 PID/memory/IO limits |
| `app/vault_runtime/agent_packages/sandbox_broker_ipc.py` | `7541fb2b8ac71b5857a903e0a442e42be0d15c1b736e8abed202f3b1f01541f5` | Bounded broker IPC concepts after replacing package registry with fixed catalog |
| `app/vault_runtime/agent_packages/sandbox_broker_transport.py` | `46a22d95424546749f05e977ef024788065501968f1cb536bc5c75ec719394bd` | Private socket transport and bounded message handling |
| `app/modules/runtime_tools/skill_executor.py` | `a28caa3381b2e6e14c02f7986f3eb9f70187f79abd667a7af1e6ebfbdb94efe1` | Per-job root, clean environment, resource limits and workspace context materialization |

Donor tests include `test_vault_bubblewrap_sandbox_backend.py`,
`test_vault_sandbox_cgroups.py`, `test_runtime_skill_worker.py` and hardware
negative/profile tests. Bubblewrap `0.8.0` is present on this Linux host.

## Required adaptation

- Rename ownership from Agent Package to fixed-agent/capability execution.
- Never copy package installation, agent registry, delegation or additional
  agent identity code.
- Replace hosted/internal inference routes and excluded signal bundles with
  local owner-configured provider/built-in capability policy.
- Bind every sandbox run to local `user_id`, `workspace_id`, local session and
  fixed agent kind.
- Keep database handles, provider secrets, Vault source, host home, Docker
  socket and local/LAN network outside the sandbox.
- Use brokered canonical tools rather than direct database/secret mounts.

## Current isolation already present

Identity, PostgreSQL rows, memory, Voice, Background runs, Mail, Calendar,
Contacts, credentials, extensions and tools already carry user/workspace scope.
This is necessary but not sufficient evidence of process sandboxing or
simultaneous workload safety.
