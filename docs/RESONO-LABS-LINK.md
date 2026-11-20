# Connect Vault with ReSono Labs Link

## Overview

ReSono Labs Link can provide secure remote access to Vault when you want to
connect from another computer or device.

Vault includes a local connection bridge specifically for applications that
need a local HTTP or WebSocket destination. The bridge starts automatically
with the Vault Docker package.

In Link, a **service** can expose a **web interface**, an **agent** endpoint,
or both. Remote access to the Vault dashboard uses a **Custom HTTP/WebSocket
service** with a **web interface**. That is separate from Link **Agents**, which
are for agent-to-agent (A2A) communication.

## Before you begin

Make sure:

- Vault is running and healthy;
- ReSono Labs Link is installed on the same computer as Vault; and
- you have completed the normal ReSono Labs Link account and connector setup.

Use the ReSono Labs Link setup instructions for installing Link, signing in,
connecting this computer to your Link account, and managing public access.

## Add Vault to ReSono Labs Link

In ReSono Labs Link:

1. Open **Services**.
2. Choose **Add service**.
3. Select **Custom HTTP/WebSocket**.
4. When Link asks for the local destination, enter:

```text
http://127.0.0.1:8766
```

Use a clear name such as **Vault** or **ReSono Labs Vault**. Keep the service on
the same computer where the Vault Docker package is running.

Run connector setup once if the new service record is not wired yet.

Complete the remaining account, access, tunnel, and sharing steps using the
instructions provided by ReSono Labs Link.

## Test the connection

First confirm that Vault opens locally at:

```text
https://127.0.0.1:8765
```

Then use ReSono Labs Link's connection test or open the Vault address supplied
by Link. The normal Vault sign-in page should appear. Sign in with your Vault
account as usual.

ReSono Labs Link provides the connection to this computer. It does not replace
Vault's username, password, account permissions, or workspace privacy.

## If it does not connect

Check these items in order:

1. Confirm Docker Desktop or Docker Engine is running.
2. Confirm Vault is healthy.
3. Confirm the Link destination is exactly `http://127.0.0.1:8766`.
4. Confirm the Link connector is running on the same computer as Vault.
5. Follow ReSono Labs Link's troubleshooting instructions to check the Link
   account, connector, tunnel, and public address.

You can check Vault from the package folder with:

```bash
./vault-package status
./vault-package logs
```

## About the local bridge

The address on port `8766` is local to this computer. It forwards HTTP and
WebSocket traffic to Vault's protected HTTPS service and verifies Vault's local
certificate. It does not expose Vault directly to the internet and does not
bypass Vault authentication.

For more information, open **The Vault Local Connection Bridge** in Documents.
