from types import SimpleNamespace

import pytest

from app.vault_runtime.decision_learning.chat_source import project_chat
from app.vault_runtime.decision_learning.repository import ReviewConflictError
from app.vault_runtime.decision_learning.reviewer import _validate_input


def source(*, error=False, **changes):
    call = dict(type="function_call", call_id="call", name="lookup", arguments={"person":"Sarah"})
    values = dict(conversation_id="c", segment_id="s", turns=[("t","Find Sarah", "completed","complete",5)],
        events=[("t",1,"context",{"memories":[{"memoryId":"m","content":"Sarah is office manager"}]}),
            ("t",2,"model_response",dict(origin="server_sdk", output=[
                dict(type="reasoning",summary=["Look up the office manager"]),call])),
            ("t",3,"tool_status",dict(state="succeeded")),
            ("t",4,"assistant_final",dict(text="Found Sarah")),
            ("t",5,"terminal",dict(state="completed"))],
        invocations=[("i","t","call","lookup","read","succeeded",{"person":"Sarah"},{"isError":error})],
        definitions=[SimpleNamespace(name="lookup",tool_id="contacts.lookup",effect_class="read",description="Find contacts")])
    values.update(changes)
    return project_chat(**values)


def test_projects_original_links_context_summary_and_answer_without_inventing_success():
    snapshot = source()
    _validate_input(snapshot)
    point, = snapshot.observations
    assert snapshot.coverage == "unknown"
    assert point.final_source_id == "chat-final:t"
    assert point.proposal_source_id.startswith("chat-proposal:")
    assert point.context_source_ids == ("chat-event:t:1",)
    assert point.reasoning_source_ids == ("chat-event:t:2:summary",)
    assert point.answer_source_id == "chat-event:t:4"
    assert point.execution == "completed" and point.request_outcome == "unknown"
    assert not point.feedback_source_ids
    assert source(error=True).observations[0].tool_report == "error"


def test_late_summary_not_attributed_to_an_earlier_call():
    snapshot = source(events=[
        ("t",1,"model_response",dict(origin="server_sdk",output=[dict(type="function_call",call_id="call",name="lookup")])),
        ("t",2,"model_response",dict(origin="server_sdk",output=[dict(type="reasoning",summary=["After the fact"])])),
        ("t",3,"tool_status",dict(state="succeeded")),
        ("t",4,"assistant_final",dict(text="Found Sarah")),("t",5,"terminal",dict(state="completed"))])
    assert not snapshot.observations[0].reasoning_source_ids


@pytest.mark.parametrize("changes", [
    dict(turns=[("t","Find Sarah","running","unknown",5)]),
    dict(turns=[("t","Find Sarah","completed","incomplete",5)]),
    dict(turns=[("t","Find Sarah","completed","complete",6)]),
    dict(invocations=[("i","other","call","lookup","read","succeeded",{}, {})]),
    dict(invocations=[("i","t","missing","lookup","read","succeeded",{}, {})]),
    dict(invocations=[("i","t","call","different","read","succeeded",{}, {})]),
])
def test_unqualified_capture_rejected_before_review(changes):
    with pytest.raises(ReviewConflictError):
        source(**changes)


def test_tool_removal_does_not_assign_a_current_capability_to_history():
    snapshot = source(definitions=[])
    assert snapshot.observations[0].capability_id is None
    assert not snapshot.capabilities


def test_direct_answer_is_a_decision_point_and_empty_history_skips():
    snapshot = source(invocations=[],events=[
        ("t",1,"context",{}),("t",2,"model_response",dict(origin="server_sdk",output=[])),
        ("t",3,"waiting",{}),("t",4,"assistant_final",dict(text="Answer")),
        ("t",5,"terminal",dict(state="completed"))])
    assert snapshot.observations[0].point_id == "chat-turn:t"
    assert source(turns=[],events=[],invocations=[]) is None


def test_unexecuted_original_proposal_is_not_dropped_or_counted_as_success():
    snapshot = source(invocations=[])
    assert snapshot.observations[0].point_id.startswith("chat-point:")
    assert snapshot.observations[0].execution == "not_requested"
    assert snapshot.observations[0].result_source_id is None


def test_complete_requires_actual_history_fingerprint_and_closed_segment():
    from app.vault_runtime.conversation.history_projection import history_fingerprint
    context = dict(captureVersion=2,historyTurnIds=["t"],suppliedTools=[],
        historyFingerprint=history_fingerprint((dict(turnId="t",input="Find Sarah",state="running",
            answer=None,originalSources=[],toolResults=[]),)))
    events = [("t",1,"context",context),
        ("t",2,"model_response",dict(origin="server_sdk",output=[])),
        ("t",3,"waiting",{}),("t",4,"assistant_final",dict(text="Answer")),
        ("t",5,"terminal",dict(state="completed"))]
    assert source(closed=True,events=events,invocations=[]).coverage == "complete"
    assert source(closed=False,events=events,invocations=[]).coverage == "unknown"
    context["historyFingerprint"] = "0"*64
    assert source(closed=True,events=events,invocations=[]).coverage == "unknown"


def test_segment_context_requires_exact_segment_and_original_completed_summary():
    from app.vault_runtime.conversation.history_projection import history_fingerprint
    handoff=dict(segmentId='prior',sourceFingerprint='a'*64,reviewerContractVersion=2,text='Earlier context')
    context=dict(captureVersion=3,historySegmentId='s',previousSummary=handoff,historyTurnIds=['t'],suppliedTools=[],
        historyFingerprint=history_fingerprint((dict(turnId='t',input='Find Sarah',state='running',
            answer=None,originalSources=[],toolResults=[]),)))
    events=[('t',1,'context',context),('t',2,'model_response',dict(origin='server_sdk',output=[])),
        ('t',3,'waiting',{}),('t',4,'assistant_final',dict(text='Answer')),('t',5,'terminal',dict(state='completed'))]
    values=dict(closed=True,events=events,invocations=[],turns=[('t','Find Sarah','completed','complete',5,1,'s')])
    assert source(**values,summary_contexts={'prior':dict(handoff)}).coverage=='complete'
    assert source(**values,summary_contexts={}).coverage=='unknown'
    original=dict(handoff)
    context['previousSummary']=dict(handoff,text='Fabricated success')
    assert source(**values,summary_contexts={'prior':original}).coverage=='unknown'
    context['previousSummary']=None
    context['historySegmentId']='different'
    assert source(**values,summary_contexts={}).coverage=='unknown'
    context['historySegmentId']='s'
    del context['previousSummary']
    assert source(**values,summary_contexts={}).coverage=='unknown'


def test_voice_and_chat_share_unchanged_bounded_summary_formatter():
    from app.vault_runtime.voice.context import previous_summary_context
    rendered=previous_summary_context('x'*5000)
    assert rendered.endswith('x'*4096) and not rendered.endswith('x'*4097)
    assert 'untrusted recalled context' in rendered
