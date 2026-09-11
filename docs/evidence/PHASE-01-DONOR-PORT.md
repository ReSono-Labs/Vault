# Rejected Phase 1 R1-First Scaffold Evidence

Status: rejected after owner grounding correction; files must be removed

Donor (read-only):
`/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/storage/database.py`

Donor SHA-256 before copy:
`4e3f7f8416469f5d093ecf58f2ad1637e97c21d7415aaf83b0017693e982712d`

The code was copied to `src/vault/storage/database.py`. The R1 database connection,
foreign-key, busy-timeout, WAL, ordered migration, idempotency and health
behavior was preserved, but this created an unauthorized alternative to the
existing Voice Vault runtime/datastore architecture. It is not accepted build
evidence and must not be carried forward.

Donor repository changes: must match the captured pre-copy status after tests.

Additional bounded donors:

- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/config.py`
- `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/api/http_server.py`

The attempted scaffold preserved: absolute root, minimum token length,
loopback host, explicit data/workspace/log paths and directory preparation.
Preserved HTTP behavior: loopback-only bind, threaded lifecycle, bearer token
comparison, JSON/no-store response, quiet request logging. Later-phase route
imports were intentionally not copied into Phase 1. These files are superseded
by the required Voice Vault runtime extraction and are scheduled for removal.
