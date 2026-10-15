import asyncio
import json

from app.vault_runtime.decision_routing.diagnostics import LiveDiagnostics
from app.vault_runtime.decision_routing.selector import DecisionSelector
from app.vault_runtime.live_memory.preparation import ParallelPreparation, WorkerBudget
from app.vault_runtime.live_memory.voicemem_stream import VoiceMemStream
from tests.unit.test_live_memory_component import snapshot, Ports, settle
from tests.unit.test_decisions_selector_boundary import request, Clock, Cancellation, Transport


class Logger:
    def __init__(self):
        self.rows = []
    def info(self, message):
        self.rows.append(json.loads(message))


def test_actual_stream_events_parallel_reconsideration_final_reuse_and_off_privacy():
    async def run():
        logger = Logger()
        workers = WorkerBudget(global_limit=4,user_limits={"user":4})
        preparation = ParallelPreparation(ports=Ports(),workers=workers,diagnostics=LiveDiagnostics(logger=logger))
        stream = VoiceMemStream(preparation,debounce_s=0,max_wait_s=1,meaningful=lambda _: True)
        await stream.feed_partial(snapshot("PRIVATE DRAFT SENTINEL"))
        assert await settle(stream) is not None
        assert await stream.finalize(snapshot("PRIVATE DRAFT SENTINEL",final=True),timeout_s=1) is not None
        stream.invalidate()
        await stream.wait_closed()
        off = VoiceMemStream(preparation,debounce_s=0,max_wait_s=1,meaningful=lambda _: True)
        await off.feed_partial(snapshot("DELETED SECRET"),enabled=False)
        off.invalidate()
        await off.wait_closed()
        await workers.drain()
        events = [r["event"] for r in logger.rows]
        for event in ("revision_accepted","preparation_started","reuse_checked","memory_lookup_complete",
                      "decision_lookup_complete","decision_reconsidered","preparation_ready","final_reused",
                      "stream_invalidated","draft_skipped"):
            assert event in events
        assert events.index("preparation_started") < events.index("preparation_ready") < events.index("final_reused")
        assert any(r.get("reason") == "off" for r in logger.rows)
        serialized = json.dumps(logger.rows)
        for forbidden in ("PRIVATE DRAFT SENTINEL","DELETED SECRET","authority-memory-preference-generation-1","login"):
            assert forbidden not in serialized
        assert all(r["user_id"] != "user" and "input_fingerprint" not in r for r in logger.rows)
    asyncio.run(run())


def test_selector_success_fallback_stale_and_throwing_sink_preserve_actual_result():
    logger = Logger()
    diagnostics = LiveDiagnostics(logger=logger)
    selected = DecisionSelector(transport=Transport(),clock=Clock(),diagnostics=diagnostics).choose(
        request(),deadline=20,cancellation=Cancellation(),is_current=lambda _: True)
    assert selected.definition_id == "decision-invoice"
    assert logger.rows[-1]["reason"] == "selected" and logger.rows[-1]["definition_version"] == 3
    assert logger.rows[-1]["definition_id"] != selected.definition_id
    assert logger.rows[-1]["candidate_kind"] == "learned_rule"
    assert logger.rows[-1]["generation_id"] != request().generation_id
    assert logger.rows[-1]["candidate_count"] == len(request().candidate_set)
    fallback = DecisionSelector(transport=None,clock=Clock(),diagnostics=diagnostics).choose(
        request(),deadline=20,cancellation=Cancellation(),is_current=lambda _: False)
    assert fallback.reason == logger.rows[-1]["reason"] == "stale"
    class Broken:
        def emit(self,*_,**__):
            raise RuntimeError("LOGGER SECRET")
    result = DecisionSelector(transport=None,clock=Clock(),diagnostics=Broken()).choose(
        request(),deadline=20,cancellation=Cancellation(),is_current=lambda _: True)
    assert result.reason == "unavailable"
    raw = json.dumps(logger.rows)
    assert "ABC" not in raw and "invoice 482" not in raw and "Supply" not in raw


def test_diagnostic_unknown_fields_and_logger_failures_do_not_leak():
    logger = Logger()
    diagnostics = LiveDiagnostics(logger=logger)
    diagnostics.emit("arbitrary secret",snapshot(),reason="password")
    diagnostics.emit("preparation_ready",snapshot(),decision_count=-1)
    assert logger.rows == []
    class Broken:
        def info(self,*_):
            raise RuntimeError("secret")
    LiveDiagnostics(logger=Broken()).emit("preparation_ready",snapshot())


def test_changed_final_is_logged_as_rejected_then_fresh_not_reused():
    async def run():
        logger = Logger()
        workers = WorkerBudget(global_limit=4,user_limits={"user":4})
        preparation = ParallelPreparation(ports=Ports(),workers=workers,diagnostics=LiveDiagnostics(logger=logger))
        stream = VoiceMemStream(preparation,debounce_s=0,max_wait_s=1,meaningful=lambda _: True)
        await stream.feed_partial(snapshot("ABC invoice"))
        await settle(stream)
        assert await stream.finalize(snapshot("Sarah contact",revision=2,final=True),timeout_s=1) is not None
        stream.invalidate()
        await stream.wait_closed()
        await workers.drain()
        events = [r["event"] for r in logger.rows]
        assert "final_reused" not in events
        assert events.index("final_preparation_rejected") < events.index("final_researched") < events.index("final_completed")
        assert next(r for r in logger.rows if r["event"] == "final_preparation_rejected")["reason"] == "not_exact"
    asyncio.run(run())
