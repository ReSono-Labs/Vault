# Vault Progress and Evidence

Current phase: public release preparation  
Overall status: Vault Plugin Kit implementation and deployment complete; production Docker package functioning and owner visual QA accepted.

Plugin Kit completion (2026-09-02): public schemas, offline CLI, TypeScript and
Python helpers, starters, managed embedded-MCP lifecycle, package-rendered
settings, encrypted secret delivery, per-tool Voice/Background grants and
invocation-bound memory/context/activity services are implemented. The complete
guide and downloads are in Documents. Focused unit, PostgreSQL, frontend and
archive checks pass; the rebuilt Docker and Linux packages contain the kit. The
live Docker Vault, PostgreSQL and bridge are healthy. The kit remains ordinary
developer tooling, not an in-product Build Agent.

Owner visual QA (2026-09-02): a deliberate desktop and phone pass over every
public-facing page accepted the UI. Two mobile regressions were found and
corrected: Documents Back/Next now stay compact on one row, and Vault Help
scrolls in a dedicated flexible region so each bubble shows its full text.
Header, suggestions, sources and the composer no longer shrink into that
scroll region. Formal 1440×1000 and 390×844 screenshot files were not captured;
owner live acceptance at desktop and phone sizes closes the visual gate.
Known remaining product gaps stay visible and do not reopen UI work: no
dedicated Background Agent submission page, no standalone Contacts page, and
no Mail-account removal control.

Phase 6 visual acceptance is therefore complete. Public release is no longer
blocked by screenshots.

Voice response display correction (2026-08-29): live Voice and direct web search
were owner-verified as functioning and their runtime/tool logic was left
unchanged. The response presentation had two CSS defects: left alignment inside
the centered mic column and an explicit three-line clamp. Response text now
uses the full centered mic-column width, preserves streaming whitespace, wraps
unbroken content, exposes long replies in a bounded vertical scroll region and
follows the newest streamed text. Frontend regression remains `9 passed`, the
production build passes, and the rebuilt standalone package serves the new
fingerprinted CSS/JS assets while healthy.

Production package correction (2026-08-29): Vault now installs as one coherent
Docker package with a production-only PostgreSQL/pgvector database, persistent
package data, local CA/TLS, non-root runtime and exact Browser Voice build. The
first-run flow creates the permanent master; each account transaction also
creates private user/workspace roots and independent key material. Tests can
target only `resono_vault_test`, so a schema-dropping fixture cannot reach the
installed or manual Vault database. Backup, verified restore, data-preserving
uninstall and exact-confirmation factory reset are implemented. Rebuild/reinstall
preserves database and setup state. Full evidence is in
`docs/evidence/2026-08-29-PRODUCTION-PACKAGE.md`.

The package does not clone a full server or database per account. One versioned
runtime/schema supports concurrent users; identity, sessions, authorization,
data, storage, keys, memory and execution context are separately scoped. This
is the accepted clean package architecture in
`docs/planning/24-PRODUCTION-PACKAGE-AND-USER-PROVISIONING.md`.

Per-user vector completion (2026-08-29): the production schema now uses a real
pgvector column, and the R1 OpenAI embedding provider is composed through each
user/workspace's encrypted shared-or-individual provider policy. Voice learning
embeds accepted records immediately; startup and pre-search repair missing
vectors. The reviewer remains a model-backed Background capability rather than
a third system agent. Isolated verification is `226 passed`, Browser Voice is
`9 passed`, and the production frontend build passes.

Executable imported capabilities remain fail-closed in Docker because the
verified unprivileged container cannot create Bubblewrap's nested namespace.
Privileged mode, Docker socket access and broad `SYS_ADMIN` were rejected. A
narrow donor-derived broker requires a later reviewed package revision; no
unsandboxed fallback is permitted.

Owner-authorized mobile/onboarding/voice correction (2026-08-29): every
management and onboarding surface now has explicit mobile width containment;
the verified 390 px render has a 390 px document/body scroll width and no
element crossing either side. Later onboarding cards now use the same centered
premium primary action, grouped secondary action, message-before-actions order,
spacing and mobile stacking as the approved opening cards. Selecting an active
user expands its management detail and selecting the same user again collapses
it. Mail remains workspace-isolated and supports multiple accounts; stored
account labels are now returned by the backend and shown above each email
address.

R1 Voice startup correction (2026-08-29): Vault already had exact donor
provider settings (`server_vad`, threshold `0.92`, 500 ms prefix padding, 1200
ms silence, create response on, interruption off, near-field noise reduction,
mini-transcribe, 24 kHz PCM and automatic tool choice). The missing R1 connect
greeting is now generated from authenticated display name and local daypart and
sent once after the Realtime data channel opens. Browser capture now requests
the Voice donor's echo cancellation, noise suppression and automatic gain
control constraints.

Test-data isolation incident and correction (2026-08-29): a manual integration
command was incorrectly pointed at `resono_vault_browser_test`; an integration
fixture intentionally drops its schema, removing the current manual onboarding
account. No database snapshot existed. Pytest now refuses to start against the
manual browser database, and the supported test harness targets only
`resono_vault_test`. The refusal is regression-tested. Final verification uses
the supported harness: `149 passed`, frontend `9 passed`, production build
passes, live local/authenticated-ingress/outbound checks pass. Manual Vault
onboarding must be completed again because the lost password hash cannot be
reconstructed.

Latest management-UX correction (2026-08-29, reopened after owner review): Voice Home remains Browser Voice,
while onboarding, login, Library, Connections and Accounts now use the current
R1 management-console geometry and responsive rules. Forms are bounded,
connection setup is organized into sections, account management is a visible
navigation destination, onboarding explicitly offers optional users and shared
provider configuration, and temporary-password first-login replacement remains
enforced. A guarded test-only factory-reset workflow was added but has not been
executed. The first rendered Accounts pass was explicitly rejected: retained
page scroll clipped its heading and its sections were not professionally
composed. Navigation scroll reset and the Accounts section geometry have been
corrected. Owner visual QA on 2026-09-02 accepted desktop and mobile
management surfaces, so this is no longer an open Phase 6 gate.
Verification for the code correction: `8 passed` frontend tests, production
TypeScript/Vite build passed, the reset script compiles, and the restarted
local/LAN/internet test harness passed local health, authenticated ingress and
outbound connectivity checks.

Connections modal correction (2026-08-29): Add Mail and Add Calendar now use
the current R1 management donor's native dialog pattern—centered bounded panel,
dimmed/blurred backdrop, modal heading and close control, two-column desktop
fields, single-column mobile fields, and Cancel/Save actions. Calendar switches
between the admitted ICS-subscription and CalDAV fields without adding the
unsupported donor file-import mode. Successful connections close the dialog;
validation failures stay inside it. Frontend regression remains `8 passed` and
the production build passes.

Accounts correction (2026-08-29): the invalid workspace selector was removed;
private workspaces remain fixed internal account boundaries. The master sees a
compact active-account directory and selects one account before reset/delete or
provider controls appear. Provider access is now a real persisted per-account
policy: shared resolves the encrypted Vault master credential, while individual
resolves a separately encrypted credential in that user's fixed private
workspace. Secrets are never returned. Focused PostgreSQL provider regression,
all `8` frontend tests and the production build pass.

Onboarding experience correction (2026-08-29): the master name is collected
exactly once. First run now advances through one focused question at a time:
name, personalized `Hello, {name}` transition, experience style, master login
credentials, optional secondary users, and optional provider setup. Motion uses the existing
Browser Voice/R1 palette, restrained lateral/scale transitions and a welcome
orbit; `prefers-reduced-motion` disables animation. The four experience styles
are clear choice cards rather than a generic select. Frontend regression remains
`8 passed`, production build and live connectivity checks pass.

Owner walkthrough correction: Continue is now a centered premium action on the
name and experience steps. Experience has no default selection; hover/focus
tracks the pointer and click establishes a distinct persistent choice. The
server-validated setup entry establishes first-run authority in an HttpOnly
cookie, and non-secret step/name/experience progress resumes after navigation or reload.
Master password and provider secrets are never stored as progress. The prior
generated-recovery interruption is bypassed by the existing local owner
registration path, keeping setup authenticated through optional users/provider
and into the first Vault session.

Refresh/resume security correction: browser-held setup credentials were rejected
after a live walkthrough reproduced both lost authority at the password step and
reuse of a credential from a prior factory reset. The installer now opens
`/identity/setup/start?credential=...`; the server validates the current
credential, establishes an HttpOnly, SameSite=Strict first-run cookie, and
redirects to a clean Browser Voice onboarding URL. The fresh-start marker clears
stale non-secret browser progress from any prior reset. Registration accepts the
cookie after reload and clears it when the credential is consumed.
Passwords/API keys remain absent from resume storage. A real HTTP regression
proves setup-session issuance, refresh-style registration without a body token,
cookie clearing, setup-link validation, and redirect behavior. The live harness
was verified at `setupComplete:false`; therefore no additional reset is required.
The master name now has one authoritative collection point.

Stale-fragment correction (2026-08-29): the live server accepted the current
installer credential while the redirected UI still displayed an invalid-token
error. The browser could retain an obsolete `#setup` fragment from a prior reset
and post it after the server had already established the valid HttpOnly setup
cookie. A server-marked `?setup=fresh` load now categorically ignores legacy
fragment authority. Regression is `9 passed`; the production build, live LAN
303 setup redirect, cookie issuance, local health, authenticated ingress and
outbound provider-route checks pass.

Full-chain correction (2026-08-29): cookie issuance alone was not accepted as
proof of a working phone-browser setup journey. After server validation, the
one-time bootstrap proof is now carried in the server-generated onboarding URL
as well as the HttpOnly fallback cookie. It survives refresh, takes precedence
over obsolete fragments, is submitted directly for owner registration, and is
removed from browser history immediately after successful consumption. A new
PostgreSQL HTTP regression follows setup start through the redirect payload and
completes owner registration without a cookie; all `6` focused HTTP identity
tests, `9` frontend tests and the production build pass. The restarted live
server returns the expected bootstrap redirect and remains
`setupComplete:false`.

Provider-sharing correction (2026-08-29): the provider credential is now one
encrypted Vault-wide configuration anchored to the permanent master's private
workspace. Every active local user may use and inspect its configured status
from an isolated workspace, while only the master may replace or remove the
secret. This fixes the prior per-private-workspace behavior without exposing
the API key. Regression: 142 unit tests and the dedicated PostgreSQL provider
sharing test pass.

Latest Voice behavior correction (2026-08-29): the current R1 graph was used
only for navigation and every claim was checked against current source. Vault
now composes scoped startup memory plus the prior completed summary, exposes
progressive Skill loading, restores scoped MCP projections, executes serialized
Realtime function calls through the authenticated local tool runtime, and
returns their results to the live provider session. R1 memory explain/explicit
remember tools and exact PCM/noise/transcription/VAD/tool-choice settings are
ported. Full session transcript close/finalize learning is retained. The fixed
Background Agent goal-intake handoff remains open and is not claimed complete.

Verification: `142 passed` backend unit tests, `13 passed` focused Voice/PostgreSQL integration tests,
`8 passed` Browser Voice tests, production TypeScript
and Vite build passed, and Python compilation passed. The LAN configuration
test enforces the accepted rule: non-loopback binding requires TLS.

Latest owner constraint: the retained identity inventory is exactly Voice Agent
plus Background Agent. All other donor agents are removal candidates; there is
no Build Agent. This is now encoded in Grounding, contributor rules, the index,
and the Phase 4 negative acceptance test. Phase 5 must treat every imported
Plugin, Skill, MCP server and tool as a capability assigned to one or both of
those fixed roles. An import that creates, registers, selects, publishes,
generates or delegates to another agent is prohibited and fails the phase.

Latest built-in capability constraint: Mail (as the donor multi-account mail
client), Contacts and Calendar are the only built-ins. External AI, social
posts, recipes, local events and other donor signal/tool families are excluded;
recipes/local events require a later Plugin decision before any copy.

| Phase | Status | Entry/exit evidence |
|---|---|---|
| 0 Grounding and controls | COMPLETE | Corrected review, borrowing matrix, R1 memory merge, two-agent boundary and AST closure |
| 1 Runtime extraction | COMPLETE | 24 tests plus real PostgreSQL loopback start/health/stop proof; exit review passed |
| 2 Identity/workspaces | COMPLETE | 48 tests with real PostgreSQL/HTTP, four-user concurrency, full pairwise isolation and path guards |
| 2D Concurrent multi-user sandbox | IN PROGRESS | M1 proves four simultaneous sessions/workspaces/private-memory writes. M2 adds a passing Voice-derived Bubblewrap boundary and four concurrent Background workers with one-run failure containment. Broker integration for executable imported capabilities plus concurrent Voice/Mail/Calendar load remain open. |
| 3 Memory components | COMPLETE, LIMITED CLAIM | 70 tests proved scoped R1 v2 schema/lifecycle/retrieval in isolation; not production learning integration |
| 4 Voice/agents/tools components | COMPLETE, LIMITED CLAIM | 102 tests plus production Background correction proved two-agent runtime components; not complete learning integration |
| 4C R1 memory/learning production integration | COMPLETE | M0–M4 plus packaged per-user vectors passed: strict R1 reviewer, Voice capture/close/retry learning, real R1-derived embeddings in scoped pgvector storage, startup/pre-search repair, Background memory references/typed phase evidence, 226-test full PostgreSQL regression and anti-drift exit; auto-writeback correctly excluded |
| 5 Extensions | COMPLETE | 151 tests on real PostgreSQL; local scoped imports, grants, encrypted credentials, rollback/recovery, default-off/safe-mode and anti-drift exit proved |
| 6 Browser Voice | COMPLETE | Exact donor/asset/visual inventory and local-only build proved; owner visual QA on 2026-09-02 accepted every public-facing page at desktop and phone sizes after mobile Documents navigation and Vault Help chat overflow were corrected |
| 6B Mail/Contacts/Calendar | COMPLETE, LIMITED CLAIM | Mail, Contacts and Calendar are locally composed with encrypted/scoped credentials, fixed-Voice-Agent tools, confirmation-protected side effects and PostgreSQL isolation. Visual QA is accepted with the owner. Remaining visible gaps: no standalone Contacts page, no Mail-account removal control, and no dedicated Background Agent submission page. |
| 7 Linux desktop/local release | PRIVATE PACKAGE IMPLEMENTED; PUBLIC RELEASE PREP | Production Docker image, lifecycle wrapper, database, TLS, backup/restore and clean first-run state verified. Phase 6 visual acceptance is closed. Remaining release work is the public bundle, clean-machine install proof, and documentation reconciliation. Imported executable capabilities remain fail-closed pending a narrow sandbox broker. No device deployment. |
| 8 Windows/macOS desktop/local packaging | DEFERRED | Begins only after accepted Linux evidence; no device deployment |
| 9 Optional connectivity/remote management | DEFERRED | Explicit phase activation required |
| 10 Agent Plugins/external memory | IN PROGRESS; M0–M2 COMPLETE, M3 INSTALLED/NOT ACTIVE, M4 PACKAGE BUILT | Agent Plugins 1.0 subset and scoped auto-approved memory service pass 231 backend and 9 frontend tests plus production build. The standalone Hermes provider is installed and discoverable but cannot be selected until a Vault credential is issued through authenticated Connections. OpenClaw `v2026.8.1`/`ea806575` is now frozen and reviewed; its native stateless memory-slot package passes syntax, manifest and package checks but is not installed/live-tested. Native OpenClaw SQLite remains internal and is not used as a Vault bypass. Loopback only; Phase 9 routing is not included. |

Never mark progress from file presence alone. Record commands, test results,
donor hashes, security negatives, review findings and accepted limitations.

Latest Phase 6B verification (2026-08-29) covers multi-account Mail, Contacts,
Calendar account connect/list/sync/remove, encrypted credential storage, event
cache, confirmation-before-create, replay denial, workspace isolation and
fixed-agent tool registration. Current superseding regression evidence is
recorded below.
Phase 6 visual exit is closed by owner live QA on 2026-09-02, recorded in
`docs/evidence/PHASE-06-BROWSER-VOICE.md`. Automated screenshot capture on the
agent host remains unavailable; it is not substituted for owner acceptance.

Current remaining release work: public download bundle, clean-machine
installation proof, and documentation reconciliation. Visual UI is done.

Current production correction status: the fixed Background Agent is composed
with the frozen R1 SDK runner, encrypted local provider access, scoped memory
references, strict typed output, bounded tools and durable phase evidence.
Voice final transcript capture, close-triggered R1 learning and authenticated
retry are composed. Account management supports owner-created users and
password change with other-session revocation. The latest full PostgreSQL suite
passes `194 passed in 97.40s`; frontend tests/build pass (`6 passed`). See the
Phase 4 production correction and Phase 4C exit reviews. Background automatic
canonical-memory writeback remains excluded because R1 does not implement it.

Master-account correction: the first onboarded account is the protected
permanent master account. It can create secondary users, reset/unlock their
passwords with complete session revocation, and remove their local access with
session/membership revocation and private-workspace archival. Secondary users
cannot administer accounts and the master cannot target itself. Full regression
passes `196` backend tests, `6` frontend tests and the production frontend build.
See `docs/planning/21-MASTER-ACCOUNT-CONTROL-CONTRACT.md` and
`docs/evidence/MASTER-ACCOUNT-CONTROLS.md`.

Multi-account identity is NEW Vault behavior; it is not attributed to a donor.
The master now selects setup-link, temporary-password, or master-managed access
for each secondary account. Setup credentials are one-use and temporary
sessions cannot enter Vault until the password changes. MFA is absent and was
not added.
The optional post-recovery onboarding step now lets the master add secondary
accounts immediately. The same canonical API is used later in Account
management, and each secondary requires a future-use `under_18` or `adult`
classification. No parental-control behavior is inferred from that field yet.

Current superseding regression: `203 passed` against the isolated PostgreSQL
database, `6 passed` in Browser Voice, and the production TypeScript/Vite build
passed. This includes all account modes, activation replay denial, forced
password restriction, four-user Background concurrency/failure containment and
the locked-runner Bubblewrap probe.

Latest onboarding/age-classification regression supersedes that count:
`204 passed` backend, `7 passed` Browser Voice tests, production build passed.

AI onboarding now reuses the canonical encrypted OpenAI provider store for the
master workspace and configures Realtime, Background and voice choices. It is
optional and remains editable in Connections. Standalone provider OAuth and
additional MCP/modular model providers are explicitly future adapters; no fake
OAuth UI or ReSono cloud broker was added. The same `204`/`7` full regression
and production build pass after this wiring.

Project test environment: `.venv` is synchronized from `uv.lock`, and the
dedicated `resono-vault-test-postgres` pgvector container is healthy on
loopback with its own named volume. The verified `scripts/test_env.py test-all
-q` workflow passes `194` backend tests, `6` frontend tests, and the production
Browser Voice build. See `docs/development/LOCAL-TEST-ENVIRONMENT.md`.

Internet test infrastructure: `scripts/internet_test_env.py` adds a reversible,
development-only authenticated HTTPS tunnel around the loopback Browser
Voice/Vault origin and checks outbound DNS/TLS/provider reachability. Vault and
PostgreSQL remain loopback-only; this is not product routing, hosting, Link,
Tailscale or device deployment. Verification evidence must come from a live
`start` plus `check`, not file presence.

Live internet harness verification (2026-08-29): the production frontend built,
Vault started against the isolated pgvector database, and all four checks
passed: local health, anonymous public-edge rejection, authenticated public
HTTPS health, and outbound provider DNS/TLS reachability. Socket inspection
confirmed Vault on `127.0.0.1:8765`, PostgreSQL on `127.0.0.1:55436`, and the
ngrok inspection API on `127.0.0.1:4040`. The temporary tunnel remains running
for owner testing; its generated credentials are ignored local runtime state.
