# Planning-to-code validation — feature index

The detailed reports below are frozen prebuild observations, not current build
orders. Later deltas: [C03R repair evidence](2026-10-07-LMD-C03R-build-evidence.md)
and [C02 SQL/index evidence](2026-10-07-LMD-C02-build-evidence.md), plus
[C05A/C06A component evidence](2026-10-07-LMD-C05A-C06A-build-evidence.md). Register owns
status; old absence findings must not trigger rebuilding these implemented subsets.

2026-10-07. This is the current internal feature-by-feature source inventory. It supersedes earlier broad contract-status counts and branch-location holds. Validation used the current working tree, including untracked built components; no owner branch lookup is required. It is not production deployment certification, owner acceptance or a READY build order.

Each linked report names the complete feature plan read, traces actual owners/callers/storage/tests, and separates existing foundations from missing planned behavior. Conditional research/policy/access items are not falsely counted as completed code or unconditional rebuilds.

| Feature / requirement coverage | Code-backed result | Detailed validation |
|---|---|---|
| Indexed hybrid retrieval; R06/07/18/31/33 | Prebuild report found JSON/Python default path. Later C02 adds tested SQL/index adapter; production cutover/maintenance remain C13. Canonical store/C01 retained | [01 prebuild](2026-10-07-feature-01-indexed-retrieval-validation.md), [C02 build](2026-10-07-LMD-C02-build-evidence.md) |
| Live drafts/parallel context/VoiceMem; R02–05/25/27/28 | Prebuild report found no live controller/VoiceMem adapter. C05A/C06A now supplies unmounted extraction/shared preparation; real current/relevance loaders, preference, mounts and comparative quality remain outstanding | [02 prebuild](2026-10-07-feature-02-live-memory-VoiceMem-validation.md), [bounded component](2026-10-07-LMD-C05A-C06A-build-evidence.md) |
| Dedicated transcription; R02/05/30 | Existing conversational Voice/credentials retained; dedicated incremental transcription/controlled response handoff absent; specific entitlement unverified | [03](2026-10-07-feature-03-transcription-validation.md) |
| Separate Chat/text model/history; R19/24/34/35 | Help and unmounted C03A private immutable turns exist. General Chat/model stream/history/continuation absent | [04](2026-10-07-feature-04-Chat-history-validation.md) |
| Attachments/general tool parity; R11/36/37 | Existing workspace files/catalog/grants/invocation recovery retained. Private submitted multimodal Chat path and conversation tool adapter absent | [05](2026-10-07-feature-05-attachments-tool-parity-validation.md) |
| Complete final evidence/reasoning/factual analysis; R12/13/22/23/32; DA-R04–07 | Existing factual pipeline/citations and Voice sources retained. Full-context coordinator, interactive summary/cause/coverage wiring absent | [06](2026-10-07-feature-06-session-evidence-analysis-validation.md) |
| Procedural rules/rebuild/routing/API; R08–18/20; DA-R01–09/11 | C17A offline selector retained. Procedural storage/learning/retrieval/capability mapping and C17B transport absent. Historical data qualification not performed | [07](2026-10-07-feature-07-decision-learning-selector-validation.md) |
| Modular/removal/measured acceptance; R01/21/26/28/29; DA-R10–12 | Isolated foundations have bounded tests; integrated useful-response/quality/removal proof absent. Concern-separated planning documents exist; no runtime implementation is implied by them | [08](2026-10-07-feature-08-evaluation-modularity-validation.md) |

## Reconciliation and duplication disposition

The [reconciled scope](../planning/2026-10-07-live-memory-reconciled-build-scope.md) merges these missing deltas into the existing allocation; [register](../contracts/2026-10-05-live-memory-build-contract-register.md) owns current status. Preserve C01/C03A/C17A. C03B's extra user-final row is withdrawn, not an automatic prerequisite. C03/C17 parents are allocation envelopes, not additional builds. Reuse canonical memory/reviewer/embeddings, C03A identity, existing source and invocation ledgers, credentials, files and grants.

The confirmed code overlap is repeated current-authority SQL in C03A versus Voice; it requires a minimal shared-authority review before mounting, not another copied predicate. The proposed C03B extra event was not built. No second canonical memory store, reviewer or embedding provider was added by the three foundations. This does not excuse the earlier incorrect whole-feature completion/readiness claims.

## Actual test scope and limits

Fresh runs recorded in reports: 38 search/memory units; 11 existing Voice units; 32 conversation/Help/catalog units; 16 reviewer/evidence units; 112 selector/strict-JSON units. These groups overlap; their sum is not a unique-test count. Earlier isolated PostgreSQL C03A evidence is prior evidence, not a fresh DB run. No production DB/source-history read, migration, paid provider call, SDK install, donor edit, deployment or runtime code change occurred in this audit. Runtime names absent were checked alongside positive current call paths; name searches alone were not treated as proof.

Final combined run of those 16 unit files: **197 distinct tests passed** (1.56 seconds). All three existing foundation implementation manifests still verify unchanged. This is focused regression evidence, not a new whole-suite or end-to-end acceptance claim.

Internal source inventory is complete for the listed feature plans. Detailed bounded implementation contracts still need review against this inventory and current hashes; integrated release cannot be claimed. Physical production schema/index/data, provider entitlement, historical coverage, real browser/model/audio behavior and performance remain explicitly unverified.
