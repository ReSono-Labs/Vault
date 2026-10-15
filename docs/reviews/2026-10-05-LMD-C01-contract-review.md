# LMD-C01 build contract review

Review ID LMD-CR01-r1. Target LMD-C01/r1. Reviewer: internal self-review, same
model/context; not independent or owner acceptance. Exact final target/input/source
identities bound by `2026-10-05-live-memory-phase02-candidate.sha256` plus current
plan/source manifests. Candidate initially drafted, then IN_REVIEW; READY only
after passing this review. No implementation tested in this review.

## Checks against request, corrected plan and existing code

- Original R01/R06/R31/R33 authorize independently replaceable retrieval retaining
  canonical store and normal lookup. D24 and architecture module r3 define the
  necessary foundation. It does not claim the required HNSW outcome yet.
- Existing MemoryService is current caller seam; keyword-only constructor accepts
  added optional backend without requiring composition/API/plugin changes. Search
  returns tuple of unchanged RetrievalMatch/MemoryRecord; explicit embedder/factory
  fallback behavior is named, not inferred.
- Legacy default delegates existing MemoryRetriever, preserving scope, rank/limit,
  lexical/exact semantic fallback and existing repair. New optional backend False
  repair policy preserves final search while removing its query-time repair only.
- New port has no write/grant/session/model authority. Necessary source imports
  are limited to existing read/retrieval types; no optional live/donor dependency.
  Existing MemoryService retains confirmation; adapter gets no tools/credentials.
- Paths allow minimal foundation only. No index/schema/SQL/db/provider/voice/Chat
  changes. An allowed service edit cannot acquire query/ranking or live duties:
  explicit semantic restrictions plus full diff review enforce this.
- Expected tests compare to actual old MemoryRetriever behavior, not only fake
  adapter output. Wrong-but-well-formed custom backend with repair=False but no
  retrieval, changed scope, hidden default SQL/extra dependency must fail review.
- Unit mocks establish compatibility/delegation; they do not establish PostgreSQL
  isolation/recall, latency, authentication, third-party entitlement or user UX.
  Those belong to later contracts and remain unready.
- Prerequisites actual inspected source/hash and23 baseline tests passing. No
  production resource/owner policy dependency to build this read-only compatibility
  slice. Readiness applies only to these files and behavior.
- Recovery restores only this slice; does not delete unrelated owner docs/data or
  rewind accepted publication. Exact source/candidate hashes and new-file diff
  inspected at build restart; changes stale this review.

| Finding | Severity | Evidence/source | Classification | Resolution |
|---|---|---|---|---|
| CR01-01 | Minor clarity | Repair policy boolean is future-engine policy, not user Live Memory preference | Correction | Contract explicitly distinct and legacy=True; no settings dependency |
| CR01-02 | Major possible proxy | A protocol scaffold alone could leave service using old inline path | Verification | Contract requires actual default adapter delegation and direct parity tests; no scaffold-only completion |
| CR01-03 | Major overclaim | No HNSW/DB query is in allowed paths | Verification | Outcome explicitly O2 foundation only, future indexed contract remains unready |

Decision PASS for exact C01/r1; lifecycle may move READY. No open blocker for this
contract. New signatures/resource assumptions outside allowlist require revised
Phase02 contract; readiness is not authorization for broader implementation.
Next route Phase03 only for LMD-C01/r1, then stop. Owner acceptance not claimed.
