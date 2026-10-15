# C04B — retain completed factual analysis across publication retry

Authority: original R31/R32 recovery requirement and owner instruction to finish
without duplication. REUSE existing absolute Vault
`/home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/memory/`
`chat_learning.py`, `contracts.py`, `pipeline.py`, Voice configured review factory,
canonical source guard and existing Chat segment checkpoint. No new table/worker,
model runner, memory store or copied procedural lease implementation.

Internal review CONTINUE bounded correction: the C08B completed-only checkpoint
does not retain successful analysis if canonical publication fails. Extend THAT
row with reviewed/completed state, validated factual review JSON and bound provider.
Capture the actual selected provider/model before analysis; reject changed identity.
Revalidate source/scope and save reviewed output BEFORE publication, under existing
session advisory lock; a retry parses and validates the same stored output, without
calling the model again. Completed writes/dispositions remain atomic with state
transition. Old completed checkpoints migrate as completed, never rerun by default.
Provider failure before output remains retryable by existing end-session boundary;
no autonomous recovery scheduler or full windowing is claimed by this slice.

Failure cases: invalid citation checkpointed; differing source/model/provider reused;
crash after analysis causes repeated model work; partial canonical fact saved before
completed transition; old completed checkpoint reanalyzed. Actual isolated mounted
test induces publication failure then explicit retry and proves model call count
stays one. Existing source revocation/erase and factual/procedural independence hold.
Rollback preserves old completed rows; incomplete reviewed rows must not be treated
as completed by legacy code. No live draft retention or permission changes.
