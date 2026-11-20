# Internet connectivity testing

`scripts/internet_test_env.py` runs a disposable test Vault from source and
publishes it through an authenticated ngrok tunnel. Use it to test Vault from a
phone or another network and to check outbound provider access. It is test
infrastructure only, not a way to host Vault.

## What it sets up

- Vault from source (`python -m app.vault_runtime.local_api`) with data in
  `.runtime/internet-test/vault-data` and its own database,
  `resono_vault_browser_test`, in the test container.
- Vault listens on all interfaces, port 8765, with TLS from a local CA the script
  creates in `.runtime/internet-test/tls`. The certificate covers the LAN address,
  so phones on the same network can use the LAN URL too.
- ngrok forwards to `https://<LAN address>:8765` and verifies Vault's certificate.
  Its edge requires a separate Basic Authentication login.
- PostgreSQL stays on `127.0.0.1:55436` and is never published.
- Vault's own accounts, sessions, CSRF checks, workspace scoping and tool grants
  apply as usual.

## Requirements

Docker, uv, Node.js 22 with npm (run `npm --prefix frontend ci` once), openssl,
and an ngrok agent that is signed in.

## Start, check, stop

```bash
python3 scripts/internet_test_env.py start
python3 scripts/internet_test_env.py check
python3 scripts/internet_test_env.py status
python3 scripts/internet_test_env.py stop
```

`start` starts the test database, builds the web app and starts Vault and ngrok.
It prints:

- the public URL;
- the LAN URL;
- where to find the ingress username and password;
- where to find the setup credential.

All secrets live in `.runtime/internet-test/` with mode 0600, and git ignores them.

On a fresh database, open the public or LAN URL with `#setup=` followed by the
contents of `.runtime/internet-test/setup-credential`. The value stays in the URL
fragment, so it is never sent to the server or to ngrok. After setup the web app
removes it from the URL.

`check` reports these checks: local health, that the public URL rejects anonymous
requests, that it accepts the ingress login, and that a model provider is
reachable over DNS and TLS. It uses no provider key.

`stop` stops only the Vault and ngrok processes this script started. The test
database keeps running; stop it with `python3 scripts/test_env.py stop`.

To start over, see the factory reset in
[LOCAL-TEST-ENVIRONMENT.md](LOCAL-TEST-ENVIRONMENT.md#a-test-vault-for-manual-browser-testing).

## Rules

- Do not remove the edge login or publish the database port.
- Treat the ngrok URL as temporary. It is not a release endpoint.
- Stop the harness when you are done. Vault is reachable on your LAN while it runs.
