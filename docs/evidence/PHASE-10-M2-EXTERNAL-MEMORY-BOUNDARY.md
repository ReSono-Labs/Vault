# Phase 10 M2 External Memory Boundary Evidence

Date: 2026-08-31  
Status: complete

## Delivered

- additive external-integration identity and replay-ledger schema;
- one-time opaque enrollment credential, stored only as a SHA-256 hash;
- identity bound by the server to one user and one workspace;
- exact `search` and `propose` grants;
- loopback API contract v1 with health, search, get and proposal operations;
- bounded request IDs, queries, result limits, memory IDs, proposal content and
  evidence;
- proposal and granted-mutation attribution in the canonical transcript/evidence path;
- proposals reviewed by Vault's existing classifier and reconciler rather than
  classified or written by the adapter;
- immediate integration revocation; and
- no database credential or client-selected user/workspace field.

The implementation is a narrow service boundary, not a new agent framework.
Hermes and OpenClaw remain outside Vault and will consume this boundary through
their own native Plugin/provider contracts.

## Verification

Focused PostgreSQL API/runtime chain:

```text
2 passed in 2.92s
```

Composition plus expanded scope-isolation chain:

```text
3 passed in 8.12s
```

Full backend regression after the initial M2 chain:

```text
231 passed in 142.67s
```

Browser Connections and production build:

```text
9 passed
TypeScript/Vite production build passed
```

Python compilation passed. The repository does not install Ruff, so a Ruff
invocation was unavailable and is not claimed.

## Proved negatives

- forged `userId` and `workspaceId` request fields do not affect scope;
- a credential cannot read a private memory in another user's workspace;
- a proposal-only credential cannot search;
- duplicate request IDs are rejected;
- oversized proposals are rejected before consuming a request ID;
- revoked credentials cannot search or propose; and
- enrollment credentials are returned once and never listed again.

## Integration approval rule

Creating the external integration is the user's approval. Incoming proposals
are automatically classified and reconciled by Vault. Correction and forget
apply immediately only when their exact operation grants are present. Tests
prove granted correction and forgetting, wrong-operation denial, attribution,
scope isolation, replay denial and immediate revocation. There is no separate
approve/deny queue or confirmation UI.
