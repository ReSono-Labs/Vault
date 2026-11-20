# Install Vault on Windows

## Overview

Vault runs on Windows through Docker Desktop. Docker keeps Vault and its
database together in the same isolated package used on other supported
computers. You run everything from Windows; there is no Ubuntu or WSL step.

## Before you begin

You need:

- a Windows 10 or Windows 11 computer;
- Docker Desktop (its installer sets up everything Docker needs); and
- the Vault Docker package (`resono-labs-vault-docker-….zip`), unzipped.

Vault does not need to replace Windows or take control of the rest of your
computer. Docker Desktop runs it in the background and keeps its private data
in dedicated Docker volumes.

## 1. Install Docker Desktop

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and
start it. Wait until it reports that the engine is running.

## 2. Install Vault

Open the unzipped Vault package folder in File Explorer, click the address bar,
type `powershell` and press Enter. In the PowerShell window, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\vault.ps1 install
```

Vault loads its image, starts, and opens your one-time setup link in the
browser. Create the master account there.

Keep the recovery login shown during setup somewhere safe. ReSono Labs cannot
retrieve it for you.

## 3. Choose folders for your agents

The install makes your user folder (for example `C:\Users\Name`) and your
drives visible to Vault. Nothing is used until you choose it. The setup wizard
offers to create a **ReSono Vault** folder in Documents (including Documents in
OneDrive) and to add other folders. You can change this any time in
**Settings → Folders**, and the master account can give other people access to
folders in **People and access**.

A drive connected after Vault started appears after the next
`.\vault.ps1 start` or a restart of the computer.

## 4. Trust Vault's local certificate

Vault protects its local connection with HTTPS. If your browser does not yet
trust it, export Vault's local certificate authority:

```powershell
docker cp resono-vault-vault-1:/var/lib/resono-vault/tls/vault-local-ca.crt .\vault-local-ca.crt
```

Double-click `vault-local-ca.crt`, choose **Install Certificate**, select
**Current User**, and place it in **Trusted Root Certification Authorities**.
Restart the browser afterward.

Only install the certificate created by your own Vault package. It is used to
trust this local Vault connection; it does not give Vault access to other
encrypted websites.

## Everyday use

Docker Desktop must be running before Vault can start. From the Vault package
folder in PowerShell:

```powershell
.\vault.ps1 start
.\vault.ps1 status
.\vault.ps1 stop
.\vault.ps1 setup     # show and open the setup link again
```

If PowerShell refuses to run the script, prefix the command with
`powershell -ExecutionPolicy Bypass -File`.

Open Vault at:

```text
https://127.0.0.1:8765
```

To update, unzip the new package and run `.\vault.ps1 update` from it.
Updating or reinstalling does not remove the Vault database or private user
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

```powershell
.\vault.ps1 status
.\vault.ps1 logs
```

### The browser says the connection is not trusted

Complete the certificate step above and fully restart the browser. Do not turn
off HTTPS verification.

### Port 8765 or 8766 is already in use

Another application is using Vault's local address. Stop that application or
change the conflicting Vault port in `vault.env` before starting the package.
Avoid exposing either port publicly.

## Current Windows limitation

The installer is a PowerShell script. A double-click installer is planned.
