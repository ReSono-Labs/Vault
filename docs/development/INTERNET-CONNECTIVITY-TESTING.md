# Internet Connectivity Testing

This development-only harness proves that Vault can make outbound internet
requests and accept inbound HTTPS requests without exposing PostgreSQL or
changing the local-only product boundary.

## Boundary

- Vault remains bound to `127.0.0.1:8765`.
- PostgreSQL remains bound to `127.0.0.1:55436`.
- ngrok publishes only the Vault web/API origin through HTTPS.
- The public edge requires separate generated Basic Authentication credentials.
- Vault's own account, session, CSRF, workspace and tool controls remain active.
- This is disposable test infrastructure. It is not Link, Tailscale, production
  routing, hosting, or device deployment.

## Start and verify

Prerequisites are Docker, uv, Node/npm and an authenticated ngrok agent.

```bash
python3 scripts/internet_test_env.py start
python3 scripts/internet_test_env.py check
python3 scripts/internet_test_env.py status
```

`start` brings up the isolated test database, builds Browser Voice, starts the
local Vault runtime and creates an authenticated HTTPS tunnel. It prints the
public URL and paths to generated credentials. Secrets live only under
`.runtime/internet-test/`, are ignored by Git and have owner-only permissions.

For a database with no owner account, construct the initial setup URL by
appending `#setup=` and the exact contents of `.runtime/internet-test/setup-credential`
to the local or public Browser Voice URL. The fragment remains in the browser
and supplies the one-time bootstrap proof; onboarding itself asks only for name
and experience. After successful setup, Browser Voice removes the fragment.

`check` proves local health, rejection of anonymous internet access,
authenticated internet access to Vault, and outbound DNS/TLS provider reach.
No provider API key is used by this check.

## Stop

```bash
python3 scripts/internet_test_env.py stop
```

This stops only the Vault and ngrok processes recorded by this harness. The
isolated database remains running; stop it with `python3 scripts/test_env.py
stop` when finished.

Never publish the database port, remove edge authentication, bind Vault to
`0.0.0.0`, or treat the temporary ngrok URL as a release endpoint.
