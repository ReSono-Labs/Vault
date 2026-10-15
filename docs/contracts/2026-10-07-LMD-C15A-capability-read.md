# C15A/r1 — current capability read adapter

Existing single ToolCatalog owns definitions/schema/scope/audiences/availability;
existing LocalToolAuthority/catalog authorizer owns grants. DA-R03 and original
stable capability direction require an explicit read-only mapping, never semantic
tool equivalence guessed by models. NEW decision_routing/capabilities.py adapts
catalog.definitions_for and supplied existing authoritative authorizer. No new
registry, grant tables, registration/handlers, inferred provider mapping or tools.

Caller supplies immutable explicit CapabilityBinding(capability_id,tool_id,
provider_key). Multiple current providers for one capability remain ambiguous,
not first-match. Read takes actual ToolInvocationContext for scope/authority
checks; it does not create a tool call or durable invocation. Catalog enumerates
current visible definitions; authorizer checks current grant; unavailable/missing/
denied provider produces no eligible capability. Authorizer errors fail closed.
Resolved records include exact current name/schema/effect/provider, not handlers.
Canonical fingerprint includes scoped local session identity and mappings/resolved
metadata, but no credentials or arguments. Catalog/grants re-read each capture;
no independent mutable cache. read_only requires all requested current effects
read; it does not authorize invocation, activate rule or bypass confirmations.

Exact Vault donor root above tools/catalog.py definitions_for and voice/tools.py
LocalToolAuthority.authorize, tools/strict_json.py canonical JSON. Explicit bindings
remain composition-owned and must be grounded actual aliases, never inferred from
description. No production bindings or optional import into core catalog.
Internal review CONTINUE bounded adapter. Tests actual ToolCatalog dynamic
replace/remove, changed schema/effect/authorization, ambiguous binding, denied/
foreign scope, fingerprint invalidation and zero handler calls. Existing SDK/DB-
free selector import test must preserve core separation with new module optional.
