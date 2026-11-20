"""Shared test helpers moved out of test modules (TST-01)."""

from threading import Event
from time import monotonic
from types import SimpleNamespace as NS

from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from tests.support.mounted_conversation_runtime import create, wait


def finish_workers(runtime):
    deadline=monotonic()+10
    while monotonic()<deadline:
        with runtime._lock:
            if not runtime._workers:
                return
        Event().wait(.02)
    raise AssertionError("Bounded review worker did not finish")


def configure(m,*,bad_citation=False):
    conversation=create(m)
    runtime=m.app._conversation_runtime
    calls=[]
    def evaluate(**kwargs):
        calls.append(kwargs)
        assert "morning appointments" in kwargs["input_text"]
        return dict(contractVersion=2,summary="Appointment preference captured",candidates=[dict(
            domain="personal",memoryType="preference",stableKey="appointment-time",
            content="User prefers morning appointments",sourceEntryIndexes=[999 if bad_citation else 0],
            sourceAuthority="user_asserted",confidence="high",sensitivity="normal",
            reconciliationIntent="create",shouldStore=True)])
    runtime.memory_learning.voice_learning._reviewer_factory=lambda u,w:OpenAIMemoryReviewer(
        credentials=m.app._voice_provider_credentials,user_id=u,workspace_id=w,executor=evaluate)
    embedded=[]
    class Embedder:
        model_key="text-embedding-3-small"
        def embed(self,text):
            embedded.append(text)
            return [1.]+[0.]*1535
    runtime.memory_learning.voice_learning._embedder_factory=lambda *_:Embedder()
    async def runner(**kwargs):
        kwargs["model_response_sink"](NS(response_id="response",output=[NS(type="message",id="answer",
            role="assistant",content=[NS(type="output_text",text="Understood")])]))
        return "Understood"
    runtime.runner=runner
    result=m.post(f"/conversations/{conversation}/turns",dict(submissionKey="fact",input="I prefer morning appointments",
        expectedHistoryVersion=0),m.headers)
    assert result.status_code==202
    assert wait(m,conversation,result.payload["turnId"])["state"]=="completed"
    finish_workers(runtime)  # Terminal DB state precedes worker slot release.
    return conversation,runtime,calls,embedded
