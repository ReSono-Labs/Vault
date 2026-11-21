from datetime import UTC, datetime

from app.vault_runtime.background_agent.work_record import failure_kind, turn_origin


class Cursor:
    def __init__(self, row):
        self.row = row

    def execute(self, *_):
        pass

    def fetchone(self):
        return self.row


def _turn(key, text):
    return {"submission_key": key, "input_text": text, "created_at": datetime(2026, 11, 20, tzinfo=UTC)}


def test_each_kind_of_actor_is_told_apart() -> None:
    assert turn_origin(Cursor(_turn("link:abc", "We just did an overhaul")), "t")["how"] == "a message in Link"
    assert turn_origin(Cursor(_turn("6f1e-uuid", "start it now")), "t")["how"] == "a message in web chat"
    voice = turn_origin(Cursor(_turn("link:abc", "[Spoken on a voice call] check the CRM")), "t")
    assert voice["by"] == "owner" and voice["how"] == "a message in voice call"
    coordinator = turn_origin(Cursor(_turn(
        "vault-wake:digest:1", "[Automated message from Vault, not from the user]\n\nBackground work could not finish.")), "t")
    assert coordinator["by"] == "coordinator" and coordinator["wokenBy"].startswith("Background work could not finish")
    assert turn_origin(Cursor(None), "missing") is None and turn_origin(Cursor(None), None) is None


def test_failure_kinds() -> None:
    assert failure_kind("validationerror") == "vault"
    assert failure_kind("approval_denied") == "needs_owner"
    assert failure_kind("RateLimitError") == "temporary"
    assert failure_kind("stalled_outcome_unknown") == "unconfirmed"
    assert failure_kind("agent_incomplete") == "task"
    assert failure_kind(None) is None
