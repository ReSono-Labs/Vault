# C14E — atomic compiled catalog activation

Bounded contract r1, internal prebuild review 2026-10-07. Reuses C14C generations,
definitions/examples/vectors and C15A capabilities; no second rule store/model.
Source inspected: rules.py, rule_schema.py, repository.py, capabilities.py, existing
actual DB fixtures and decision-learning plan. No activation implementation exists.

Compile a building generation against an explicitly expected scope activation epoch.
Serialize compilation under a scoped transaction advisory lock; copy unchanged prior
definitions/examples with their original review references/vectors; replace revised
definitions only if version advances exactly one. Revalidate every resulting
definition. Example-only revisions must preserve authoritative fields and retain
prior examples/evidence; ordinary behavioral revisions do not imply old examples
remain correct. Existing publisher's version increment is retained, not a second
version authority. Revalidate every resulting
definition, including retained rules. Required bounded transactional qualification
callback checks original source, suppression, quality and current capabilities; no
permissive default. Only literal qualified read-only results can become active;
writes/unknown/unqualified rules remain inactive. All enabled examples of active
rules require current compatible vectors and observed resolved source evidence.
No numeric confidence threshold invented. No tool invocation/provider call in locks.

Pointer and generation states switch atomically; conflict/exception leaves prior
catalog and building generation untouched. Pointer epoch survives invalidation.
Source review deletion invalidates dependent active catalogs and increments epoch
before cascading removal; it must not prevent existing account/conversation erasure.
This deliberately refines the plan's RESTRICT FK: nullable pointer SET NULL plus
before-delete invalidation, membership CASCADE. No silent dangling authority.
Copying examples is derived generation data, not new transcript capture. A catalog
with no eligible read-only rule is not activated. Existing execution grants/final
meaning/slots/confirmation remain separate; pointer is not authorization.

Tests: actual PostgreSQL first activation/additive compilation/CAS/revision,
failure rollback, retained-source/capability denial, write inactivity, exact retry,
owned scope and source deletion. Synthetic gates/vectors only. Production source
qualification, worker mount and runtime active retrieval remain separate contracts;
do not claim full automatic learning delivered by this bounded compiler.


## Completion continuation — retained-review generation rebuild

The existing ChatLearningPublisher now owns rebuild, using the SAME service,
repository publication, additive compiler merge and activation gates. The owned
CSRF-protected POST /conversations/decisions/rebuild requires requestKey and
expectedEpoch. Prepare/reuse compatible vectors before locking; no model, embedding
or tool call occurs in the replacement transaction. Reconstruct only current,
complete, exact completed v3 reviews in original order. Unknown/changed/forgotten
source reviews are reported as unqualified, never converted into eligible evidence.

All derived deletion, publication, predecessor/version checks, merges and final
qualification/pointer activation share ONE transaction and existing scoped activation
lock. Only the final compiled generation becomes active. A failure preserves the
prior catalog and all its artifacts; successful replacement preserves conversations,
reviews, factual memory and suppressions. No qualified read-only replacement leaves
an empty pointer, rather than resurrecting a revoked predecessor. Existing epoch and
policy metadata acknowledge exact retry. Rebuild retains the explicit1024-review
and existing catalog/example budgets; unsupported predecessor history fails safely.

Mounted isolated-DB proof covers two original reviews/create/add-example, a failed
replacement with prior catalog rollback, successful same-ID/version reconstruction,
exact retry, no repeated analysis/reconciliation, and revoked capability handling.
Rebuild is not historical requalification and does not solve changed-identity/new-
source semantic forgetting: those remain distinct original requirements.
