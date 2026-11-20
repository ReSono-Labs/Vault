from types import SimpleNamespace as NS

from app.vault_runtime.local_api.app import VaultLocalApiApp


class _Identity:
    def authenticate(self, session_token):
        assert session_token == "session"
        return NS(user_id="user-1", workspace_id="workspace-1", session_id="session-1")

    def require_csrf(self, **_kwargs):
        return None


def _app(conversation_runtime):
    return VaultLocalApiApp(store=NS(health=lambda: {"status": "ok"}), token="secret",
                            identity_service=_Identity(), conversation_runtime=conversation_runtime)


def _health(app):
    return app.handle(method="GET", target="/background/health",
                      headers={"Authorization": "Bearer session"}, body=b"")


def test_app_reads_health_from_and_stops_the_durable_worker():
    events = []

    class Jobs:
        def stop(self, **_):
            events.append("durable-stop")

        def health(self):
            return {"state": "degraded"}

    runtime = NS(background_coordinator=NS(jobs=Jobs()), close=lambda: events.append("runtime-close"))
    app = _app(runtime)
    response = _health(app)
    assert response.status_code == 200 and response.payload == {"durable": {"state": "degraded"}}
    app.close()
    assert events == ["runtime-close", "durable-stop"]


def test_health_without_coordination_reports_disabled():
    app = _app(NS(background_coordinator=None, close=lambda: None))
    assert _health(app).payload == {"durable": {"state": "disabled"}}
    app.close()


def test_coordination_flags_default_false():
    from app.vault_runtime.local_api.config import VaultLocalApiConfig
    config=VaultLocalApiConfig(host='127.0.0.1',port=8765,token='test',data_root='/unused',
        storage_status_file='/unused',storage_mount_point='/unused')
    assert config.background_coordination_enabled is False
    assert config.owner_approvals_enabled is False


def test_worker_failure_is_visible_and_start_does_not_claim_success():
    from app.vault_runtime.background_agent.jobs import BackgroundJobs
    import pytest
    jobs=BackgroundJobs(database_url='dbname=unused',executor=None)
    async def failed():
        raise RuntimeError('fixture startup failure')
    jobs._serve=failed
    with pytest.raises(RuntimeError,match='startup failed'):
        jobs.start()
    assert jobs.health()=={'state':'degraded'}
    jobs.stop()


def test_nonfinite_elapsed_time_cannot_poison_saved_budget():
    from app.vault_runtime.background_agent.jobs import BackgroundJobs
    import pytest
    jobs=BackgroundJobs(database_url='dbname=unused',executor=None)
    for value in (float('nan'),float('inf'),-1):
        with pytest.raises(ValueError): jobs.debit(None,active_seconds=value)
