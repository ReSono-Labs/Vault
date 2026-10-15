import asyncio
from types import SimpleNamespace as NS

import pytest

from app.vault_runtime.background_agent.sdk_runner import run_agent_turn


def test_shared_runner_streams_original_response_and_delta_without_network(monkeypatch):
    from agents import Runner
    sequence = []
    def streamed(agent,**kwargs):
        assert agent.name=='ReSono Voice Agent' and kwargs['input']=='submitted'
        async def events():
            await kwargs['hooks'].on_llm_start(None,agent,None,[])
            await kwargs['hooks'].on_llm_end(None,agent,NS(response_id='original',output=[]))
            sequence.append('dispatch-boundary')
            yield NS(type='raw_response_event',data=NS(type='response.output_text.delta',delta='Hello'))
            result.is_complete=True
        result = NS(is_complete=False,stream_events=events,run_loop_exception=None,final_output='Hello')
        return result
    monkeypatch.setattr(Runner,'run_streamed',streamed)
    answer = asyncio.run(run_agent_turn(api_key='synthetic',model='gpt-5.6-sol',instructions='test',input_text='submitted',
        base_url=None,reasoning_effort='none',max_turns=2,agent_name='ReSono Voice Agent',
        model_response_sink=lambda response:sequence.append(response.response_id),
        text_delta_sink=lambda text:sequence.append(text),cancel_requested=lambda:False))
    assert answer=='Hello' and sequence==['original','dispatch-boundary','Hello']


def test_required_original_capture_failure_propagates_before_dispatch(monkeypatch):
    from agents import Runner
    dispatched = []
    def streamed(agent,**kwargs):
        async def events():
            await kwargs['hooks'].on_llm_end(None,agent,NS(output=[]))
            dispatched.append(True)
            yield NS(type='unused')
        return NS(is_complete=False,stream_events=events,run_loop_exception=None,final_output='unreachable',
            cancel=lambda **_:None)
    monkeypatch.setattr(Runner,'run_streamed',streamed)
    def failed(_):
        raise ValueError('capture failed')
    with pytest.raises(ValueError,match='capture failed'):
        asyncio.run(run_agent_turn(api_key='synthetic',model='gpt-5.6-sol',instructions='test',input_text='submitted',
            base_url=None,reasoning_effort='none',max_turns=2,agent_name='ReSono Voice Agent',
            model_response_sink=failed,text_delta_sink=lambda _:None))
    assert not dispatched


def test_failed_delta_sink_immediately_cancels_and_drains_sdk_loop(monkeypatch):
    from agents import Runner
    states = []
    def streamed(agent,**kwargs):
        async def events():
            yield NS(type='raw_response_event',data=NS(type='response.output_text.delta',delta='partial'))
            assert states==['immediate']
            states.append('drained')
        return NS(is_complete=False,stream_events=events,run_loop_exception=None,final_output='unreachable',
            cancel=lambda *,mode:states.append(mode))
    monkeypatch.setattr(Runner,'run_streamed',streamed)
    def failed(_):
        raise ValueError('durable delta failed')
    with pytest.raises(ValueError,match='durable delta failed'):
        asyncio.run(run_agent_turn(api_key='synthetic',model='gpt-5.6-sol',instructions='test',input_text='submitted',
            base_url=None,reasoning_effort='none',max_turns=2,agent_name='ReSono Voice Agent',text_delta_sink=failed))
    assert states==['immediate','drained']


def test_shared_runner_gemini_uses_chat_completions_and_original_capture(monkeypatch):
    from agents import Runner
    from agents.models.openai_provider import OpenAIProvider
    original_init=OpenAIProvider.__init__
    protocols=[]
    def init(self,**kwargs):
        protocols.append(kwargs['use_responses'])
        original_init(self,**kwargs)
    monkeypatch.setattr(OpenAIProvider,'__init__',init)
    captured=[]
    def streamed(agent,**kwargs):
        async def events():
            await kwargs['hooks'].on_llm_end(None,agent,NS(response_id='gemini-original',output=[]))
            yield NS(type='raw_response_event',data=NS(type='response.output_text.delta',delta='Hello'))
            result.is_complete=True
        result=NS(is_complete=False,stream_events=events,run_loop_exception=None,final_output='Hello')
        return result
    monkeypatch.setattr(Runner,'run_streamed',streamed)
    answer=asyncio.run(run_agent_turn(api_key='synthetic',model='gemini-test',instructions='test',input_text='submitted',
        base_url='https://generativelanguage.googleapis.com/v1beta/openai/',model_api='chat_completions',
        reasoning_effort='medium',max_turns=2,agent_name='ReSono Voice Agent',
        model_response_sink=lambda response:captured.append(response.response_id)))
    assert protocols==[False] and captured==['gemini-original'] and answer=='Hello'
