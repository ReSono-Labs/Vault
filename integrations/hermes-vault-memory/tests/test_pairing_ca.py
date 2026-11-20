from __future__ import annotations

import importlib.util
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PAIRING_PATH = Path(__file__).resolve().parents[1] / "src" / "resono_vault_hermes" / "pairing.py"
_SPEC = importlib.util.spec_from_file_location("resono_vault_hermes_pairing", _PAIRING_PATH)
assert _SPEC and _SPEC.loader
_pairing = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_pairing)
refresh_host_ca = _pairing.refresh_host_ca


def _test_pem() -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        pem = Path(tmp) / "ca.crt"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(Path(tmp) / "ca.key"),
                "-out",
                str(pem),
                "-days",
                "1",
                "-subj",
                "/CN=vault-test-ca",
            ],
            check=True,
            capture_output=True,
        )
        return pem.read_bytes()


PEM = _test_pem()


class PairingCaTests(unittest.TestCase):
    def test_refresh_host_ca_writes_verified_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "vault-local-ca.crt"
            context = ssl.create_default_context()
            with mock.patch.object(_pairing, "_get_bytes", return_value=PEM) as get_bytes:
                refreshed = refresh_host_ca("https://127.0.0.1:8765", dest, context)
            self.assertEqual(dest.read_bytes(), PEM)
            self.assertEqual(get_bytes.call_count, 1)
            self.assertIsInstance(refreshed, ssl.SSLContext)

    def test_refresh_host_ca_falls_back_unverified_only_for_ca_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "vault-local-ca.crt"
            context = ssl.create_default_context()
            calls: list[int] = []

            def fake_get(_url: str, ctx: ssl.SSLContext) -> bytes:
                calls.append(ctx.verify_mode)
                if len(calls) == 1:
                    raise ssl.SSLError("certificate verify failed")
                return PEM

            with mock.patch.object(_pairing, "_get_bytes", side_effect=fake_get):
                refresh_host_ca("https://127.0.0.1:8765", dest, context)
            self.assertEqual(dest.read_bytes(), PEM)
            self.assertEqual(len(calls), 2)
            self.assertNotEqual(calls[0], ssl.CERT_NONE)
            self.assertEqual(calls[1], ssl.CERT_NONE)


if __name__ == "__main__":
    unittest.main()
