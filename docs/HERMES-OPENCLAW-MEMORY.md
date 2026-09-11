# Connect Hermes and OpenClaw to Vault Memory

ReSono Labs Vault can be the shared long-term memory for Hermes and OpenClaw.
Each agent keeps its own personality, tools, conversations, and abilities.
Vault provides the approved memory they can recall across sessions.

This guide covers the setup performed on the computer running Hermes or
OpenClaw. Vault must already be installed, running, and reachable from that
computer.

## What the connection does

After you connect an agent:

- Vault supplies a small, non-sensitive startup profile when a new session
  begins;
- the adapter searches Vault for memories related to each new prompt;
- recalled memories are added to the session as context, not instructions;
- successful conversations are proposed to Vault for review; and
- Vault decides whether anything is useful and durable enough to save.

Hermes and OpenClaw do not write directly to the Vault database. They submit
proposals through their own separately approved connection. Vault performs the
classification, reconciliation, evidence checks, and ingestion.

The connection also adds five memory tools: search, get, store, correct, and
forget. Correct and forget work only while that exact access remains approved.

## Before you begin

You need:

- a running ReSono Labs Vault;
- the Vault adapter files from the `integrations` folder in the Vault download;
- a working Hermes or OpenClaw installation; and
- access to the Vault account whose memory this agent should use.

Download the adapter for the agent you are connecting:

- [Download the Hermes memory plugin (ZIP)](/downloads/resono-vault-hermes-memory-0.1.0.zip)
- [Download the OpenClaw memory plugin (ZIP)](/downloads/resono-vault-openclaw-memory-0.1.0.zip)
- [Download this Vault's local CA certificate](/vault-local-ca.crt)

Extract the adapter archive on the computer running that agent. The commands
below should be run from the folder containing the extracted adapter directory.
Compressed TAR versions are available in the same download folder for users
who prefer them.

Use the Vault address that is reachable from the agent computer. Common
examples are:

```text
Same computer: https://127.0.0.1:8765
Private network or VPN: https://your-vault-address:8765
```

Do not use Vault's Link compatibility bridge on port `8766` for these memory
adapters. They support Vault's verified HTTPS connection directly.

If Vault uses its local certificate authority, the agent computer must trust
that CA. Do not disable certificate checking.

## Connect Hermes

### 1. Install the Hermes adapter

Open a terminal on the computer running Hermes. Install the extracted adapter
into Hermes's own Python environment:

```text
~/.hermes/hermes-agent/venv/bin/python -m pip install ./hermes-vault-memory
```

If Hermes is installed somewhere else, replace the first path with the Python
inside your Hermes installation. Installing the package into an unrelated
system Python will not make it visible to Hermes.

### 2. Set the Vault address and certificate when needed

If Vault is not available at `https://127.0.0.1:8765`, add its address to
`~/.hermes/.env`:

```text
RESONO_VAULT_MEMORY_URL=https://your-vault-address:8765
```

When the agent computer needs Vault's local CA file, also add:

```text
RESONO_VAULT_CA_FILE=/full/path/to/vault-ca.crt
```

### 3. Pair Hermes with Vault

Run:

```text
resono-vault-memory-pair
```

The command opens Vault in your browser. Sign in to the correct Vault account,
review the requested memory access, and choose **Connect**. No credential needs
to be copied by hand.

The pairing command stores the local credential in `~/.hermes/.env` and selects
`resono-vault` as Hermes's external memory provider.

### 4. Restart and check Hermes

Run:

```text
hermes gateway restart
hermes memory status
```

The status should show `resono-vault` as installed, available, and active.
Hermes's built-in `MEMORY.md` and `USER.md` files remain available; Vault is
the selected external memory provider.

## Connect OpenClaw

The Vault adapter supports OpenClaw 2026.8.1 or newer. Use a supported Node.js
version for your OpenClaw release.

### 1. Install the OpenClaw adapter

Open a terminal on the computer running OpenClaw. From the folder containing
the extracted adapter, run:

```text
openclaw plugins install ./openclaw-vault-memory --force --accept-capabilities
```

`--force` confirms that you intentionally chose the reviewed local package.
`--accept-capabilities` approves the memory tools and conversation hooks needed
for automatic recall and saving.

### 2. Trust Vault's certificate when needed

If the agent computer needs Vault's local CA, add its full path to
`~/.openclaw/.env`:

```text
NODE_EXTRA_CA_CERTS=/full/path/to/vault-ca.crt
```

If Vault is not at `https://127.0.0.1:8765`, also add:

```text
RESONO_VAULT_MEMORY_URL=https://your-vault-address:8765
```

### 3. Pair OpenClaw with Vault

Run the pairing command from the installed extension:

```text
node ~/.openclaw/extensions/resono-vault-memory/pair.mjs
```

The command opens Vault in your browser. Sign in to the correct Vault account,
review the requested access, and choose **Connect**.

Pairing automatically:

- stores the credential in `~/.openclaw/.env`;
- enables the ReSono Vault Memory plugin;
- selects it in OpenClaw's memory slot;
- enables automatic recall and completed-turn proposals;
- enables startup memory injection;
- allows the two required conversation hooks; and
- explicitly turns OpenClaw local dreaming off.

### 4. Keep dreaming off

OpenClaw local dreaming must remain disabled while Vault owns ingestion. Two
independent ingestion systems can create duplicate or competing memories.
Vault reviews completed turns and decides what should become durable memory.

The pairing command sets:

```text
plugins.entries.resono-vault-memory.config.dreaming.enabled=false
```

If you edit the plugin configuration later, leave **OpenClaw local dreaming**
off.

### 5. Restart and check OpenClaw

Restart the OpenClaw gateway using the normal command for your installation,
then run:

```text
openclaw plugins inspect resono-vault-memory --runtime --json
openclaw gateway status
```

The runtime inspection should show the plugin enabled, the Vault memory slot
selected, five memory tools, and two conversation hooks.

Selecting the Vault memory slot replaces OpenClaw's `memory-core` slot. It does
not remove OpenClaw's unrelated SQLite runtime and session state.

## How memory enters a session

Both adapters use two forms of automatic recall.

### Startup memory

The first prompt in a session receives a small profile from Vault. It contains
up to eight active, normal-sensitivity, medium- or high-confidence memories.
It is not a dump of everything Vault knows.

Startup memory is on by default. To keep search-based recall but disable the
startup profile:

```text
Hermes: RESONO_VAULT_STARTUP_MEMORY=false
OpenClaw: plugins.entries.resono-vault-memory.config.startupMemory=false
```

### Prompt-based recall

Before later prompts, the adapter searches Vault using the current request and
adds relevant results to the agent's context. The agent is explicitly told to
treat recalled memory as data, not as instructions.

For OpenClaw, keep `autoRecall` enabled. Hermes performs this through its active
memory-provider lifecycle.

## How conversations are saved

The adapters do not blindly save every message as memory.

After a successful primary-agent turn:

1. the adapter submits a bounded conversation excerpt to Vault;
2. Vault's memory reviewer classifies the proposal;
3. temporary requests, unsupported claims, and unsuitable information are
   rejected;
4. accepted memory is reconciled with existing memory; and
5. Vault stores the memory with its evidence and scope.

OpenClaw uses `autoCapture`; Hermes uses its primary-agent turn synchronization.
Non-primary Hermes contexts do not automatically propose memory.

Saving can take several seconds because Vault performs the review before
committing durable memory. The agent conversation does not need to wait for
that review to become a normal response.

## Test the connection

Use a real, durable fact that you are comfortable storing. For example, tell
Hermes:

```text
Please remember that I prefer project summaries as short bullet points.
```

Allow the completed turn to be reviewed. Start a fresh OpenClaw session and
ask:

```text
How do I prefer project summaries?
```

You can repeat the test in the opposite direction. A one-time test phrase may
correctly be rejected by Vault, so test with an actual durable preference.

In Vault, open **Memory** to confirm that Hermes and OpenClaw are listed as
separate active connections. Each connection is independently revocable.

## Disconnect safely

### Disconnect Hermes

```text
resono-vault-memory-pair --disconnect
```

This revokes the Vault connection, removes the local credential, and turns off
Hermes's external memory provider. Hermes's built-in memory remains.

### Disconnect OpenClaw

```text
node ~/.openclaw/extensions/resono-vault-memory/pair.mjs --disconnect
```

This revokes the Vault connection, removes the local credential, restores the
`memory-core` slot, and disables the Vault plugin. Restart OpenClaw afterward.

Use `--local-only` only when Vault cannot be reached or the connection was
already revoked in Vault.

You can also revoke an agent immediately from **Vault → Memory**. After
revocation, use the matching disconnect command on the agent computer to clean
up its local configuration.

## Common problems

### Vault does not open during pairing

Copy the pairing address shown in the terminal into a browser that can reach
Vault. Pairing expires after ten minutes; run the command again if needed.

### Certificate unknown or certificate verification failed

The agent computer does not trust Vault's local CA. Configure
`RESONO_VAULT_CA_FILE` for Hermes or `NODE_EXTRA_CA_CERTS` for OpenClaw. Do not
turn TLS verification off.

### Hermes cannot find the provider

The adapter was probably installed into the wrong Python environment. Install
it with the Python inside the Hermes installation, restart Hermes, and check
`hermes memory status` again.

### OpenClaw shows the plugin but does not inject memory

Confirm that the Vault plugin owns the memory slot, `autoRecall` and
`startupMemory` are enabled, and its conversation hooks are allowed. Runtime
inspection should report two hooks. If OpenClaw reports legacy workspace state,
stop its gateway, run `openclaw doctor --fix`, and restart it.

### A conversation did not become memory

That does not necessarily mean the connection failed. Vault intentionally
rejects temporary requests, greetings, fabricated test markers, unsupported
claims, secrets, and information that is not useful as durable memory.

### The agent cannot use memory after revocation

That is expected. Revocation immediately invalidates that agent's credential.
Run the local disconnect command to finish cleanup, then pair it again if you
want to restore access.
