"""Task 0 dependency proofs; fake model, real SDK, independent Python processes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

PROBE = Path(__file__).parents[1] / "support" / "background_sdk_proof.py"


def run_probe(mode, directory, choice="allow_once", *, success=True, provider_key="openai"):
    result = subprocess.run(
        [sys.executable, str(PROBE), mode, str(directory), choice],
        capture_output=True, text=True, timeout=20,
        env={**os.environ, "OPENAI_API_KEY": "credential-sentinel-must-not-be-saved", "VAULT_PROOF_PROVIDER": provider_key},
    )
    if success:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0, "An invalid saved action resumed successfully"
    return result.stderr


@pytest.mark.parametrize("choice,expected_effects", [("allow_once", 1), ("deny", 0)])
@pytest.mark.parametrize("provider_key", ["openai", "xai"])
def test_serialized_approval_resumes_after_process_restart(tmp_path, choice, expected_effects, provider_key):
    prepared = run_probe("prepare", tmp_path, provider_key=provider_key)
    assert prepared == {"waiting": True, "effects": False}
    saved = (tmp_path / "state.json").read_text()
    assert "credential-sentinel-must-not-be-saved" not in saved
    assert "proof-card" in saved
    resumed = run_probe("resume", tmp_path, choice, provider_key=provider_key)
    assert resumed == {"output": "finished", "waiting": False}
    effects_path = tmp_path / "effects.jsonl"
    effects = effects_path.read_text().splitlines() if effects_path.exists() else []
    assert len(effects) == expected_effects
    if effects:
        assert json.loads(effects[0]) == {"card_id": "proof-card", "text": "brief"}


@pytest.mark.parametrize("field,value,error", [
    ("model_id", "changed-model", "checkpoint execution identity changed"),
    ("approval_hash", "0" * 64, "approval request changed"),
])
def test_changed_checkpoint_cannot_execute_the_saved_action(tmp_path, field, value, error):
    run_probe("prepare", tmp_path)
    path = tmp_path / "state.json"
    saved = json.loads(path.read_text())
    saved[field] = value
    path.write_text(json.dumps(saved))
    assert error in run_probe("resume", tmp_path, success=False)
    assert not (tmp_path / "effects.jsonl").exists()
