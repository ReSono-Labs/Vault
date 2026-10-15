# C06E — real Chat draft preparation mount

Owner LC-R01–07 and latest instruction require observable memory/tool preparation
while typing. Branch feature/live-memory-decisions. REUSE exact Vault absolute root
/home/christian/Documents/Projects/ReSono-Labs-Vault/: live_memory/{voicemem_stream,
preparation,canonical_ports,current_state,stream_registry}.py; memory_search/
{indexed,postgres}.py; conversation/{api,runtime,repository}.py; decision_routing/
{selector,contracts}.py; voice/credentials.py and tools/catalog.py; frontend/src/
browser-voice/conversation/{api,useConversation,ChatPanel,conversation.css}.
NEW joining live_memory/chat_runtime.py and optional decision_routing/openai_transport.py.
No replacement scheduler, memory store, auth/grant authority, tool executor or agent.

One bounded owning asyncio loop hosts existing VoiceMem streams; authenticated
CSRF-protected draft revisions replace transient state, including empty/IME input.
Scoped read-only status polls expose only current validated envelopes. Limit handles,
expire idle streams, count underlying jobs, reject conflicting/out-of-order updates.
History context is server-owned, bounded and explicitly contextual, never permission.
Recall uses existing read-only pgvector SQL backend, no draft vector repair/writes.
Tool routing uses actual currently authorized definitions, existing selector and
documented standalone Decisions endpoint; classify only, no arguments/effects.
Distinguish current-tool proposals from retrieved learned rules. Missing credentials,
endpoint access or selection evidence stays unavailable, not simulated success.

Material gate: current-tool finite choices permit cold-start preview without
inventing learned rules. They do not replace semantic learned-example retrieval
or certify C14/C15 completion. Alternative keyword route prediction rejected.
Independent decision draft loop rejected. CONTINUE bounded Chat mount; learned
catalog, Voice input transport, complete review/activation remain later integration.

Frontend invalidates visible readiness synchronously on mutation/Send; stale HTTP
callbacks fenced by revision and view lifecycle. Polls do not trigger model work.
Debounce/coalescing inherited from VoiceMem; IME paused. New Chat may create an
empty canonical conversation header, but unsent text never enters durable history.
Send clears only the display; the submitted worker seals the server stream and
uses its existing exact immutable-final rebind with a 1.5s deadline. Current
history/memory/preference/session/grants are revalidated. Failure/changed input
uses normal final retrieval; no pre-Send execution/learning. Validated proposed
tool IDs are contextual hints to the normal final model, never execution authority.
Existing LocalToolAuthority gains one batched read of the same grant predicate;
initial actual test exposed per-tool-connection latency and selection timeout.
No permission changes; execution still invokes the existing single-tool authorizer.

Tests: actual lifecycle with deterministic ports, model/transport failures, stale
and deleted drafts, isolation, Send fencing, IME, no tool invocation; focused existing
tests/build. No paid calls or installed DB experiments. Removal: disconnect host
mount and UI observer; durable history/memory intact. Internal review: freshness
and current grants required before exposure, no claimed reasoning/confidence,
bounded provider timeout/no retries, idle cleanup and shutdown drain required.
# Incremental display refinement

Memory may be displayed after its current-snapshot validation while parallel
decision selection is still pending. Reuse the same preparation attempt/callback,
not another search or loop. Never display an initial tool choice that still requires
fresh-memory reconsideration. Every edit clears both complete and interim envelopes;
polling validates the interim memory records with the same current-state guard.
