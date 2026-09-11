# Install Vault on Windows

## Overview

Vault runs on Windows through Docker Desktop. Docker keeps Vault and its
database together in the same isolated package used on other supported
computers.

## Before you begin

You need:

- a Windows 10 or Windows 11 computer that supports WSL 2;
- Docker Desktop set to use Linux containers;
- the Ubuntu app for WSL; and
- a copy of the Vault package.

Vault does not need to replace Windows or take control of the rest of your
computer. Docker Desktop runs it in the background and keeps its private data
in dedicated Docker volumes.

## 1. Install WSL and Docker Desktop

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

Restart Windows if asked. Open Ubuntu once and complete its short username and
password setup.

Install Docker Desktop, select the WSL 2 engine when prompted, and make sure
Docker Desktop is running. In Docker Desktop, open **Settings → Resources →
WSL integration** and enable integration for Ubuntu.

## 2. Open the Vault package in Ubuntu

Open Ubuntu from the Start menu and change to the folder containing Vault. If
possible, keep the package inside your Ubuntu home folder instead of under
`C:\`; this normally gives Docker better file performance.

Vault's current package helper uses `uv`. Install it once inside Ubuntu:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen Ubuntu after installation if the `uv` command is not found.

## 3. Start Vault

From the Vault package folder, run:

```bash
./vault-package install
./vault-package setup
```

The first command builds and starts Vault. The second prints a one-time setup
address. Copy that address into your Windows browser and create the master
account.

Keep the recovery login shown during setup somewhere safe. ReSono Labs cannot
retrieve it for you.

## 4. Trust Vault's local certificate

Vault protects its local connection with HTTPS. If your browser does not yet
trust it, export Vault's local certificate authority from the package folder:

```bash
docker compose cp vault:/var/lib/resono-vault/tls/vault-local-ca.crt ./vault-local-ca.crt
explorer.exe .
```

In the Windows folder that opens, double-click `vault-local-ca.crt`, choose
**Install Certificate**, select **Current User**, and place it in **Trusted Root
Certification Authorities**. Restart the browser afterward.

Only install the certificate created by your own Vault package. It is used to
trust this local Vault connection; it does not give Vault access to other
encrypted websites.

## Everyday use

Docker Desktop must be running before Vault can start. Use these commands from
the Vault package folder in Ubuntu:

```bash
./vault-package start
./vault-package status
./vault-package stop
```

Open Vault at:

```text
https://127.0.0.1:8765
```

Updates can reuse the same package and data:

```bash
./vault-package install
```

Reinstalling or updating does not remove the Vault database or private user
data.

## Connecting another local application

Some desktop applications accept a local HTTP address but cannot connect
directly to Vault's local HTTPS address. Vault includes a local connection
bridge for this situation:

```text
http://127.0.0.1:8766
```

The bridge is started automatically with Vault. See
[The local connection bridge](LOCAL-CONNECTION-BRIDGE.md) for what it does and
when to use it.

## Troubleshooting

### Vault does not start

Make sure Docker Desktop is open and reports that its engine is running, then
run:

```bash
./vault-package status
./vault-package logs
```

### The browser says the connection is not trusted

Complete the certificate step above and fully restart the browser. Do not turn
off HTTPS verification.

### Port 8765 or 8766 is already in use

Another application is using Vault's local address. Stop that application or
change the conflicting Vault port before starting the package. Avoid exposing
either port publicly.

## Current Windows limitation

Vault currently uses Docker Desktop and Ubuntu through WSL 2 on Windows. There
is not yet a separate native Windows installer or PowerShell package manager.
The Vault application and stored data are the same Docker package; only the
Windows startup workflow is different.
