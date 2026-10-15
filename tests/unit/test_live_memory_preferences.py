import pytest

from app.vault_runtime.live_memory.preferences import LiveMemoryPreferenceRepository
from app.vault_runtime.local_identity.authority import has_current_session_scope


@pytest.mark.parametrize("enabled,epoch", [(1, 0), ("true", 0), (None, 0),
                                          (True, True), (False, -1), (False, "0")])
def test_invalid_set_does_not_connect(enabled, epoch):
    def forbidden(*args):
        pytest.fail("Invalid preference must not connect")
    repository = LiveMemoryPreferenceRepository(database_url="unused", connector=forbidden)
    with pytest.raises(ValueError):
        repository.set(object(), enabled=enabled, expected_epoch=epoch)


@pytest.mark.parametrize("lock", [True, False])
@pytest.mark.parametrize("authorized", [True, False])
def test_extracted_authority_preserves_predicate_and_optional_locks(lock, authorized):
    class Cursor:
        def execute(self, sql, params):
            self.sql, self.params = sql, params
        def fetchone(self):
            return (1,) if authorized else None
    cursor = Cursor()
    assert has_current_session_scope(cursor, user_id="u", workspace_id="w",
                                    local_session_id="s", lock=lock) is authorized
    assert cursor.params == ("w", "s", "u", "w")
    for clause in ("s.expires_at>now()", "s.active_workspace_id=%s", "s.status='active'",
                   "u.status='active'", "m.status='active'", "w.status='active'"):
        assert clause in cursor.sql
    assert ("FOR SHARE OF s,u,m,w" in cursor.sql) is lock
