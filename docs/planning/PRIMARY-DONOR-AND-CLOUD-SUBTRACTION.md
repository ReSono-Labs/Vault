# Primary Donor and Cloud Subtraction Contract

Status: controlling owner correction

## Primary donor

Vault is extracted from:

1. `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/`
2. `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/src/browser-voice/`

Preserve their features, contracts, runtime behavior, UI and tests wherever
they apply. R1 is not an alternative base.

## Mandatory subtraction

Do not port ReSono cloud authentication or any required ReSono control-plane
dependency. Remove hosted account login, hosted token/session authority, ReSono
device-trust approval, subscription/billing gates, operator approval, hosted
Vault registration/presence requirements, and mandatory polling of ReSono APIs.

## Local replacement boundary

The installed Vault owns local accounts, password verification, sessions,
workspace membership, integration identities, recovery and authorization.
Browser Voice uses the same visuals and local Vault endpoints. Provider APIs
explicitly configured by the owner are not ReSono authentication and remain
optional adapters.

## Anti-drift test

Failure occurs if basic install, login, management, voice, memory, workspace or
extension use contacts a ReSono domain, requires a ReSono-issued credential, or
waits for a hosted ReSono decision.
