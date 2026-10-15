# C14M — immutable existing-rule context for ended Chat reviews

REUSE existing `ReviewInput.existing_decisions`, canonical active definitions,
`source_coverage_json` and compiler add-example/revise semantics. NEW snapshot
joining only in the existing source/review repository, no parallel decision store.

Internal prebuild review CONTINUE: initial ended-segment review receives bounded
active scoped rule IDs/versions plus exact applicability in its existing description
field. Store that small catalog context in the existing claim metadata, not session
history. Subsequent retry/source requalification uses that original bound context,
not whichever catalog has become active later. Revalidate each referenced immutable
scoped definition/version/content. Thus activating a rule never changes its own
source fingerprint. Missing legacy context stays empty, never backfilled. More than
128 rules or 4096-character rule projection requires bounded catalog partitioning,
not silent truncation or a fabricated summary. Existing 100k review limit still wins.

Current compiler remains the CAS/predecessor authority; stale revision proposals
cannot overwrite newer rules. Reviewer sees existing rules and can no_change,
add_example or revise; example-only changes cannot mutate behavior. Test an actual
second Chat segment adding examples to one definition/version+1, with no duplicate
rule, and requalify the first source after pointer changes. This does not claim
cross-window consolidation or semantic dedup quality beyond supplied rule context.
