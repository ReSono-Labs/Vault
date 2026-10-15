# C04A — stop legacy silent review truncation, not complete windowing

Original grounding R31/R32 and complete-session analysis plan prohibit tail/candidate
loss disguised as completed review. REUSE the existing factual reviewer, limits,
provider error boundary and pipeline; no new agent, provider, schema or review loop.
Actual inspected code `OpenAIMemoryReviewer.review` sliced transcript[:100000],
Gemini fallback repeated that slice, and `_parse_review` sliced candidates[:32].
The existing unit test explicitly expected that candidate loss.

Internal prebuild review CONTINUE bounded safety correction: oversized transcript
fails before credential/provider access; dense output and oversized summary fail
before ingestion/publication. Preserve retained sources and ordinary supported
session behavior. Remove those slices; do NOT pretend this delivers windows,
pagination, consolidation, durable job recovery or full C04 acceptance. Existing
provider error responses remain compatible; factual failure cannot suppress the
independent procedural review. Test 100001 characters/no provider calls, 33 candidates
rejected without clipping, and supported exact limits. Pending full coordinator
must replace this explicit overflow with actual complete analysis, not restore
silent truncation. No installed DB or paid calls needed for this safety proof.
