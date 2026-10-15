# C15A/r1 — current capability eligibility read

Explicit immutable capability/tool/provider bindings adapt actual ToolCatalog
definitions_for and the supplied existing grant authorizer. No independent registry,
grant engine, handler, tool call, active-rule compiler or inferred provider alias.
Multiple available providers for one semantic capability fail as ambiguous.
Unavailable/foreign/denied providers disappear. Exact current schema/effect/name/
provider and scope/mappings determine fingerprint, re-read on every capture.
read_only reports current effect eligibility only, not permission to execute.

**110 targeted units passed in 0.75 seconds**: three new actual-catalog adapter
tests plus existing selector boundary tests. Dynamic replacement/removal, schema
and effect changes, authorization revocation/error, foreign scoped provider,
ambiguity, duplicate mapping and fingerprint invalidation covered. Every handler
would fail the test if called. SDK/DB-free selector core import remains tested with
optional packages blocked and credential reads forbidden. Package-file inventory
adds only known optional adapter; core import allowlist not broadened for SQL/grants.
`git diff --check` passed. No database/provider/tool execution or donor changes.

Production bindings, qualified source gate, active generation compilation/pointer,
required-slot/condition validation and final runtime revalidation remain. Current
authorizer must be the actual composition authority, not a permissive replacement.
Imported providers may impose additional checks at handler time; existing runtime
must still enforce these and confirmations. Adapter is unmounted; full C15 not done.
