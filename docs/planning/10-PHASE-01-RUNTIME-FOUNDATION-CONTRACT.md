# Phase 1 Runtime Foundation Contract

Status: accepted extraction slice 1A  
Authority: `GROUNDING.md`, anti-drift protocol, Phase Build Contracts

## Scenario

A developer can load deterministic standalone Vault configuration on Linux,
Windows, or macOS without ReSono cloud credentials, a ReSono endpoint, a
privileged filesystem path, or any outbound network operation.

## Exact donor inputs

Primary donor root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

| Donor file | SHA-256 | Disposition |
|---|---|---|
| `app/vault_runtime/local_api/config.py` | `72f3cd733189678dc988221571cef0cccd3abaef519cba0c520e86c3067c2a38` | Copy and locally subtract hosted/deferred fields |
| `app/vault_runtime/runtime_paths.py` | `118a37308ae769d18ef17ab87a6d45738df21749ebfc9b946056a6d94dcac1e8` | Copy and adapt hard-coded paths to OS-local roots |
| `tests/unit/test_vault_runtime_local_api_config.py` | `83858ed1a0985a26b83733e4406f1648e72fdcaecf4010bce4fb3376daf6b756` | Carry applicable security behavior; replace cloud/tunnel cases with standalone/path cases |

Package `__init__.py` files are copied only as package boundaries. Imports of
uncopied API/server modules are removed from the local API initializer.

## Preserved behavior

- token is mandatory and may be loaded from a file;
- management binding accepts loopback addresses only;
- Browser Voice listener requires explicit, non-wildcard HTTP(S) origins;
- media relay requires the startup listener, fixed path, and distinct port;
- integer, bounded-integer, boolean, and origin parsing semantics remain;
- runtime-artifact cache root remains explicitly overrideable.

## Grounded adaptations

- Remove hosted `api_base_url` and `service_api_key`; standalone Vault has no
  ReSono control-plane authority.
- Do not port R1 tunnel, Link, notification sidecar, or external-AI socket
  configuration in Phase 1; they are deferred or require later contracts.
- Replace `/etc`, `/var/lib`, `/run`, and `/tmp` defaults with an owner-local
  root resolved from an explicit override or standard OS environment.
- Keep all adaptations in this repository; donor files remain read-only.

## Negative acceptance checks

- no `RESONO_API_BASE_URL` or service API key field;
- no cloud secret decryption module;
- no R1/Link/Tailscale listener;
- no non-loopback management bind;
- importing and resolving configuration performs no network operation;
- no agent registration of any kind.

## Exit evidence

Tests must cover token loading, loopback rejection, origin validation, media
listener constraints, explicit data-root override, Linux/XDG, Windows, and
macOS path selection. Donor Git status and diff fingerprints must match the
captured pre-port baseline.
