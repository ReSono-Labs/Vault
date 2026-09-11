# UX and Onboarding Contract

## Deferred duplicate-name review

The current first-run flow asks for the master user's name on the initial
“Meet Your Vault” page and again later in onboarding. This duplication should
be reviewed before onboarding is finalized, with a likely preference for one
authoritative name-entry step rather than collecting it on the first landing
page. This note does not authorize a current implementation change.

Status: frozen candidate v1

Browser Voice is the exact visual authority. Copy its required components,
styles, assets and tests only when the UI phase begins. Do not redesign them.

First run: installer starts the loopback service, opens the local web app, and
the owner supplies name plus interaction style. Security bootstrap may generate
or require local authentication, but must not add product-personality questions.
After the master recovery credential is shown, onboarding may optionally create
up to three secondary accounts using the same master-selected access modes as
account management. Each secondary is classified only as `under_18` or
`adult`. Skipping this step enters Vault immediately; accounts remain available
in later management. Models, voice, memory, extensions, backups and
integrations stay outside onboarding.

After optional account creation, onboarding offers optional AI configuration
for the master workspace. The current grounded provider uses the existing
encrypted OpenAI API-key boundary and selects Realtime, Background and voice
settings. Skipping it leaves Vault management available but Voice/Background
model execution unconfigured.

Provider OAuth must use a later inspected standalone donor or a new bounded
provider adapter with local callback, state/PKCE, encrypted token storage,
refresh, revocation and scope tests. The removed ReSono cloud broker is not an
OAuth donor. Do not display an OAuth action until that end-to-end path exists.

Future model providers, including owner-approved MCP-based adapters, register
through the modular connection/provider boundary. They must not create another
onboarding authority, credential store or agent identity.

The age classification is stored for future parental-control work but has no
current authorization, filtering, monitoring or content-policy effect. Do not
collect a birth date or infer an age.

Browser Voice cloud authentication is not ported. Its login/account visuals are
rewired to Vault-owned local authentication and sessions. No ReSono account,
hosted callback, subscription check, device approval or operator action appears
in the local flow.

New account/workspace screens must compose inspected Browser Voice primitives.
Visual regression screenshots at desktop and narrow widths are phase evidence.
Cloud billing, cloud account, ReSono operator, subscription and cloud-only
controls must be removed without changing the remaining visual language.
