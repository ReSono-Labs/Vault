# Vault Developer and Agent Instructions

## Project rule

Vault is a local-first, open-source extraction project. Preserve the existing
Vault + Voice platform; optional Hermes/OpenClaw memory and credential access is
an additional use case, not permission to redefine or reorganize the product.
**Use donor code.** Do
not invent, rewrite, or redesign an existing feature. First define the required
behavior, then locate the proven implementation in another project on this
computer, record the absolute donor path, and copy/extract/port that code with
only the smallest grounded adaptations.

Do not use donor code merely as inspiration for a fresh implementation. Do not
translate working code into a new architecture because it appears cleaner. The
donor implementation is the starting implementation unless evidence proves it
cannot satisfy Vault's security, portability, local-only, or public-release
requirements.

The primary code donors are Voice `app/vault_runtime/` and
`frontend/src/browser-voice/`. Start every feature search there. Remove ReSono
cloud authentication and required cloud control-plane coupling; do not replace
the rest of the Voice feature with R1 or newly written code. R1 is secondary
evidence only for a required local behavior absent from the Voice donors.

“Remove cloud authentication” does not mean remove authentication. Replace it
with local Vault-owned accounts, credential verification, sessions, CSRF/origin
controls, workspace membership and recovery. Never retain a dependency on a
ReSono account, ReSono identity service, hosted token issuer, hosted device
trust service, subscription gate, or ReSono operator approval.

All donor repositories are strictly read-only. Inspection and test execution
must not mutate them. Never run formatting, migrations, dependency upgrades,
code generation, cleanup, or builds that write tracked output in a donor. Copy
only phase-required files into Vault, then modify the Vault copies. Before and
after donor inspection, check donor worktree state when a Git repository is
available and do not alter pre-existing owner changes.

No implementation work is authorized until `GROUNDING.md` is accepted and the
feature has an evidence-backed donor entry in
`docs/planning/FEATURE-DONOR-MAP.md`. New work must be explicitly marked `NEW`.

## Required reading order

Before planning, coding, reviewing, testing, packaging, or deploying:

1. Read `GROUNDING.md`.
2. Read `INDEX.MD`.
3. Read `docs/protocols/ANTI-DRIFT-PROTOCOL.md`.
4. Read `docs/planning/PROJECT-BORROWING-MATRIX.md`.
5. Read `docs/planning/FEATURE-DONOR-MAP.md`.
6. Read the research or plan applicable to the feature.

If these documents disagree, stop. Resolve the grounding conflict in writing
before changing code.

## What `INDEX.MD` does

`INDEX.MD` is the concise map of the repository. It tells a developer what each
top-level path owns without becoming a second architecture specification.

Update it in the same change whenever a top-level directory, deployable,
service boundary, package, or canonical documentation location is added,
removed, renamed, or changes ownership. Do not list every source file.

## Anti-drift procedure

The copied anti-drift protocol is controlling process guidance. Apply it to
every feature and phase:

- state the governing requirement;
- identify the donor and exact absolute source path;
- distinguish observed code from an assumption;
- record dependencies, security boundaries, and counterexamples;
- mark unresolved decisions `OPEN` or `CONDITIONAL`;
- require acceptance evidence before declaring completion; and
- do not let implementation silently change product scope.

When donor behavior conflicts with Vault grounding, grounding wins. Record the
necessary adaptation; do not quietly redesign the feature.

## Architecture and code cleanliness

- Keep modules small, single-purpose, and named for the domain they own.
- Keep business logic independent of the web UI, operating system, and model
  provider.
- Use one canonical implementation for each capability. Adapters may translate;
  they may not fork business rules.
- Put authorization and workspace scoping in repository/service boundaries,
  not only in UI filters.
- Keep secrets out of source, manifests, logs, model context, and memory.
- Default network listeners to loopback. Remote access is an explicit adapter.
- Treat imported Plugins, Skills, MCP servers, and tools as untrusted.
- Preserve provenance, migrations, deterministic recovery, and auditable errors.
- Never add cloud telemetry, ReSono-operated dependencies, or silent outbound
  traffic.
- Avoid OS-specific paths and shell assumptions in product code.

## Front-end visual lock

The public-facing and management web app is Browser Voice visually. Port its
existing presentation exactly. Do not redesign, reinterpret, rebrand, replace,
or introduce a second component/design system. Back-end wiring may change for
local Vault contracts, but visual changes require an explicit owner decision.

When a genuinely new Vault screen is required, build it only from inspected
Browser Voice components, tokens, responsive rules, and interaction patterns.
Record the exact donor files used in the feature donor map.

## Porting workflow

For every feature:

1. Add or update its donor-map row.
2. Inspect and test the donor behavior.
3. Write the Vault contract and note required adaptations.
4. Copy/extract/port only the phase-required donor files into Vault, with
   attribution and license compatibility recorded; leave the donor untouched.
5. Add positive, negative, isolation, and migration tests.
6. Update `INDEX.MD` if structure or ownership changed.
7. Record evidence and remaining limitations.

## Capability exposure and execution proof

Never declare a tool or capability implemented merely because its service,
adapter, schema, or handler exists in the repository. This project previously
allowed Web search logic to exist in a donor without proving that standalone
Vault exposed it to Voice; the resulting feature was invisible and unusable.
That failure must not recur.

For every built-in, Plugin, Skill, MCP tool, or other agent capability, trace
and prove the complete runtime chain before calling it ready:

1. reproduce or identify a successful donor execution and inspect its runtime
   logs when a working donor is available;
2. record the exact tool name, schema, target, handler/adapter, authorization
   path, credential source, prompt guidance, result contract, and failure path;
3. register the capability in Vault's one canonical `ToolCatalog` rather than
   leaving disconnected logic in a service module;
4. verify it is enumerated into every intended fixed system agent's actual
   session or run request—not merely present in Python source;
5. verify the management Library shows the capability in the correct category
   so the owner can confirm that it exists and who may use it;
6. invoke it through the same public runtime boundary the agent uses and test
   positive, denial, malformed-input, credential-scope, and safe-failure cases;
7. for Voice tools, start a new Realtime session during verification because
   its tool supply is fixed when the session is created; and
8. preserve evidence of the full chain in `docs/evidence/`.

A passing adapter unit test alone is insufficient. A visible management row
alone is insufficient. A tool definition included in a provider payload alone
is insufficient. Readiness requires definition, authorization, enumeration,
dispatch, execution, result handling, visibility, and evidence to agree.

When the owner reports that a donor capability just worked, inspect that exact
successful execution and its logs before modifying Vault. Do not guess from a
similarly named module, substitute another provider, or design a parallel tool.
Donor inspection remains read-only.

Copying code is not automatically safe for public release. Verify licenses,
remove ReSono secrets/branding/private endpoints, and preserve required notices.
If rights are unresolved, block public distribution of the affected code; do
not respond by silently reimplementing the feature.

## Multi-user and shared memory

Multi-user identity, workspace authorization, and shared-memory visibility are
new Vault work. They must wrap the proven R1 memory behavior without copying its
single-user `primary` assumption. Every read, write, search, context injection,
vector operation, evidence lookup, correction, deletion, and integration call
must be scoped at the storage/service boundary.

Vault may eventually be the primary memory store for Hermes, OpenClaw, and
other owner-approved agents. Implement that through authenticated, revocable
integration identities and a canonical Vault memory service. MCP or another
adapter may expose the service, but adapters must never query storage directly,
bypass Vault reconciliation, or create a second source of truth. Treat external
writes as attributable proposals and grant read, propose, correct, forget, and
administrative operations independently.

## System agents

The only agent identities allowed in Vault are the fixed Voice Agent and fixed
Background Agent. Treat `system agent` as a required runtime role, not as a
synonym for Voice donor labels such as first-party, built-in, package, template
or coordinator. Do not port Agent Foundry, a Build Agent, Agent Hub, specialist
agents, user/developer agents, graph templates, agent publication or delegation
to installable agent packages.

Skills, Plugins, MCP servers and tools extend the two system agents. They must
not instantiate additional agents. If a copied dependency creates or registers
another agent identity, stop, add it to the donor/index review and remove it
unless the owner explicitly changes grounding.

For every donor module containing `agent`, classify it before copying:

- `VOICE_SYSTEM_AGENT`: fixed Browser Voice/Voice Vault interactive runtime;
- `BACKGROUND_SYSTEM_AGENT`: fixed generic background queue/runtime;
- `CAPABILITY_ONLY`: preserve only the identity-neutral tool/service behavior;
- `REMOVE_AGENT`: package, specialist, coordinator, generated, developer,
  marketplace, Foundry, Hub, delegation target, or Build Agent behavior.

Record the classification and full donor path in the borrowing matrix or phase
evidence. Names such as `system`, `built_in`, `first_party`, and `internal` are
not evidence. New agent-registration, selection, publication, generation, or
delegation surfaces are automatic anti-drift failures.

## Build and desktop/local packaging requirements

### Production package and test-data separation

The installed Vault package is `Dockerfile` + `compose.yml` operated through
`scripts/vault_package.py` or the root `vault-package` wrapper. It owns exactly
these persistent production volumes: `resono-vault-data` and
`resono-vault-postgres-data`. The PostgreSQL service is private to the Compose
network and is never published to the host. `compose.test.yml` and its
`resono-vault-test-postgres-data` volume are test infrastructure only.

Never point pytest, a migration experiment, or an integration fixture at an
installed or manually used Vault database. The test harness allowlists the
database name `resono_vault_test` exactly and must reject every other database
name. A schema-dropping test against any other database is a critical process
failure.

Installing Vault initializes the package database, schema, pgvector, local CA,
TLS identity, runtime secrets and a one-time master onboarding credential.
Onboarding creates the permanent master account and its private workspace. A
secondary account is not complete when a database row exists: its user root,
private workspace root and independent user/workspace key material must also be
provisioned. All users share one versioned application/runtime and schema while
identity, sessions, authorization, data, storage paths, keys, memory and
execution context remain user/workspace scoped. Do not clone an entire server
or database per user; that would fragment migrations, backup, concurrency and
future shared-memory policy.

Memory vector setup is part of the production package, not optional test
infrastructure. The package schema must create the pgvector extension and the
real `vector` storage column. Every accepted memory remains owned by a concrete
user/workspace scope; when that scope has shared or individual provider access,
the R1-derived embedding provider stores a real provider vector in the same
scope. New memories are embedded during ingestion. Missing or legacy vectors
are retried at startup and before semantic lookup. Provider failure may leave a
truthfully unembedded memory for later retry, but code must never substitute a
hash, keyword, random or fabricated vector. Account deletion relies on the
memory foreign-key cascade to remove that user's vectors with their records.

The structured memory reviewer is `CAPABILITY_ONLY`. It is a real model-backed
review execution hosted by the fixed Background runtime, but it must never be
registered or presented as a third system agent. Vault's immutable agent
inventory remains Voice Agent plus Background Agent.

Account removal must revoke sessions, remove memberships and private feature
data, erase that account's storage/key roots, and retain only the minimum
pseudonymous audit tombstone required by referential integrity. Never remove
the permanent master through the secondary-user flow.

Uninstall preserves production data by default. Backup, restore and factory
reset are package operations. Restore and factory reset require their exact
confirmation phrases; do not weaken or bypass those guards.

### Built-in capability boundary

Only Mail, Contacts and Calendar are built-in personal capabilities. Preserve
the Voice Vault multi-account mail client rather than reducing Mail to a tool.
Keep each domain modular. Do not port External AI, social posts, recipes, local
events or any other donor signal/tool family into core. A possible future
Plugin is not authorization to copy or expose that feature now.

Desktop/local installers, OS service packaging, signed artifacts, distribution
bundles, and release instructions remain authorized project work. Deployment
to a hardware device is not authorized or required. Do not flash device images,
target R1/Android firmware, use fastboot, add USB/udev device installation, or
make physical-device proof an acceptance condition.

Initial onboarding asks only for the local user's name and desired interaction
style, such as strict, concise, warm, or funny. Additional configuration stays
optional and belongs in web management.

## Definition of done

A feature is not done until its contract, donor provenance, security boundary,
tests, documentation, migration/recovery behavior, and supported desktop/local
platform status agree. Physical-device deployment is excluded.
