"""Idempotent initialization and serving entrypoint for the Vault package image."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import ipaddress
import os
from pathlib import Path
import secrets
import stat
import sys
from urllib import request
from urllib.parse import quote
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_LOG = logging.getLogger(__name__)


DATA_ROOT = Path(os.environ.get("RESONO_VAULT_DATA_ROOT", "/var/lib/resono-vault"))


def _write_once(path: Path, value: str, *, mode: int = 0o600) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip()
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(value + "\n")
    path.chmod(mode)
    return value


def initialize() -> None:
    for relative in ("config", "keys", "private/workspaces", "extensions", "backups", "tls"):
        path = DATA_ROOT / relative
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
    password = _write_once(DATA_ROOT / "postgres-password", secrets.token_urlsafe(48), mode=0o644)
    host = os.environ.get("RESONO_VAULT_PACKAGE_DATABASE_HOST", "postgres")
    name = os.environ.get("RESONO_VAULT_PACKAGE_DATABASE_NAME", "vault")
    user = os.environ.get("RESONO_VAULT_PACKAGE_DATABASE_USER", "vault_runtime")
    database_url = f"postgresql://{quote(user)}:{quote(password)}@{host}:5432/{quote(name)}"
    _write_once(DATA_ROOT / "config/database-url", database_url)
    _write_once(DATA_ROOT / "config/local-api-token", secrets.token_urlsafe(48))
    setup = _write_once(DATA_ROOT / "config/setup-credential", secrets.token_urlsafe(32))
    _write_once(DATA_ROOT / "config/setup-credential-hash", sha256(setup.encode()).hexdigest())
    _write_once(DATA_ROOT / "config/session-capability-secret", secrets.token_urlsafe(48))
    _ensure_tls()
    if os.geteuid() == 0:
        uid, gid = _runtime_owner()
        for root, directories, files in os.walk(DATA_ROOT):
            os.chown(root, uid, gid)
            for name in directories:
                os.chown(Path(root) / name, uid, gid)
            for name in files:
                os.chown(Path(root) / name, uid, gid)
    print("Vault package initialization is complete.")


def _runtime_owner() -> tuple[int, int]:
    """The account the vault service runs as. On Linux the installer sets it to the
    installing user so files Vault writes in their folders belong to them."""
    def value(name: str) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            return 10001
        if not raw.isdigit() or int(raw) == 0:
            raise SystemExit(f"{name} must be a non-root numeric id.")
        return int(raw)
    return value("RESONO_VAULT_RUNTIME_UID"), value("RESONO_VAULT_RUNTIME_GID")


def _ensure_tls() -> None:
    certificate_path, key_path = DATA_ROOT / "tls/vault.crt", DATA_ROOT / "tls/vault.key"
    ca_path, ca_key_path = DATA_ROOT / "tls/vault-local-ca.crt", DATA_ROOT / "tls/vault-local-ca.key"
    requested = _requested_tls_names()
    if certificate_path.exists() and key_path.exists() and ca_path.exists() and ca_key_path.exists():
        existing = x509.load_pem_x509_certificate(certificate_path.read_bytes())
        existing_ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        alternatives = existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        observed = {str(value) for value in alternatives.get_values_for_type(x509.DNSName)}
        observed.update(str(value) for value in alternatives.get_values_for_type(x509.IPAddress))
        if (
            requested.issubset(observed)
            and _has_extension(existing_ca, x509.SubjectKeyIdentifier)
            and _has_extension(existing_ca, x509.KeyUsage)
            and _has_extension(existing, x509.AuthorityKeyIdentifier)
            and _has_extension(existing, x509.KeyUsage)
        ):
            return
    if ca_path.exists() and ca_key_path.exists():
        ca = x509.load_pem_x509_certificate(ca_path.read_bytes())
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        if not (
            _has_extension(ca, x509.SubjectKeyIdentifier)
            and _has_extension(ca, x509.KeyUsage)
        ):
            ca, ca_key = _new_local_ca()
    else:
        ca, ca_key = _new_local_ca()
    now = datetime.now(UTC)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    alternative_names: list[x509.GeneralName] = []
    for value in sorted(requested):
        try:
            alternative_names.append(x509.IPAddress(ipaddress.ip_address(value)))
        except ValueError:
            alternative_names.append(x509.DNSName(value))
    server_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ReSono Vault")])
    certificate = (
        x509.CertificateBuilder().subject_name(server_subject).issuer_name(ca.subject)
        .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alternative_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=None, decipher_only=None,
        ), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_key_path.write_bytes(ca_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(server_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    for path in (ca_key_path, key_path):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    for path in (ca_path, certificate_path):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def _has_extension(certificate: x509.Certificate, extension_type: type) -> bool:
    try:
        certificate.extensions.get_extension_for_class(extension_type)
        return True
    except x509.ExtensionNotFound:
        return False


def _new_local_ca():
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ReSono Vault Local CA")])
    now = datetime.now(UTC)
    ca = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=None, decipher_only=None,
        ), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return ca, ca_key


def _requested_tls_names() -> set[str]:
    values = {
        item.strip() for item in os.environ.get(
            "RESONO_VAULT_TLS_HOSTS", "localhost,127.0.0.1",
        ).split(",") if item.strip()
    }
    if not values:
        raise RuntimeError("RESONO_VAULT_TLS_HOSTS must contain at least one host.")
    return values


def serve() -> None:
    initialize()
    from app.vault_runtime.composition import build_local_app
    from app.vault_runtime.local_api.config import VaultLocalApiConfig
    from app.vault_runtime.local_api.server import serve as serve_api

    config = VaultLocalApiConfig.from_env()
    from contextlib import ExitStack
    from app.vault_runtime.memory.local_embeddings import packaged_runtime
    with ExitStack() as runtimes:
        if os.environ.get("RESONO_VAULT_LOCAL_EMBEDDINGS") == "1":
            runtimes.enter_context(packaged_runtime())
        serve_api(config, build_local_app(config))


def healthcheck() -> None:
    context = ssl.create_default_context(cafile=str(DATA_ROOT / "tls/vault-local-ca.crt"))
    with request.urlopen("https://127.0.0.1:8765/health", timeout=3, context=context) as response:
        if response.status != 200:
            raise SystemExit(1)


def show_setup() -> None:
    path = DATA_ROOT / "config/setup-credential"
    if not path.exists():
        raise SystemExit("Initial setup has already been consumed.")
    print(path.read_text(encoding="utf-8").strip())


def reconcile_restore(database_url: str | None = None) -> dict[str, int]:
    """Reconcile background coordination state after backup restore so routines start paused
    and no restored pending action or stale in-flight job auto-executes."""
    import psycopg
    from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
    from app.vault_runtime.background_agent.routines import BackgroundRoutines

    effective_url = database_url or (DATA_ROOT / "config/database-url").read_text(encoding="utf-8").strip()
    now = datetime.now(UTC)
    paused_routines = 0
    expired_actions = 0
    reconciled_work = 0

    with psycopg.connect(effective_url, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('vault_private.vault_background_work')")
            if cursor.fetchone()[0] is None:
                return {"pausedRoutines": 0, "expiredActions": 0, "reconciledWork": 0}
            cursor.execute(
                """SELECT DISTINCT user_id, workspace_id FROM (
                     SELECT user_id, workspace_id FROM vault_private.vault_background_routines
                     UNION
                     SELECT user_id, workspace_id FROM vault_private.vault_background_work
                   ) scopes"""
            )
            scopes = [OwnerScope(str(r[0]), str(r[1])) for r in cursor.fetchall()]

            cursor.execute(
                """UPDATE vault_private.vault_background_actions
                   SET state='expired', updated_at=%s
                   WHERE state IN ('pending', 'approved')""",
                (now,),
            )
            expired_actions = cursor.rowcount

            cursor.execute(
                """UPDATE vault_private.vault_background_work
                   SET state=CASE WHEN state='running' THEN 'unknown' ELSE 'cancelled' END,
                       updated_at=%s
                   WHERE state IN ('proposed', 'ready', 'queued', 'running', 'waiting_approval', 'waiting_input')""",
                (now,),
            )
            reconciled_work = cursor.rowcount

            cursor.execute(
                """UPDATE vault_private.vault_background_runs
                   SET state=CASE WHEN state IN ('running','reviewing','repairing') THEN 'failed' ELSE 'cancelled' END,
                       cancellation_requested=true,
                       checkpoint_json=NULL,
                       failure_code=COALESCE(failure_code, 'restored_from_backup'),
                       updated_at=%s
                   WHERE state NOT IN ('completed', 'failed', 'cancelled') OR checkpoint_json IS NOT NULL""",
                (now,),
            )
            cursor.execute("SELECT to_regclass('vault_background_queue.procrastinate_jobs')")
            if cursor.fetchone()[0] is not None:
                cursor.execute(
                    """UPDATE vault_background_queue.procrastinate_jobs
                       SET status='cancelled'
                       WHERE status IN ('todo', 'doing')"""
                )

    routines = BackgroundRoutines(database_url=effective_url)
    for scope in scopes:
        try:
            routines.reconcile_after_restore(scope, now=now)
            paused_routines += 1
        except Exception as exc:
            _LOG.warning("restore_routine_reconcile_failed user_id=%s workspace_id=%s error=%s", scope.user_id, scope.workspace_id, type(exc).__name__)
    return {
        "pausedRoutines": paused_routines,
        "expiredActions": expired_actions,
        "reconciledWork": reconciled_work,
    }


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    commands = {
        "initialize": initialize,
        "serve": serve,
        "healthcheck": healthcheck,
        "show-setup": show_setup,
        "reconcile-restore": reconcile_restore,
    }
    if command not in commands:
        raise SystemExit(f"Unsupported package command: {command}")
    commands[command]()


if __name__ == "__main__":
    main()
