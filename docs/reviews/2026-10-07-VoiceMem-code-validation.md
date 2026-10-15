# VoiceMem plan-to-code validation

Owner explicitly identifies VoiceMem as part of the prior implementation. Audit
that scope directly, without requiring a branch name or inferring completion from
new contract statuses. Read-only checks, 2026-10-07.

Documented identity: xzf-thu/VoiceMem, upstream commit
6cacb3c1e7fca2679f3bf95451f6b480efd9a783. Runtime plan section
"VoiceMem adoption plan and specific cut points" names stream.py feed_partial/
speculative retrieval, cognitive_graph/local_query_classifier.py and leftbrain/
brain.py. Modular plan names live_memory/voicemem_adapter.py. Research names
feed_partial, _kick, _speculate, _confirm and _ready_memory. These are exact
integration targets, not merely a generic phrase "voice memory".

Current code validation:
- Searches in app, frontend/src, tests, pyproject.toml and uv.lock return only
  existing VoiceMemoryLearning/BrowserVoiceMemoryIcon for the broad VoiceMem
  substring, not upstream integration. No matches for voicemem_adapter,
  feed_partial, _ready_memory, _speculate, local_query_classifier or
  memory_repository_v2.
- Main tracked-file inventory has no VoiceMem/live_memory/cognitive_graph/
  leftbrain paths. Current new packages remain memory_search, conversation and
  decision_routing; none implements the documented donor streaming/classifier.
- Installed Vault source searched read-only for donor/integration symbols;
  broad VoiceMem matches only existing VoiceMemoryLearning, with no donor adapter
  or streaming/classifier matches. No service or private volume altered/read.
- Existing VoiceMemoryLearning is factual transcript finalization through
  MemoryPipeline; it is not evidence of upstream VoiceMem integration. Existing
  MemoryRetriever uses lexical candidates plus Python cosine over stored embeddings.
  Neither supplies the documented partial-input speculative controller.

Disposition: documented VoiceMem integration NOT VERIFIED in current source or
installed source. Documentation/code mismatch remains explicit; do not silently
label it implemented, assume an entirely new integration is needed, or rebuild it.
Names may have changed in another artifact; absence of these symbols does not
prove the owner-reported build never existed. It does establish that these
documents cannot presently point to the promised implementation in this codebase.

Need to resolve actual implementation provenance before any VoiceMem build scope.
This is our source-audit responsibility, not a request that the owner find a branch.
