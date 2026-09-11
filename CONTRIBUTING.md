# Contributing

Start with `GROUNDING.md`, `SKILLS.MD`, `INDEX.MD`, and the anti-drift protocol
under `docs/protocols/`. They define the product boundary, donor provenance,
security rules, and required evidence.

Contributions should:

- preserve the fixed Voice Agent and Background Agent model;
- keep listeners loopback-first and extensions disabled by default;
- avoid new hosted dependencies, telemetry, or silent outbound traffic;
- include positive, denial, malformed-input, isolation, and recovery tests;
- keep secrets, local runtime state, donor checkouts, and generated artifacts
  out of commits; and
- update the controlling contract and evidence when behavior changes.

Run the relevant Python and frontend tests before submitting a change. Never
run integration tests against an installed or manually used Vault database.

By contributing, you represent that you have the right to submit the work under
the repository's license and that required third-party notices are preserved.
