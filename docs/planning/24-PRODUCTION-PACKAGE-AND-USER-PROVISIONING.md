# Production Package and User Provisioning

Status: accepted implementation contract, 2026-08-29.

## Decision

Vault installs as one local package with one versioned application runtime and
one private PostgreSQL/pgvector database. The first-run flow creates the
permanent master account and its private workspace. Each later account receives
an isolated identity, sessions, workspace, data scope, storage roots and key
material inside that package.

Vault does not start a duplicate API server, frontend or PostgreSQL database for
every user. Per-user server/database cloning would create divergent migrations,
multiply resource consumption, complicate backup and prevent a controlled
future shared-memory policy. Simultaneous users are separated by authenticated
user/workspace scope at every repository, capability and execution boundary.

## Package composition

- `initialize` creates package directories, secrets, local CA/TLS identity and
  database configuration idempotently.
- `postgres` is a package-private pgvector PostgreSQL 16 service. It is not
  published to the host.
- `vault` serves the local API and exact Browser Voice frontend over TLS as a
  non-root user.
- `resono-vault-data` holds install configuration, package keys, extensions and
  private user/workspace roots.
- `resono-vault-postgres-data` holds the production database.

The production schema creates pgvector and stores embeddings in an actual
`vector` column. It retains the earlier JSON representation only for
donor-compatible readback by the R1 Python cosine-ranking path; JSON is not the
package's vector setup.

Production resources are distinct from `compose.test.yml` and
`resono-vault-test-postgres-data`. Tests may use only the exact database name
`resono_vault_test`.

## Account provisioning transaction

For every account, Vault:

1. validates master authority, username, age classification and password mode;
2. creates the identity and its fixed private workspace in the database;
3. stages private user and workspace roots under the package volume;
4. creates independent 256-bit user and workspace keys with private modes;
5. atomically publishes the staged roots; and
6. rolls the database identity back if storage provisioning fails.

Startup reconciliation completes an interrupted committed identity without
replacing existing keys. It rejects mismatched or symlinked storage ownership.

The user root is `private/users/<user-id>/`; the workspace root is
`private/workspaces/<workspace-id>/`. A user cannot select another private
workspace. More than one authenticated user can use the shared runtime at the
same time, while repositories, sessions, Mail, Contacts, Calendar, Voice,
Background, transcripts and memory remain scoped.

## Per-user memory vectors

Vector provisioning follows account and memory authority; it does not create a
separate vector database per user. Every embedding belongs to its memory
record's enforced user/workspace scope in the shared versioned database. The
fixed Voice and Background agents retrieve only through that scoped service.

The exact embedding provider is adapted from:

- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/providers/openai/embeddings.py`; and
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/embedding_access.py`.

Vault resolves the encrypted shared or individual provider access selected for
the specific user/workspace. Accepted memories are embedded during Voice
learning. A package-start backfill and a pre-search backfill repair legacy or
temporarily failed vectors. No configured provider means the memory remains
available to truthful lexical retrieval until real embeddings can be created;
Vault never fabricates semantic vectors.

The memory review itself is a real structured model execution, but it remains
a capability hosted by the fixed Background Agent. It does not add another
system-agent identity to the package.

## Account deletion

The permanent master cannot be deleted by the secondary-account operation.
Deleting a secondary account revokes sessions, removes workspace membership
and owned private workspaces, deletes private feature data and removes private
user/workspace roots and their keys. A pseudonymous identity tombstone remains
only where audit foreign keys require it.

## Package lifecycle

The supported operator surface is `vault-package`:

- `install` or `install --lan`
- `start`, `status`, `logs`, `stop`
- `setup`
- `backup`
- `restore <backup> --confirm "RESTORE VAULT BACKUP"`
- `uninstall` (data preserved)
- `factory-reset --confirm "DELETE ALL VAULT DATA"`

Backup contains a PostgreSQL custom dump and encrypted/private package roots,
with SHA-256 verification. Restore verifies the manifest before replacing
package data and then requires a passing package health check. Reinstall and
image rebuild preserve the production volumes and onboarding state.

## Executable capability sandbox boundary

The image retains the donor-derived Bubblewrap runner and the production
container is non-root, drops all capabilities and uses `no-new-privileges`.
Docker's default unprivileged container boundary does not permit Bubblewrap to
create a second nested user namespace on the verified host. Therefore imported
capabilities that require OS process execution fail closed in this package;
they are never run unsandboxed. Built-in Voice and Background capability calls
remain scoped application operations.

Do not solve the nested-namespace restriction with a privileged container,
Docker socket mount or broad `SYS_ADMIN`. A later package revision may add a
narrow donor-derived host capability broker, with its own anti-drift review and
negative isolation tests. Until then, executable imported capabilities are
unavailable rather than unsafe.


### Local embedding package — 2026-10-09

The current Docker package includes Google EmbeddingGemma 300M (Ollama BF16
artifact, 768 dimensions) and the CPU-only Ollama runtime, isolated on container
loopback port 11435. It requires no OpenAI embedding credits or Hugging Face token
at runtime. Reuse the installed Ollama runtime/cache when building:

```sh
ollama pull embeddinggemma:300m
python3 scripts/stage_local_embeddings.py --models /path/to/ollama-models
docker build -t resono-labs-vault:local .
```

`packaging/local-embeddings/` is generated build input, excluded from Git. Its
SHA256SUMS are checked during Docker build; the staging script rejects a changed
model manifest. This deployment reused Ollama 0.32.14 and the external drive cache.
The image carries the original model license layer. Original records and source
evidence remain in PostgreSQL; maintenance regenerates only vector representations.
Inference has two threads, one concurrent request and lower scheduling priority.
No model API port is published to the host.


### Embedding context/batch correction — 2026-10-09

Ollama embeddings require physical batch size at least the input token count.
The initial batch-32 setting was incorrect; the current batch is 2048 for the
2048-token context. This does not increase the two inference threads. Inputs
up to 32768 characters are tokenized by Ollama with `truncate=false`; only its
explicit token-context overflow triggers recursive source-preserving windows.
All windows must succeed within a shared deadline and 31-request ceiling. Their
token-weighted normalized mean occupies the existing one-vector record; no new
store or learning job is introduced. Input contents never enter error logs.
The lock wait and inference share one deadline, rather than doubling the budget.
Local live preparation may use the existing adapter's 30-second bound for long
inputs; the stream's finalization deadline still prevents delaying Chat for it.

The shared procedural reviewer now renews its existing owner/attempt-fenced lease
while model work is pending, rechecking canonical source and local authority on
each renewal and before completion. Renewal is bounded to ten minutes and writes
no analysis output. Revocation, changed source, reclaimed ownership or budget
exhaustion prevent publication. No new reviewer, scheduler or capture path.


The memory-limited verification refined the physical batch to **256**. A 2048
batch exhausted a 1.5 GB container's memory on long windows; smaller windows now
respond to explicit physical-batch/token-context overflow using the same complete
source-preserving split. Each accepted window is verified at no more than 256
model-tokenized tokens, including the prompt prefix. This supersedes the initial
2048-batch correction above, while retaining the 2048 model context, two threads,
shared request deadline and no truncation.
