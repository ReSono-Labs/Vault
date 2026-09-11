# Vault Plan Anti-Drift Review

Review type: internal same-context self-review  
Candidate: planning set v1  
Result: SUPERSEDED — the owner corrected the primary donor and system-agent
boundary after this review. It does not authorize implementation.

## Attacks and findings

1. **Could “most Voice features” silently import cloud product scope?** Yes.
   Correction: Release 1 enumerates only owner-named local capabilities;
   unenumerated domains are deferred and require the missed-feature gate.
2. **Could exact Browser Voice mean copying cloud behavior?** No. Visual system
   is exact; cloud API, billing and operator behavior are excluded.
3. **Could donor-first damage donors?** Correction applied: donors are read-only
   and only bounded files are copied into Vault.
4. **Could multi-user be approximated with UI filters?** No. Requirements place
   scope in repository/service calls and demand cross-user negative tests.
5. **Could optional shared memory become a global pool?** No. Vault remains the
   authority and integrations have revocable operation/workspace grants.
6. **Could cross-platform goals force an early rewrite?** No. Python/React/SQLite
   donors remain; platform adapters and packaging are thin boundaries.
7. **Is public open-source distribution proven legal?** Not yet. R1 is PolyForm
   Noncommercial and Browser Voice license evidence is unresolved. Release is
   blocked pending licensor confirmation; donor reimplementation is prohibited.
8. **Are all later integrations necessary now?** No. Link, remote management,
   Hermes and OpenClaw are explicitly deferred.

## Traceability sample

V-001 -> Phase 1 -> offline/no-outbound tests -> local-start evidence.  
V-002 -> Phase 6 -> copied donor files + visual regression -> screenshot review.  
V-005/V-006 -> Phase 2 -> isolation tests -> denial evidence.  
V-007 -> Phase 3 -> donor parity/scope tests -> memory evidence record.  
V-008 -> Phase 5 -> hostile archive/grant tests -> lifecycle evidence.  
V-003/V-012 -> Phase 7 -> clean VM/upgrade/restore/uninstall evidence.

## Authorization conclusion

The former Phase 1 conclusion is invalid. The R1-first scaffold was removed.
Use `2026-08-29-GROUNDING-CORRECTION-REVIEW.md` and complete the Voice Vault
dependency inventory before implementation resumes.
