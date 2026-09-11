from __future__ import annotations

from pathlib import Path

from cryptography import x509

from app.vault_runtime import package_runtime


def test_package_initialization_is_idempotent_and_creates_owned_secrets(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(package_runtime, "DATA_ROOT", tmp_path)
    monkeypatch.setenv("RESONO_VAULT_TLS_HOSTS", "localhost,127.0.0.1,192.168.1.50")

    package_runtime.initialize()
    setup = (tmp_path / "config/setup-credential").read_text(encoding="utf-8")
    password = (tmp_path / "postgres-password").read_text(encoding="utf-8")
    package_runtime.initialize()

    assert (tmp_path / "config/setup-credential").read_text(encoding="utf-8") == setup
    assert (tmp_path / "postgres-password").read_text(encoding="utf-8") == password
    assert (tmp_path / "config/database-url").read_text().startswith(
        "postgresql://vault_runtime:"
    )
    assert (tmp_path / "config/local-api-token").stat().st_mode & 0o777 == 0o600
    certificate = x509.load_pem_x509_certificate((tmp_path / "tls/vault.crt").read_bytes())
    alternatives = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "localhost" in alternatives.get_values_for_type(x509.DNSName)
    assert "192.168.1.50" in [str(value) for value in alternatives.get_values_for_type(x509.IPAddress)]
