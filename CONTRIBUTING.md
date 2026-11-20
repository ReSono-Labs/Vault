# Contributing

Thanks for helping with Vault. This page covers the workflow and the rules every
change must follow.

## Before you start

- Read [docs/development/ARCHITECTURE.md](docs/development/ARCHITECTURE.md). It
  explains how Vault is put together and lists the rules that keep it consistent.
- Set up the test environment: [docs/development/LOCAL-TEST-ENVIRONMENT.md](docs/development/LOCAL-TEST-ENVIRONMENT.md).
- To run your build as an installed package, see
  [docs/development/PRODUCTION-PACKAGE.md](docs/development/PRODUCTION-PACKAGE.md).
- For anything large (a new domain, a new agent surface, a schema redesign), open
  an issue first so the approach can be agreed before you write it.

## Making a change

1. Branch from `main`.
2. Follow the existing structure. Put each piece where the architecture document
   says it belongs, and reuse the existing service rather than adding a parallel one.
3. Add tests:
   - the success case;
   - access denied;
   - malformed input;
   - isolation between users and workspaces;
   - recovery after a restart, where state is kept.
4. Run the checks below.
5. Update the documentation in the same change when behaviour, commands,
   configuration or structure change. This includes `ARCHITECTURE.md` when you add,
   move or remove a module or an API area. Add a `CHANGELOG.md` entry under
   **Unreleased** for anything a user or integrator would notice.
6. Open a pull request that says what changed, why, and how you tested it.

## Checks

```bash
python3 scripts/check_public_tree.py
python3 scripts/test_env.py test
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

CI runs the same checks on every push and pull request.

## Rules

- **Agents.** Vault has two agent kinds, Voice and Background. Plugins, Skills, MCP
  servers and tools add capabilities, never new agents.
- **Tools.** Register every tool in the `ToolCatalog` and invoke it through
  `ToolCatalog.invoke`, so grants, schema checks and approvals apply. A tool is
  done when it is enumerated into the intended agent's session or run, visible in
  the Library, and tested through that path.
- **Scope.** Every read and write carries the user and workspace and is checked in
  the service or repository, not only in the UI.
- **Approvals.** When a user asks for an action directly, the agent prepares it and
  shows one approval card. Do not add a second confirmation step.
- **Network.** Listeners stay on loopback by default, and any other address
  requires TLS. Do not add telemetry, hosted dependencies or silent outbound
  traffic.
- **Secrets.** Keep secrets out of source, logs, model context, memory and plugin
  processes. Never commit `.env*`, `.runtime/`, keys, certificates, database dumps
  or local data.
- **Paths.** Use paths relative to the repository or derived from configuration.
  Do not commit absolute paths from your machine; `scripts/check_public_tree.py`
  rejects them.
- **Migrations.** Schema changes are new numbered files in
  `app/vault_runtime/migrations/` (`NNNN_name.py` with `apply(cursor)`, optionally
  `NNNN_name.sql`). Never edit, rename or delete a merged migration: the runner
  stores each checksum and refuses to start when one changes.
- **API changes.** If you change a route or its responses on purpose, regenerate
  the route snapshot (see the guard tests in LOCAL-TEST-ENVIRONMENT.md) and review
  the diff in your pull request.
- **Web styles.** After changing CSS in `frontend/src`, run
  `npm --prefix frontend run theme:aurora` and commit the regenerated Aurora file.
- **Tests and data.** Never point tests at an installed or manually used Vault
  database. The test harness refuses any database except the isolated one.
- **Third-party code.** Only add code whose licence is compatible with Apache 2.0.
  Keep its notice, and record it in `NOTICE`.

## Documentation

- User guides are the seven files at the top of `docs/`. They ship in the image
  and Vault Help reads them.
- Developer documentation lives in `docs/development/`. Vault Help reads it too.
- Plans, reviews and working notes do not belong in the repository.

## Licence

Vault is licensed under the [Apache License 2.0](LICENSE). By contributing, you
confirm that you have the right to submit your work under that licence and that
any required third-party notices are kept.

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security issues
privately as described in [SECURITY.md](SECURITY.md).
