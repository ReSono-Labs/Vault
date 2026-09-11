# Security Policy

## Supported versions

Security fixes are applied to the current development release. Until version
1.0, no older release line should be assumed to receive fixes.

## Reporting a vulnerability

Do not publish exploitable details in a public issue. Contact the repository
maintainers privately through the security-reporting channel configured on the
project host. Include the affected version, installation mode, reproduction
steps, impact, and whether secrets or personal data may have been exposed.

If no private reporting channel is configured yet, disclose only that a private
security contact is needed; do not post the exploit or sensitive logs.

## Operational boundary

Vault binds to loopback by default. Anyone who changes bind addresses, exposes
ports, configures a tunnel/VPN/reverse proxy, or publishes DNS is responsible
for transport authentication, TLS, firewall policy, updates, and monitoring.
Network reachability never replaces Vault authentication or authorization.

Never include Vault data volumes, `.runtime/`, credentials, TLS private keys,
database dumps, extension secrets, or provider tokens in a report.
