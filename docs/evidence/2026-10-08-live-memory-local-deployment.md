# Local live-memory build deployment — October8

Owner authority: “We need this build done and deployed. Continue.” Branch:
`feature/live-memory-decisions`; owner worktree, including untracked modules,
preserved. Existing package lifecycle/configuration reused. No new agent, model,
scheduler, storage authority, hosted service, hardware deployment or donor edits.
This records deployment of the current bounded build, NOT full-build acceptance.

## Recovery and target

Existing local Vault production package only; unchanged loopback endpoints:
`https://127.0.0.1:8765`, Link compatibility bridge `http://127.0.0.1:8766`.
Existing `.runtime/production-package.env` used directly; no configuration reset.
Both production data volumes preserved; no restore/reset/schema-dropping tests.
Supported backup completed at `.runtime/package-backups/20261008T163053Z`.
Backup directory700/artifacts600. Previous image retained as
`resono-labs-vault:pre-live-memory-20261008` (original SHA256
`3943843df557bc0ac5c4778cc171a2543259dc197f80c0bb8d4f5f6f359ecc8f`).
An image rollback alone does not undo additive schema migration; any data restore
still requires existing explicit confirmation and verified backup workflow.

## Build and deployment proof

- Production frontend TypeScript/Vite build passed.
- Focused Chat/live preparation frontend tests:4 passed,4.22s.
- Active Chat boundaries/procedural retry coordinator checks:9 passed,22.97s.
- Canonical suppression suite including new Chat provenance check:7 passed,15.27s.
- All DB tests used only the allowlisted `resono_vault_test` on port55436.
- Docker multi-stage build passed with frozen Python lock and npm lock.
- Existing production Compose `up -d --wait --wait-timeout120` completed.
- Running image SHA256:
  `592ce5afeff0f4e95b469cb15a8858931f3252a6321bbd88c15145c72d85c47a`.
- Vault, PostgreSQL and Link bridge healthy. Direct verified-CA HTTPS app200;
  Chat asset200; unauthenticated `/conversations`403; bridge health reports
  database/schema ready and pgvector0.8.6.
- System-catalog-only index inspection: factual HNSW1536 valid/ready. Procedural
  example HNSW is created by the existing publisher's `ensure_index` on first
  eligible publication, not fabricated by this smoke check.
- Running-container hashes match working-tree `conversation/runtime.py`,
  `runtime_store.py`, `memory/suppression.py`, `memory/repository.py`, and built
  `ChatPanel-BOHErb2Z.js`. Docs updated after the image snapshot are repository
  status/evidence, not claimed to be baked into that already-built image.
- No private installed sessions read, no tool replay, no browser login or paid
  synthetic-test provider calls. Normal deployed startup/runtime retains its
  existing configured-provider behavior.

## No-drift / remaining boundary

Only additional code in this deployment turn is C13D's already-audited Chat
provenance gap: same canonical suppression guard now consumes source_ref_json,
with non-content namespaced source IDs; no new schema/model/store. Old-source
same-identity paraphrase rejected, new-source different fact allowed, Voice/scope
regressions pass. Full changed-identity semantic suppression is NOT claimed.

Register r46 remains the sole status authority. Original-scope gaps remain:
oversized procedural source windows/reconciliation; qualified Voice procedural
publication/recovery; Chat memory-operation channel/provider parity; attachments;
large display-history pagination; controlled rebuild/full semantic forget
suppression; historical evidence audit and real-provider/quality acceptance.
Continuous accumulation and factual Chat windows are delivered children, not
reasons to rebuild them. Deployed live preview is available for owner testing;
no inference from package health to completed learning or semantic quality.

## Latest completion-pass deployment — October8 local / October9 UTC

Owner authority: “lets get this built and deployed.” Existing production Compose
and `.runtime/production-package.env` reused without resetting configuration.
Current working-tree build, including untracked feature modules, deployed; branch
`feature/live-memory-decisions`. No branch reset, commit, private-history inspection
or tool replay performed.

- Supported backup: `.runtime/package-backups/20261009T023209Z`; directory700,
  artifacts600. Both existing production data volumes preserved.
- Prior running image retained as `resono-labs-vault:pre-completion-20261008`,
  SHA256 `592ce5afeff0f4e95b469cb15a8858931f3252a6321bbd88c15145c72d85c47a`.
- Docker production multi-stage build, frozen Python dependency install and
  TypeScript/Vite frontend build passed.
- New image: `resono-labs-vault:completion-20261008`, also tagged `local`, SHA256
  `dcfd579ee3c3dddf7414baa8b059621ce9d0e6ad22d070016e7a3e3e476e6482`.
- Existing Compose `up -d --no-build --wait --wait-timeout120` passed. Vault,
  PostgreSQL and Link bridge healthy.
- Verified-CA host HTTPS `/`200 and `/health`200; frontend entry assets200;
  unauthenticated `/conversations`403; host Link bridge `/health`200.
- All243 installed application Python source files match the workspace hashes.
- Scoped predeployment verification:725 unit checks and39 distinct focused
  integration checks passed for semantic forgetting and related shared learning;
  prior focused proofs cover input windows, original attachments and generation
  rebuild. No full final-combination regression or real-provider acceptance claimed.

This image contains shared Chat/Voice learning and semantic forgetting. Historical
qualification has a read-only reporting endpoint; submitting historical sessions
through learning still needs implementation. Missing historical tool-use evidence
cannot be reconstructed by deployment. Real-provider/installed-data acceptance
remains to be performed against the new running build. These are explicit limits,
not a declaration that the original whole feature scope is complete.

This appended deployment record and subsequent status-document edits occurred
after the image snapshot; application source matching above covers runtime code.
An image rollback alone does not reverse additive schema changes. Keep both data
volumes and use the established verified backup/restore workflow if restore becomes
necessary; no data restore was performed.

## Chat full-width layout and fullscreen drawer deployment

Owner requested desktop full-width Chat and mobile adaptation, with sessions,
New Chat and Live Memory switch behind a top-right fullscreen drawer sliding
left. Existing Chat owner/state/preference endpoints reused; no backend feature
or schema changed. Native modal dialog supplies keyboard dismissal/focus handling;
reduced-motion and safe-area rules included. Existing mobile viewport/nav sizing
retained.41 frontend checks and Docker TypeScript/Vite build passed.

Deployed image `resono-labs-vault:chat-drawer-20261008` (also `local`), SHA256
`bd7a2fbfdb45e27c9dd34bc46d5f33f7f3c26c7ee4a67ad750abbf3c6991e1a2`.
Prior completion image preserved as `resono-labs-vault:pre-chat-drawer-20261008`;
existing data volumes/configuration preserved; latest supported backup above retained.
Existing Compose deployment healthy. All61 frontend source files in the image
match workspace source. Verified-CA host root/health200, actual new Chat JS/CSS
assets200 with drawer markup/styles, unauthenticated conversations403 and Link
bridge health200. No enabled browser surface was available for visual desktop/
mobile inspection, so actual rendered visual QA is not claimed. No private session
read/replay or provider call was performed for this layout verification.


## 2026-10-09 local EmbeddingGemma deployment

Owner-selected local Google EmbeddingGemma replaces cloud embeddings through the
existing factory, canonical memory table, SQL indexes and procedural publisher.
Image: `b072c5eb94aa6181396de5daa448fb89d8475725cb29a3296a8d8fb3f463d731`,
`resono-labs-vault:embeddinggemma-20261009` and current `local`. Prior image retained
as `pre-embeddinggemma-20261009`. Backup: `.runtime/package-backups/20261009T104657Z`.
Vault/PostgreSQL/bridge healthy, host TLS health reports database/schema ready.

Model/runtime blobs are bundled, manifest SHA256
`85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`,
Ollama 0.32.14 CPU runtime reused from host, EmbeddingGemma 300M BF16/768.
Docker checksum verification passed. With networking disabled and a 1.5 GB memory
limit, real document/query vectors were produced; initial document load+encode
1.956s, warm short query 0.315s. Production canonical memory now has the local
profile vector, and a paraphrased question retrieved it by semantic matching alone
in 0.377s; no conversation history or answering-model call was used.

731 unit checks and 20 relevant PostgreSQL checks passed. Inference runner logs
confirm two threads and batch 32. The shared runtime is serialized, lower priority,
one model loaded, five-minute idle unload; background factual repair batch two.
Three short production embeddings took 0.336/0.284/0.279s. Container-wide 50ms CPU
sampling during these calls peaked at 226.8% (100% is one logical core); this is
whole-container usage including concurrent application activity, not an isolated
embedding-process measurement. Container memory approximately 1 GB. Thread limits
are not a hard whole-container CPU quota. No public model port or runtime downloads.

This verifies local vector generation/indexed recall, not completion of historical
qualification or all earlier remaining feature/provider acceptance work. This
evidence update was written after the image build; runtime source changes are baked.

### 2026-10-09 corrected long-input embedding deployment

Deployed image `d11d69bd953a510bddeae03ab1bc8020f109207b8cfb879ce01532bf0039a489`;
rollback tag `pre-embeddinggemma-fix-20261009`, backup
`.runtime/package-backups/20261009T111334Z`. Compose services and TLS health passed.
This supersedes the initial batch-32 configuration above: physical batch 256,
complete ordered input windows, token-weighted normalized pooling into the existing
single-vector contract, one shared 30-second preparation deadline. No partial
vector is published when a window fails. Two inference threads remain configured.

734 unit checks and 23 relevant PostgreSQL review checks passed. Full submitted
passage inference succeeded offline with networking disabled and a 1.5 GB memory
cap in 14.437 seconds, without OOM events. The deployed adapter processed the same
full passage into 768 dimensions in 14.452 seconds. Six canonical user memories
have local-profile vectors. Pooling retrieval quality for arbitrary long documents
has not been broadly evaluated; this does not add a chunk retrieval store.

The existing procedural review lease renews through its existing fenced stage
operation while model work is pending. This preserves authority/source checks;
it does not speed up provider work or hard-cancel a stalled call. Original passage
segment was retried with the existing scoped queue operation, preserving its
completed factual review. Attempt 4 failed after approximately 19 seconds with
`DecisionReviewError`, without a chained cause; durable state is retryable.
This was before lease expiry. The precise validation failure and real procedural
provider acceptance remain unresolved. No additional fix was made beyond the
owner-approved changes. This evidence update follows the image build.

### 2026-10-09 upcoming-input live recall correction

Owner clarified that live preparation must search the upcoming draft/speech, not
past Chat context. The shared ChatPreparationRuntime now embeds only current
input for factual recall and procedural examples. Previous turn text is no longer
copied into the provisional snapshot/selector. Existing history-version, source,
scope, revision and capability fences remain. Selection sees the current input and
its newly recalled memory. This applies to both Chat and Voice through the same
host; final answering history and completed-session review are unchanged.

The exact screenshot drafts returned only favorite_football_team through the
canonical indexed backend when queried without appended history. 123 focused
unit/mounted PostgreSQL checks passed, including both channels' input queries,
memory-dependent selection, cancellation and final handoff. Voice test fixtures
now use the actual 768-dimensional local profile, correcting their stale fixture.

Default live selection now reuses the configured shared model runner/credential,
not the retained API key required by the optional native Decisions adapter.
Its transport returns the existing selector wire; validation/current-state gates
are preserved. One tool-free model turn is canceled at the remaining deadline,
with a ten-second selection budget. An actual shared OAuth request selected the
synthetic contacts capability in 6.024s using configured gpt-5.6-luna. No tool ran.
Model probability estimates are not calibrated provider probabilities. Native
Decisions endpoint acceptance is not claimed; its optional adapter is retained.

Image: `4a580da56b1cc5c4967fcc540d1cfdbf5147f44135980bf08b530d379b4191e2`.
Backup `.runtime/package-backups/20261009T113240Z`; rollback
`pre-live-draft-fix-20261009`. This record is written after the image build.
The separate completed-session procedural review failure remains unresolved.

Full-catalog follow-up: the verbose selector response exceeded ten seconds with
53 choices (52 capabilities plus fallback). The model now emits probability
numbers in supplied choice order; the transport maps those actual estimates back
to the same existing wire, rejecting a wrong count. No probabilities are invented.
Real shared OAuth selection against all 53 values succeeded in 9.013s, choosing
`builtin.contacts-search.v1`, with the exact complete value set. 113 selector and
transport unit checks passed after this adjustment. Deployed canonical queries
for both screenshot drafts returned only favorite_football_team. Selection remains
provisional and may time out under slower provider responses; private drafts are
not learned and no pre-Send tool executes.

Final compact-response image:
`830e61ba2ff668179ceee62c06f33235802c14c5ba2494652247a025c372e45a`,
superseding the intermediate `4a580da...` image above. Same backup and rollback
tag. Runtime source is baked; these follow-up evidence/grounding updates were
written after the build.

### 2026-10-09 OpenAI OAuth replacement

User authorized replacing the previous ChatGPT device-code login with the documented direct-plan OAuth flow, using the existing shared credential owner. The initial external test URL used a hex host identifier and OpenAI rejected `ext_agent_host_id`; the replacement persists a UUIDv4 URI under the existing Vault config directory. Connections now starts loopback PKCE and polls the existing OAuth service; callbacks validate state, signed identity, nonce, and granted direct-plan permissions before replacing the existing encrypted shared OAuth record. Registration metadata is retained for subsequent sign-in and rotating refresh. Chat, background, memory, and help use the public Responses endpoint for the new token; the existing Voice OAuth path receives the same shared token. Live selection uses the existing native Decisions adapter with the new selected OAuth credential. No alternate token store, review pipeline, or provider acceptance gate was added.

Deployed image `810735b86b904050d3483d7acdb4807cc2e129f40473a29f7a356a7c55d52d8d`; rollback tag `resono-labs-vault:pre-direct-oauth-20261009`. Container healthy and TLS health endpoint reports database/schema/pgvector ready. Frontend build and focused OAuth/provider checks passed. The synthetic callback check could not bind port 1455 while the real browser login was completing. At deployment time the real login and provider acceptance were still pending.

The user subsequently completed the new login in Vault. The existing credential resolver now returns `chatgpt_oauth` with direct-plan metadata and public Responses routing; background model remains `gpt-5.6-luna`. A synthetic call through the existing shared agent runner completed and returned OK in 6.36 seconds. The same newly authorized shared token sent to native `/v1/decisions` received HTTP 401, `rejected_by_access_enforcement`, `Unauthorized`, in 0.946 seconds. Login and shared text inference are verified; native Decisions remains rejected. Voice provider acceptance is not verified by this check.

Further isolation: the new access token has `resource.invoke` and `chatgpt.tokens.use.direct`, is unexpired, and its account-specific model catalog includes both `gpt-6-luna` and configured `gpt-5.6-luna`. The exact billing-routing example from the official Decisions guide still returns 401 with `error.type=rejected_by_access_enforcement` and `error.code=no_matching_rule`; request ID `req_d1e81af34cc94e7fb14343be5177f36c`. The same token and exact `gpt-6-luna` model successfully complete a Responses call via the shared runner in 6.827 seconds. This isolates the rejection to endpoint authorization rather than token expiry, missing granted direct-use scopes, or absence of model access. Official ChatGPT plan usage documentation covers eligible Responses requests and warns that support for one route does not grant another route. It does not publish a Decisions-specific OAuth permission or enrollment step. No provider routing, scopes, or runtime code changed during this investigation.

### 2026-10-09 — Restore previous shared OAuth after Realtime regression

Authorized rollback: user requested the old system and verification of everything except native Decisions. Deployed the exact pre-migration image `sha256:830e61ba2ff668179ceee62c06f33235802c14c5ba2494652247a025c372e45a` and restored its matching Python and Connections/API client sources. Removed direct-OAuth callback port/environment and the migration-only dependency/test. No unrelated feature changes were reverted.

The direct-grant token had failed `/v1/realtime/calls` with HTTP 401, `rejected_by_access_enforcement` / `no_matching_rule` (request `req_fa584f61071348d192d6392e2fb010ef`). This acceptance had not been verified before the migration.

Recovered only the original encrypted OpenAI OAuth credential from the 20261009T113240Z backup through an isolated temporary database. Decrypted privately with the existing master key, confirmed legacy grant and unexpired token, verified the old text route before restoring that single global record. Chats, memories, provider model preferences, and other application records were not restored from backup. The temporary database and dump copy were removed. No alternate credential store was introduced. No user reconnect was necessary.

Deployed checks using the restored shared credential:
- Configured `gpt-5.6-luna` through the existing Codex Responses runner returned the synthetic expected `OK`.
- Existing Realtime provider successfully created a `gpt-realtime-2.1` WebRTC session and returned an SDP answer in 1.26 seconds. Synthetic SDP only: microphone/speaker audio roundtrip remains unverified.
- Existing indexed memory retrieval with local EmbeddingGemma returned one result for a personal preference query in 0.35 seconds; no memory content was printed.
- Existing memory reviewer completed a synthetic greeting review in 5.88 seconds; no test memory was persisted.
- Existing background executor completed a synthetic, tool-free structured task in 3.79 seconds; no background job was created.
- Existing model-based live selector selected `memory_lookup` for a favorite-team query in 5.87 seconds. This used the old shared model route, not the native Decisions endpoint.
- Container healthy; health endpoint confirmed database, schema, and pgvector 0.8.6.
- Frontend production build passed; 68 focused existing provider, selector, background, memory, live-memory, and conversation capture unit checks passed.

Native Decisions remains unresolved and was not included in the rollback acceptance claim. These checks validate the affected credential paths; they do not establish full browser audio or every application workflow acceptance.

### 2026-10-09 — D1 hosted with EmbeddingGemma inside Vault Docker

User authorized moving the existing D1 server into Vault Docker, stopping the host D1 process and host Ollama, and keeping the project's EmbeddingGemma resident. This change hosts the model only; it does not change tool-selection transport or any Chat/Voice/model authority contract.

- Packaged the already-installed CPU llama.cpp b11512 / a11f57ba9 runtime with checksums and its LICENSE; added a staging helper matching the existing embedding-runtime packaging approach.
- D1 runs as an existing package-lifetime child under the Vault user, on private container loopback port 11436. Q8_0 model weights are read-only mounted from `/mnt/delltools/d1-models`; no extra multi-gigabyte copy on the almost-full internal Docker disk. `VAULT_D1_MODEL_DIR` configures the model directory; the release compose default is `./models/d1`.
- Text tool classification only: no multimodal projector loaded. Three CPU threads, 4096 context, one inference slot, zero GPU layers. No new cross-model scheduler; D1 and embedding inference normally occur at different points in the flow.
- Both compose configurations set 3 CPU equivalents, 6 GiB memory maximum, 4 GiB soft reservation, and no additional container swap. EmbeddingGemma retains its two-thread inference setting; changed its existing keep-alive from five minutes to indefinite as explicitly requested.
- Extended the existing package health check with D1 readiness. Both child runtimes are started and cleaned up through the package's existing server lifetime.
- Deployed image `sha256:ce309fdd9b4b002177cff0deabab9dba06c354fce58bc0bc8c0ca190c5d087e9`. Build and both compose configuration checks passed. Rollback image: `resono-labs-vault:pre-d1-container-20261009` (does not include D1 runtime).
- Verified D1 inference through `/v1/systemone` inside the running Vault container, returning expected fallback for a greeting in 2.47 seconds. Verified existing LocalEmbeddings query inference, 768 dimensions, in 0.25 seconds. EmbeddingGemma's resident expiry is effectively indefinite.
- Container healthy, no OOM kill. D1 process RSS approximately 2.84 GiB; embedding runner approximately 670 MiB. Docker reported approximately 1.09 GiB charged memory after inference, which differs from RSS because weights are memory mapped and existing shared file-cache pages are accounted differently. Use the 6 GiB configured maximum rather than treating the observed charged memory as a full cold-start footprint.
- Host D1 process terminated. Host `ollama.service` stopped and disabled; project-internal Ollama remains running because it serves EmbeddingGemma. Confirmed only the two container model runners remain.

Known next integration work remains unchanged: translate D1's native `state/questions/criteria` request and dictionary answer/probability shape into the existing selector contract, switch the existing tool-selection transport, and resolve the earlier memory-tool misclassification probes. This deployment does not claim that D1 is already selecting Chat/Voice tools.

### D1 tool-selector compatibility and latency review — two-second requirement unmet

The user authorized wiring D1 for tool selection only, then required less than two seconds. Reviewed the existing shared Chat/Voice preparation host, native D1 API, and selector validation contract. Added an unactivated provider adapter (`decision_routing/local_transport.py`) that maps existing requests into native state/questions/criteria and normalizes native dictionary answers/probabilities back into the existing selector shape. No execution authority or credential handling is added.

Plain upcoming input resolves the initial small-case memory-selection failures caused by passing a serialized JSON envelope as native state: Q8 selected memory lookup for two explicit memory requests and fallback for a greeting, taking about 4.7–5.0 seconds with three choices. However, the captured full builtin catalog plus fallback (28 choices, 842 input tokens) incorrectly selected fallback and took 28.87 seconds. A temporary Q4_K_M runner on container-private port 11437, with the same CPU limits and an explicit missing-information clarification, took 5.74 seconds for three choices and 22.46 seconds for the full catalog; both memory cases chose fallback. Thus Q4 is not established as an accurate or sub-two-second replacement.

The temporary Q4 runner was stopped after the checks. The deployed Q8 D1 and resident EmbeddingGemma remain unchanged. Restored the source default to the existing SharedModelDecisionTransport: the unvalidated adapter is not selected or deployed, so a later build will not accidentally activate the failed configuration. No claim of D1 integration or two-second acceptance is made. Achieving that latency requires a validated reduction in the supplied authorized candidate descriptions and/or faster inference; simply replacing the transport or using Q4 does not meet it on this CPU.

### 2026-10-09: D1 selector handoff

Replaced only the shared preparation runtime's default decision transport with
LocalD1DecisionTransport. The existing Chat/Voice final handoff, scope validation,
stale-result checks, authorized catalog and tool execution remain in place.
Native D1 receives candidate values with null descriptions. Its `none` option maps
back to the existing `__fallback__` contract, including probability values.
No separate selection pipeline or catalog was introduced.

Image: `resono-labs-vault:d1-selector-20261009`
(`sha256:a508c8671625f2948deb37a8e69b235519e87ef9cda4f7d72b4ff82ac3c68bcd`).
Focused selector/transport/preparation checks: 155 passed. Native model checks
selected fallback for a greeting, web-search for online research, and workspace
search for the Link Markdown request. Package/API health checks passed after
startup. The two-second latency target remains unmet; this deployment does not
claim otherwise. D1 remains CPU-only, with the existing Docker limits and local
EmbeddingGemma service.

Post-deployment native smoke: D1 health OK and embedding service HTTP 200.
The installed runtime default is LocalD1DecisionTransport. Greeting mapped to
`__fallback__` in 8.123 seconds using an extended diagnostic client deadline;
two initial probes exceeded the production ten-second deadline. Concurrent
preparation was observed occupying the D1 slot with a 620-token prompt. The
production deadline was not increased. Selection therefore remains best-effort
under load and can fall back to the existing main-model flow.

### D1 separation correction

Deployed `resono-labs-vault:d1-independent-20261009`
(`sha256:e76938159d4ddad84d697c140603340fadc94fc3724d124323fbbd141e139114`).
D1 receives only current draft/transcript text and candidate values, plus none.
Memory evidence is excluded both at request construction and transport. Catalog
selection performs no learned-candidate embedding lookup. Fresh memory no longer
triggers a second D1 evaluation. Each independently completed branch publishes
through the existing guarded status endpoint, without waiting for its sibling.
157 focused tests passed, including both blocked-sibling publication cases and
an assertion that memory content never enters the D1 HTTP body. Installed source
and Vault/D1/Gemma health verified. CPU/latency acceptance remains for live testing.

### Grouped D1 selection

Deployed `resono-labs-vault:d1-grouped-20261009`
(`sha256:04e80dd4ea216995bff2e23f4df4607abfcecbc5edec695caa533e0000f39d82`).
Existing preparation now offers short canonical tool names mapped to existing
catalog definition IDs, excluding all goal_* tools. D1 first chooses one of the
seven user-specified families (plus none), then only that family's tools (plus
none). Both requests share the existing total ten-second deadline. No memory
context, descriptors, schemas or history enter either request. No execution or
new catalog is introduced. Hierarchical probabilities retain unresolved group
mass as fallback; unevaluated tools receive no invented per-tool likelihoods.
159 focused tests passed. Vault/D1/EmbeddingGemma health verified. Live inference
acceptance is left to the user's requested testing; no extra inference probes run.

### Group-filter repair

Immediate `unavailable` events (67–99 ms) were caused by the additional canonical
`load_agent_skill` tool lacking a group in the user-specified seven-family router.
The earlier catalog list omitted that separately registered tool. `_tools` now
filters candidates with the same adapter's group function before selection, so
out-of-group tools and all goal tools cannot invalidate D1. The main model's
catalog and authority are unchanged. 160 focused tests passed, including the
actual skill/background-goal exclusion regression. Deployed image:
`resono-labs-vault:d1-group-filter-20261009`. Installed filtering and Vault/D1/Gemma
health verified. The unverified OAuth web-search draft is excluded from this build.

### OAuth web-search investigation — not deployed

The existing web_search contract now branches on credential.auth_method in the
working tree. chatgpt_oauth reuses background_agent.sdk_runner.run_agent_turn and
the existing Codex endpoint; API-key requests retain the public Responses route.
No authentication migration, new tool contract, provider fallback, or main-model
configuration change was introduced. A completed response must contain a hosted
search call, answer text, and URL citations before the existing result is returned.

Live synthetic probes using the shared credential established:
- Public /v1/responses: HTTP 401, missing api.responses.write scope.
- Codex /responses: HTTP 200, then streamed server_error after search operations.
- include=web_search_call.action.sources exposed real URLs in failed responses.
- gpt-5.5/low reasoning also failed; the configured model remains gpt-5.6-luna.
- A single-search prompt, plain-text/no-citation prompt, and indexed/text-only
  search still failed after retrieval. Reasoning encrypted-content inclusion did
  not resolve the failure.
- Replaying returned reasoning/search items received HTTP 200 but did not yield
  a completed answer; this is not an accepted recovery path.

Representative provider request IDs (no credentials or private prompts):
0d25c32d-f01a-4d3f-a4ce-7425cce4632d (gpt-5.5);
495b0b60-2d0e-4c23-ac49-31ea4e0a095f (indexed/text-only);
a9fd1d54-d6d4-432f-a42d-b4a4d288b036 (plain-text answer).
The route correction is pending; it is not a verified search fix and is not in
Docker. A cited live provider answer remains required before deployment.

### Voice preparation display and mobile drawer — deployed

Deployed `resono-labs-vault:voice-live-mobile-20261009`, image
`1f5fe78487afeb88bd4b1539376accc4b8b4e593444a78938fb74c44c907eb65`.
Chat and Voice now render the same LivePreparationPanel. Voice reads the existing
shared preparation host through an authenticated, session-scoped GET status
adapter. OAuth uses native connection transcript deltas/completed transcripts;
it does not create a second transcription connection or take over response
creation. API-key managed Voice keeps its existing final handoff. Revision and
utterance checks discard late responses; a new utterance clears the display,
and completed results disappear after four seconds. When only a completed
transcript arrives, preparation starts after that transcript, not before it.

Mobile navigation is a native modal slide-up drawer opened by a compact Menu
button. Selecting a destination closes it. Chat's viewport reserves the actual
button size instead of the previous multi-row navigation height. Desktop
navigation is unchanged.

Validation: TypeScript/Vite build; 16 existing/updated Chat/Voice UI checks;
one drawer open/select/close check; mounted PostgreSQL Voice integration check
including the new status read and existing final capture, preference and scope
checks. Installed frontend contains both drawer and status observer. Vault API,
D1 and Gemma returned HTTP 200; EmbeddingGemma remains resident. The deployed
web_search file SHA matches the prior deployment; pending OAuth search edits
remain only in the working tree. Physical iPhone visual/audio testing was not
performed.

### 2026-10-15 — Voice live memory searches during speech (API-key path)

Deployed `resono-labs-vault:voice-live-search-20261015` (`sha256:743a5bb5fb28…`, also `local`).
Rollback image: `voice-live-mobile-20261009` (`1f5fe78487af`, ~131 MB unique layers). Backup:
`.runtime/package-backups/20261015T104914Z`. Existing compose; both data volumes preserved.

Change: the Voice agent always owns its response (`create_response=true`); the turn-end
`/preparation/final` handoff and `managedResponse` are removed. `liveTranscription` opens the
`gpt-live-transcribe` session (`delay: low`), whose deltas feed the shared preparation host
during speech; memory is applied via `session.update` and kept until the next utterance.
ChatGPT OAuth is unchanged (still turn-end).

Verified: 746 unit, 44 frontend, mounted Voice live integration test; image hashes match
workspace for the changed files; all 237 installed Python files match; Vault/Postgres/bridge
healthy, TLS `/health` 200, unauthenticated voice route 403, D1 health 200, embedding runner up.
Two older integration tests (Voice review recovery, Chat draft memory-in-selector) fail
identically without this change. NOT verified: any real OpenAI session, microphone audio,
`delay`/`session.update` acceptance by the provider, or search latency. Build cache pruned.

### 2026-10-15 — OAuth conversation, API-key transcription and Web search

Deployed `resono-labs-vault:voice-hybrid-keys-20261015` (`sha256:4561cf63aeb6…`, also `local`).
Rollback: `voice-live-search-20261015`. Backup: `.runtime/package-backups/20261015T110302Z`.

OpenAI `live_transcription` and `web_search` resolve the retained API key even while ChatGPT OAuth is
selected (`API_KEY_CAPABILITIES`); all other features follow the selected method. Saving an API key no
longer changes the selected method; Connections gains Use API key / Use OAuth. The unverified OAuth Web
search branch was removed. Install state after deploy: openai selected=chatgpt_oauth, api key retained.

Verified: 745 unit, 46 frontend, credential integration (real DB, hybrid routing) and mounted Voice
integration (OAuth conversation + API-key transcription session) tests; all 237 installed Python files
match; health 200, bridge 200, D1 200. NOT verified: real OpenAI transcription/Web search calls, microphone
audio, or provider acceptance of `delay`/`session.update`. Web search with the API key and `gpt-5.6-luna`
on the public Responses route is untried. Build cache pruned; test database stopped.

### 2026-10-15 — Live search continuity, Decisions API, D1 removed

Deployed `resono-labs-vault:live-decisions-20261015` (`sha256:ced8e99da372…`, also `local`). Rollback:
`voice-hybrid-keys-20261015`. Older images, build cache and all backups except
`.runtime/package-backups/20261015T122421Z` removed at owner request (testing phase).
Verified: 745 unit, 48 frontend, 19 mounted integration tests; all 235 installed Python files match;
health/bridge 200; no D1 process (container ~930 MiB vs ~4 GiB). Deployed Decisions transport via
API-key capability: contacts_search in 1585 ms cold / 667 ms warm; conversation stays chatgpt_oauth.
Four labeled low-confidence `test.live_search.*` memories seeded for live testing (excluded from the
startup preload, reachable by indexed search). Real-session procedural review replays OK 3/3.
NOT verified: real microphone session with live delivery, Decisions accuracy beyond synthetic probes.

### 2026-10-15 — Voice transcript fence removed; memory-lookup guidance

Deployed `resono-labs-vault:live-fence-20261015` (also `local`). Owner's test session showed live memory
delivered before each turn ended (14 deliveries, test memories not preloaded) but every tool selection stale:
the live fence included the Voice transcript count, which changes when the turn is captured. Voice live
preparation now returns a constant history identity (session/memory/preference/grant fences retained). Agent
guidance and the live memory label now say live memory was already searched; memory_lookup only if it does
not cover the request. Host `liquid-d1` user service and `~/llama.cpp` removed (models on /mnt/delltools kept).
Learned copies of the first test memories and the old seeds deleted; four fresh low-confidence test memories
seeded and verified absent from the preload. All backups, older images and build cache removed per owner.
745 unit, 48 frontend, 14 integration tests passed; 0 installed source mismatches; health/bridge 200.

### 2026-10-15 — Live tool route to the agent; session-lock stale fix

Deployed `resono-labs-vault:live-route-20261015` (also `local`). Owner test showed 7/11 selections stale and
no effect of selection on the agent. Causes: locked session read (FOR SHARE) inside the live REPEATABLE READ
check conflicted with every request's `last_seen_at` update (reproduced 200/200); selection only after a pause;
new HTTPS connection per Decisions call; the route was display-only. Now: unlocked provisional session read
(final handoff keeps lock); selection throttled to ≤1/s during speech with sticky last route; pooled client
(deployed calls 1578 ms first, then 270/229/164 ms); selected tool sent to the Voice agent as a provisional hint
(no pre-execution) with count-only delivery logging. 745 unit, 49 frontend, 22 integration tests passed;
0 installed mismatches; health/bridge 200. All backups, older images and build cache removed per owner.

### 2026-10-15 — "Load failed" in Voice; Chat live tool route

Deployed `resono-labs-vault:tool-retry-20261015` (also `local`). Bridge logs showed every Voice `web_search`
tool request from the phone (via Link → bridge) closed by the client ~4 s in (nginx 499 at 12:38:42, 13:18:02,
15:48:37) while Vault finished the search (~11 s) and stored the result; the browser surfaced WebKit's "Load
failed". Not reproducible locally (nginx timeouts 7200 s); the cut appears to be in the Link path, whose logs
need root to read. Fix in Vault: replayed toolCallId returns 202 pending, then the stored result; browser retries
only connection failures (up to 90 s), so results reach the agent. Chat Send now carries the sticky live tool
route to the text model as a named proposal. 745 unit, 51 frontend, 25 integration tests; 0 mismatches.
Backups, previous image and build cache removed.
