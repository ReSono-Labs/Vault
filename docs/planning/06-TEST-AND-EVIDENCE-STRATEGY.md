# Test and Evidence Strategy

Status: frozen candidate v1

Carry donor tests with copied code, then add Vault adaptations. Required layers:
carried Voice donor contracts; selected datastore migration/repository tests;
API/auth tests; cross-user
negative tests; extension hostile-input tests; Browser Voice behavior and visual
regression; provider-disconnected tests; installer clean-host tests; backup and
recovery tests; dependency/license/security scans.

Every requirement maps to a phase, test and evidence record in
`PROGRESS.md`. Structural checks never substitute for semantic review. A phase
cannot exit on tests written only to its chosen implementation if they do not
prove the user/security outcome.
