"""Checkpoint guards bind transport state; domain authority still owns approvals."""
from types import SimpleNamespace
import importlib
import importlib.util

import pytest


def guards():
    name = "app.vault_runtime.background_agent.checkpoints"
    assert importlib.util.find_spec(name) is not None, "SDK checkpoint guards are not implemented"
    return importlib.import_module(name)


def call(arguments='{"card_id":"proof-card","text":"brief"}'):
    return SimpleNamespace(raw_item=SimpleNamespace(name="publish_brief", arguments=arguments, call_id="call-proof"))


def envelope(module):
    return {"version": 1, "provider_key": "openai", "model_id": "proof-model",
            "sdk_version": "0.18.3", "approval_hash": module.approval_fingerprint(call()), "state": {}}


@pytest.mark.parametrize("change", [
    {"provider_key": "xai"}, {"model_id": "another-model"}, {"sdk_version": "0.19.0"}, {"version": 2},
])
def test_checkpoint_rejects_changed_execution_identity(change):
    module = guards()
    saved = envelope(module) | change
    with pytest.raises(ValueError, match="checkpoint"):
        module.validate_sdk_checkpoint(saved, provider_key="openai", model_id="proof-model", sdk_version="0.18.3")


def test_approval_fingerprint_binds_exact_tool_and_arguments():
    approval_fingerprint = guards().approval_fingerprint
    assert approval_fingerprint(call()) == approval_fingerprint(call('{"text":"brief","card_id":"proof-card"}'))
    assert approval_fingerprint(call()) != approval_fingerprint(call('{"card_id":"other","text":"brief"}'))


def test_valid_saved_identity_is_accepted_without_changing_state():
    module = guards()
    saved = envelope(module)
    module.validate_sdk_checkpoint(saved, provider_key="openai", model_id="proof-model", sdk_version="0.18.3")
    assert saved == envelope(module)
