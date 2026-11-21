# Decision: scope of the extension standards work

Date: 2026-11-20. Decided by: the Vault maintainer (device owner).
Evidence: the published gap reviews on
[#2 Agent Plugins](https://github.com/ReSono-Labs/Vault/issues/2),
[#3 Agent Skills](https://github.com/ReSono-Labs/Vault/issues/3) and
[#4 MCP](https://github.com/ReSono-Labs/Vault/issues/4), reviewed against main `71b93e2`.

These decisions bound the implementation of #2, #3 and #4. A change to any of them
needs a new decision record.

## Order of work

Four reported defects are contained first, before the wider changes:

1. Server-supplied MCP schemas must never cause network requests.
2. One workspace must never read or delete another workspace's skill or plugin files.
3. A failed upgrade or a removal must never delete data another install still uses.
4. Safe mode must stop supervised processes and keep them stopped.

The checks that matter are the behavioural ones named in each fix: the bytes each
user reads, data surviving a forced failure byte for byte, zero outbound requests,
and a process that is gone and stays gone after restart.

## Decisions

| Area | Decision |
|---|---|
| Transports | Skip stdio and the deprecated HTTP+SSE transport (2024-11-05) with a clear per-server message, and keep loading valid siblings. Support streamed responses over current Streamable HTTP. |
| Legacy MCP | Keep MCP 2025-11-25 working through a separate, separately tested adapter. It shares one lower layer with the current adapter for destination policy, header checks, bounded reading and error mapping. Current-version traffic never depends on the legacy handshake or session. |
| Authorization and accounts | Implement the MCP authorization flow. Credentials are personal by default. A shared service account needs explicit owner configuration, a visible "shared" label and a grant to use it. If a personal token is missing or expired, that user is asked to reconnect; Vault never falls back to another person's account. |
| Skills | Bundled skill scripts can be read as files. Execution stays outside the skill loader. Skill names follow the pinned upstream reference validator, and tests run against it. |
| MCP scope | This release supports MCP tools. Vault advertises only capabilities it implements. |
| Link companion | Keep its existing tool contract, documented and tested. Add pagination and backoff for discovery and polling. A timeout after a tool call was sent can mean the action already happened, so calls are never replayed automatically. |
| Namespace | Vault package data uses the `com.resonolabs.vault` namespace. The root `vault.json` reader stays for existing packages. |
| Ambiguous legacy data | Keep the bytes, and block access through every conflicting install until the device owner resolves ownership. Show the owner the conflicting installs and the recovery options. Reading private file contents still requires workspace authorization. Legacy name handling applies only to installs that already exist. |
| Safe mode | Device-wide and persistent. It blocks new starts, stops running supervised processes and their children, and holds through boot and automatic restart. |
| Remote schema references | Resolve references offline wherever Vault validates schemas supplied by a server. References inside the same document keep working. |

## Trust model for hosted executable plugins

Before install, the user's connected agent reviews the quarantined package and raises
red flags. The user explains or approves them, and the approval is bound to the exact
package hash.

That review helps the owner decide. It cannot guarantee what a running process will do
later. Until Vault confines hosted processes at the operating-system level, a hosted
executable plugin is **trusted code running with the Vault process's effective access**.
In the Docker package that means the same OS user and container as Vault, including
read access to Vault's data volume. The install screen and the kit documentation must
say this plainly. On a four-person device that belongs in the install decision now.

## What would change these decisions

- OS-level confinement of hosted processes becomes available: revisit the trust model text.
- A transport or capability outside this list is needed by a supported integration.
- The upstream standards publish a new revision.

## Addendum 2026-11-20: hosted processes are confined

The condition above is met in part: OS-level confinement now exists. Supervised plugin
and hosted MCP processes start under Linux Landlock (`extensions/confinement.py`). The
kernel lets each read its own package and system files and read and write only its own
data folder; Vault's data volume, keys, other installs (including a same-name install in
another workspace) and other processes' `/proc` entries are refused. Tests prove this
with real access attempts.

The trust model text changes accordingly: a hosted package is **confined, not
sandboxed**. It still runs as Vault's operating-system user, keeps network access and
shares CPU and memory, so the install warning and the owner's approval of the exact
package stay. Where the kernel has no Landlock, the process runs unconfined and its
status reports `confinement: none`.
