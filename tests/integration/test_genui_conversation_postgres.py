"""Generative UI over the actual mounted Chat runtime; synthetic provider, isolated real DB."""
import json
from types import SimpleNamespace as NS

import psycopg

from tests.integration.test_mounted_voice_decision_review_postgres import mounted  # noqa: F401
from tests.integration.test_mounted_conversation_runtime_postgres import create, submit, wait

TIMELINE = {"layout": "timeline", "title": "Saturday", "fallbackText": "Saturday: cake 17:00, dinner 19:30",
            "items": [{"time": "17:00", "title": "Cake", "state": "done"}, {"time": "19:30", "title": "Dinner"}]}


class Hints:
    def __init__(self, response):
        self.response, self.payloads = response, []

    def __call__(self, principal):
        return self

    def evaluate(self, payload, *, timeout_seconds):
        self.payloads.append(payload)
        return self.response


def hint_answer(choice="timeline", visual=0.9):
    return {"answers": [
        {"type": "choice", "name": "presentation", "choice": choice, "confidence": .8,
         "probabilities": [{"value": choice, "probability": .8}]},
        {"type": "predicate", "name": "visual_helps", "probability": visual}]}


def grant(m):
    m.app._conversation_runtime.authority.ensure_builtin_grants(user_id=m.principal.user_id,
        workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id, workspace_id=m.principal.workspace_id))


def call(kwargs, response_id, call_id, name, arguments):
    raw = json.dumps(arguments)
    kwargs['model_response_sink'](NS(response_id=response_id, output=[
        NS(type='function_call', id='item-'+call_id, call_id=call_id, name=name, arguments=raw)]))
    tool = next(t for t in kwargs['function_tools'] if t.name == name)
    return tool, raw


def finish(kwargs, text='Here is Saturday.'):
    kwargs['model_response_sink'](NS(response_id='final', output=[NS(type='message', id='answer', role='assistant',
        content=[NS(type='output_text', text=text)])]))
    kwargs['text_delta_sink'](text)
    return text


def test_present_ui_streams_validated_card_with_real_provenance_and_history(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    assert runtime.genui_enabled is True
    grant(m)
    hints = Hints(hint_answer())
    runtime.presentation_transport_factory = hints
    seen = {}

    async def runner(**kwargs):
        seen['instructions'] = kwargs['instructions']
        seen['tools'] = [t.name for t in kwargs['function_tools']]
        seen['input'] = json.loads(kwargs['input_text'])
        tool, raw = call(kwargs, 'r1', 'call-contacts', 'contacts_search', {"query": "test"})
        await tool.on_invoke_tool(NS(tool_call_id='call-contacts'), raw)
        tool, raw = call(kwargs, 'r2', 'call-card', 'present_ui', TIMELINE)
        seen['shown'] = json.loads(await tool.on_invoke_tool(NS(tool_call_id='call-card'), raw))
        bad = dict(TIMELINE, layout='html')
        tool, raw = call(kwargs, 'r3', 'call-bad', 'present_ui', bad)
        seen['bad'] = json.loads(await tool.on_invoke_tool(NS(tool_call_id='call-bad'), raw))
        # A dispatch without an original captured proposal fails closed.
        try:
            await tool.on_invoke_tool(NS(tool_call_id='never-proposed'), json.dumps(TIMELINE))
            seen['unlinked'] = 'accepted'
        except Exception:
            seen['unlinked'] = 'rejected'
        return finish(kwargs)

    runtime.runner = runner
    turn = submit(m, conversation)
    status = wait(m, conversation, turn)
    assert status['state'] == 'completed', status
    assert 'present_ui' in seen['tools'] and 'Layouts:\n- timeline:' in seen['instructions']
    assert '- options:' not in seen['instructions'] and 'also available' in seen['instructions']
    assert seen['input']['finalPreparation']['presentation']['layouts'] == ['timeline']
    assert hints.payloads and hints.payloads[0]['input'].find('Find my contacts') > 0
    assert seen['shown']['shown'] is True and seen['bad']['shown'] is False and seen['unlinked'] == 'rejected'

    events = runtime.store.events(m.principal, conversation, turn)
    kinds = [e['kind'] for e in events]
    assert kinds.index('ui_hint') < kinds.index('model_response')
    ui = [e['payload'] for e in events if e['kind'] == 'ui']
    assert len(ui) == 1 and ui[0]['card']['layout'] == 'timeline' and ui[0]['sources'] == ['contacts_search']
    assert ui[0]['cardId'] == seen['shown']['cardId']
    assert not any(e['kind'] == 'tool_status' and e['payload']['name'] == 'present_ui' for e in events)
    with psycopg.connect(m.url) as connection:
        names = [r[0] for r in connection.execute('SELECT tool_name FROM vault_private.vault_voice_tool_invocations')]
    assert names == ['contacts_search']  # Display cards never enter the execution ledger.

    page = m.app.handle(method='GET', target=f'/conversations/{conversation}', headers=m.headers).payload
    assert page['turns'][0]['ui'][0]['card'] == ui[0]['card'] and page['turns'][0]['answer'] == 'Here is Saturday.'
    wire = b''.join(m.app.handle(method='GET', target=f'/conversations/{conversation}/turns/{turn}/events',
                                 headers=m.headers).stream).decode()
    assert '"kind":"ui"' in wire and '"kind":"ui_hint"' in wire


def test_text_likely_hint_trims_guidance_and_failed_hint_uses_full_catalog(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    grant(m)
    seen = []

    async def runner(**kwargs):
        seen.append(kwargs['instructions'])
        return finish(kwargs, 'Hello!')

    runtime.runner = runner
    runtime.presentation_transport_factory = Hints(hint_answer('text', 0.1))
    turn = submit(m, conversation)
    assert wait(m, conversation, turn)['state'] == 'completed'
    assert 'most likely needs a plain-text answer' in seen[0] and 'Layouts:' not in seen[0]
    assert not any(e['kind'] == 'ui_hint' for e in runtime.store.events(m.principal, conversation, turn))

    def broken(principal):
        raise RuntimeError('no api key')
    runtime.presentation_transport_factory = broken
    version = m.app.handle(method='GET', target=f'/conversations/{conversation}', headers=m.headers).payload['historyVersion']
    turn = submit(m, conversation, key='send-two', version=version)
    assert wait(m, conversation, turn)['state'] == 'completed'
    assert all(f'- {key}:' in seen[1] for key in ('timeline', 'options', 'chart'))

    runtime.genui_enabled = False
    version = m.app.handle(method='GET', target=f'/conversations/{conversation}', headers=m.headers).payload['historyVersion']
    turn = submit(m, conversation, key='send-three', version=version)
    assert wait(m, conversation, turn)['state'] == 'completed'
    assert 'present_ui' not in seen[2]
