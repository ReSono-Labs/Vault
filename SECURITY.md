# Security policy

## Supported versions

Security fixes go into the latest release and `main`. Until version 1.0, older
releases do not receive fixes.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub: open the repository's
**Security** tab and choose **Report a vulnerability**
(<https://github.com/ReSono-Labs/Vault/security/advisories/new>). Do not open a
public issue or post exploit details anywhere public.

Include:

- the affected version or commit;
- how Vault is installed (Docker package, native Linux package, or from source);
- steps to reproduce;
- the impact;
- whether secrets or personal data may have been exposed.

Never attach Vault data volumes, `.runtime/` contents, credentials, TLS private
keys, database dumps, extension secrets or provider tokens. If such data is needed
to understand the issue, describe it instead.

## Scope and known limits

Vault binds to loopback by default. If you change bind addresses, expose ports,
or put Vault behind a tunnel, VPN or reverse proxy, you are responsible for that
transport: TLS, authentication at the edge, firewall rules, updates and
monitoring. Reachability never replaces Vault's own authentication and
authorization.

Hosted MCP packages run as separate processes without Vault's secrets, but they
are not yet confined by an OS-level sandbox. Import only packages you trust.
Current gaps are listed in
[docs/development/ARCHITECTURE.md](docs/development/ARCHITECTURE.md#known-gaps).
