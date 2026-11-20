# The Vault Local Connection Bridge

## Overview

Vault includes a small connection bridge for local applications that support
HTTP but cannot connect directly to Vault's HTTPS service.

Most people do not need to configure the bridge. It starts automatically with
the Docker package.

## The two local addresses

Vault's normal address is:

```text
https://127.0.0.1:8765
```

The compatibility bridge is:

```text
http://127.0.0.1:8766
```

Use Vault's normal HTTPS address in a browser. Use the bridge only when a
trusted application specifically needs a local HTTP or WebSocket address.

## What the bridge does

The connection path is:

```text
Local application
      ↓
http://127.0.0.1:8766
      ↓
Vault bridge inside Docker
      ↓ verified HTTPS
Vault at https://vault:8765
```

The application connects to the bridge on your computer. The bridge then
connects to Vault over HTTPS, verifies Vault's locally generated certificate,
and passes the response back to the application. It also supports long-lived
WebSocket connections used for live and voice features.

The bridge does not replace Vault's security, sign users in automatically, or
read Vault data on its own. Vault still handles authentication, permissions,
accounts, and access to private information.

## Why it exists

Local applications do not all support the same connection types. Some can use
an HTTP or WebSocket destination but cannot be configured to trust a private
local HTTPS certificate. The bridge provides a narrow compatibility point
without weakening or changing Vault's HTTPS service.

This also lets compatible desktop connectors work with Vault without requiring
a special version of Vault or a change to the connector.

## Is the bridge exposed to the internet?

No. The Docker package publishes the bridge only on `127.0.0.1`, also called
the loopback address. That means it is available to applications running on
the same computer and is not offered directly to other computers or the public
internet.

A separate remote-access product may carry traffic to a connector on this
computer, but the bridge itself remains local.

## Security protections

The packaged bridge:

- listens only on the local computer;
- verifies Vault's certificate instead of ignoring certificate errors;
- has read-only access to the certificate needed for verification;
- supports HTTP and WebSocket forwarding; and
- runs as a restricted Docker service.

You still sign in to Vault normally. Connecting through the bridge does not
bypass Vault accounts or permissions.

## When should I use it?

Use `http://127.0.0.1:8766` when the instructions for a trusted local connector
ask for an HTTP or WebSocket destination for Vault.

For **ReSono Labs Link**, add a **Custom HTTP/WebSocket service** under
**Services → Add service** and set the local destination to
`http://127.0.0.1:8766`. That exposes Vault's **web interface** remotely. It is
not the same as Link **Agents** used for agent-to-agent communication. See
[Connect Vault with ReSono Labs Link](RESONO-LABS-LINK.md).

Continue using `https://127.0.0.1:8765` when opening Vault directly in a web
browser.

Do not publish the bridge on a public network, place it behind ordinary port
forwarding, or change it to listen on every network interface. Use a dedicated
authenticated remote-access system when access from another device is needed.

## If the bridge is unavailable

First confirm that Docker Desktop or Docker Engine is running, then check the
package:

```bash
./vault-package status
./vault-package logs
```

Restarting the Vault package restarts the bridge along with it:

```bash
./vault-package stop
./vault-package start
```
