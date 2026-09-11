# Install ReSono Labs Vault

Choose the setup that fits your computer. Docker is the easiest option for most people. The Linux package is for people who prefer to run Vault directly as a Linux service.

Your memories, documents, and settings stay on the computer running Vault. During installation, Vault also prepares secure access from that computer and from phones on the same local network.

---

## Docker

**Recommended for most people**

The Docker package includes Vault and its local connection bridge in one ready-to-run download. It keeps the app and its supporting services together, which makes installation and future updates simpler.

### Before you begin

Install and start Docker Engine or Docker Desktop. Your computer will also need Docker Compose and either `zstd` or `gzip`.

On Windows, use Docker Desktop with WSL 2 enabled, then follow the steps below from your Linux terminal.

### Install Vault

1. Download the **ReSono Labs Vault — Docker** ZIP file.

2. Extract the ZIP file and open a terminal inside the extracted folder.

3. Start the installation:

   ```bash
   ./vault install
   ```

   Vault loads the included app, creates its private database and storage, starts the local connection bridge, and prepares secure access for your computer and local network.

4. Create your one-time setup link:

   ```bash
   ./vault setup
   ```

5. Open the setup link shown in the terminal and follow the guided setup.

You can open the link on the computer running Vault or on a phone connected to the same local network. You do not need to restart setup to switch devices.

### Why Vault creates a security certificate

During installation, Vault automatically creates a private local certificate for your computer and its local network address. The certificate turns the connection into HTTPS, which encrypts information moving between your browser and Vault. This helps prevent another device on the network from reading or changing that information.

The certificate belongs to your Vault and is created on your device. It is not supplied by a public website or shared with ReSono Labs.

Because it is private and local, a browser or phone may not recognize it the first time. If prompted, follow Vault's certificate instructions to trust the **ReSono Vault Local CA** on that device. This tells the device that your locally installed Vault certificate is valid. Only install this certificate on devices you own or trust.

### What is installed?

- **Vault** stores your memory, documents, settings, plugins, and agent information.
- **A private database** keeps Vault's saved information on your device.
- **The local bridge** lets compatible apps connect through a simple local HTTP or WebSocket address while Vault remains protected by HTTPS.

The database and bridge are not exposed to your local network. Only Vault's secure interface is made available for local access.

### Useful commands

```bash
./vault status
./vault logs
./vault stop
./vault start
./vault update
./vault uninstall
```

A normal uninstall keeps your saved Vault data so it can be used again later.

---

## Linux

**Run Vault directly on Linux without Docker**

The Linux package installs Vault as a system service. Choose this option when you are comfortable managing a Linux computer and its local database.

### Before you begin

Use a 64-bit Debian 12 computer or a compatible Linux distribution. The computer must have:

- `systemd`
- PostgreSQL running locally
- The `pgvector` extension for your PostgreSQL version
- `bubblewrap` for safely isolated third-party capabilities

### Install Vault

1. Download the **ReSono Labs Vault — Linux x86_64** ZIP file.

2. Extract the ZIP file and open a terminal inside the extracted folder.

3. Install the Vault service:

   ```bash
   sudo ./install.sh
   ```

   The installer places Vault in `/opt/resono-vault`, creates its service, and prepares its private application data in `/var/lib/resono-vault`.

4. Create your one-time setup link:

   ```bash
   resono-vault setup
   ```

5. Open the setup link shown in the terminal and follow the guided setup.

Vault initially listens securely on this computer at `https://127.0.0.1:8765`.

### Why Vault creates a security certificate

The installer automatically creates a private local certificate for Vault. This certificate enables HTTPS and encrypts information moving between your browser and Vault, even though Vault is running on your own computer.

The certificate is created and kept on your device. It does not come from a public website and is not shared with ReSono Labs.

Because it is a private certificate, your browser may not recognize it the first time. If prompted, follow Vault's certificate instructions to trust the **ReSono Vault Local CA** on that device. Only install this certificate on devices you own or trust.

### Useful commands

```bash
resono-vault status
resono-vault logs
sudo resono-vault restart
```

Installing a newer Linux package preserves your existing Vault data.

---

## After installation

Vault works on its own over your local network. When you want secure access away from home, connect it through **ReSono Labs Link** or through your own trusted private network, such as Tailscale, WireGuard, or another VPN.

In Link, add a **Custom HTTP/WebSocket service** (**Services → Add service**) with local destination `http://127.0.0.1:8766`. See the Vault Link setup guide for the full steps.

ReSono Labs Link provides the connection back to Vault; it does not replace Vault or move your Vault data into the Link website.
