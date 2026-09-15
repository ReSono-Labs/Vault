# Changelog

Notable release changes are recorded here. The project is currently preparing
its first public development release.

## Unreleased

- Workspace page uses the signed-in name as `{name}'s Workspace`, drops the private-files subtitle, keeps the folder title above `Up one folder`, and adds Close on file preview.
- Connections AI & Voice no longer shows Use API key or Disconnect provider; Connect OAuth and Disconnect OAuth are mutually exclusive.
- Settings Linked folders heading is larger, centered, and spaced below the separator.
- Platform Guide matches current Workspace chrome, Connections AI & Voice buttons, and Library page headings.

- Added public installation, contribution, security, conduct, and licensing
  documentation.
- Hardened remote MCP destinations against private-network and DNS-rebinding
  targets while preserving explicit loopback integrations.
- Added non-executing Plugin package risk review to extension preflight.
- Added transport-aware `Secure` session cookies while preserving the
  loopback-only HTTP compatibility bridge.
