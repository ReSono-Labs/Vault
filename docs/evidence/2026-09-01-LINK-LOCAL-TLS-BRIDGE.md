# Link Local TLS Bridge Evidence

Date: 2026-09-01  
Status: implemented and live-verified

## Governing requirement

Keep Link and Vault's existing HTTPS listener unchanged. Add a production-package
adapter published only at `http://127.0.0.1:8766` that forwards HTTP and
WebSocket traffic to Vault over verified TLS, preserving Link's forwarded host
and HTTPS scheme headers.

This is explicitly owner-authorized `NEW` package adaptation, not donor code.

## Implemented boundary

- `compose.yml` adds the unprivileged `link_bridge` service.
- `docker/link-bridge/nginx.conf` forwards to `https://vault:8765`.
- The host publication is fixed to `127.0.0.1`; only its host port is
  configurable.
- The bridge mounts the production data volume read-only and trusts only
  `tls/vault-local-ca.crt`.
- Upstream certificate and hostname verification remain enabled.
- HTTP/1.1 upgrade headers and long-lived proxy timeouts support WebSockets.
- The bridge drops all Linux capabilities and runs with `no-new-privileges`.

## Verification

The following checks passed:

```text
docker compose -f compose.yml config --quiet
nginx -t (unprivileged runtime UID with the production CA mounted read-only)
.venv/bin/pytest -q tests/unit/test_link_bridge_package.py \
  tests/unit/test_package_runtime.py \
  tests/unit/test_vault_runtime_local_api_config.py
16 passed
```

Live production-package proof:

```text
GET http://127.0.0.1:8766/health
HTTP/1.1 200 OK
database=ok; schemaReady=true; pgvectorVersion=0.8.6
```

Docker reported `link_bridge` healthy and published only as
`127.0.0.1:8766->8766/tcp`. An initial IP-literal hostname check failed closed;
verification was corrected to the certificate's required `localhost` DNS SAN
without disabling CA or hostname validation.
