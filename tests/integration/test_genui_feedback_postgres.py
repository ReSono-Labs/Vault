"""Presentation feedback, previews, preference application, tuner and export over the mounted runtime."""
import json
from time import monotonic, sleep
from types import SimpleNamespace as NS

import psycopg

from tests.integration.test_mounted_voice_decision_review_postgres import mounted  # noqa: F401
from tests.integration.test_mounted_conversation_runtime_postgres import create, wait
from tests.integration.test_genui_conversation_postgres import grant, finish

HEADLINES = {"layout": "headlines", "title": "Top AI news", "fallbackText": "Two stories",
             "items": [{"title": "Model A ships", "source": "Verge", "url": "https://theverge.com/a"},
                       {"title": "Lab B raises", "source": "FT"}]}
TABLE = {"layout": "table", "fallbackText": "Two stories", "columns": ["Story", "Source"],
         "rows": [["Model A ships", "Verge"], ["Lab B raises", "FT"]]}


class Embedder:
    """Deterministic local stand-in: news requests point one way, others another."""
    def __call__(self, user_id, workspace_id):
        return self

    def embed_query(self, text):
        return [1.0, 0.05, 0.0] if "news" in text.lower() else [0.0, 0.1, 1.0]


def send(m, conversation, text, key):
    version = m.app.handle(method='GET', target=f'/conversations/{conversation}', headers=m.headers).payload['historyVersion']
    response = m.post(f'/conversations/{conversation}/turns',
        {'submissionKey': key, 'input': text, 'expectedHistoryVersion': version}, m.headers)
    assert response.status_code == 202, response.payload
    turn = response.payload['turnId']
    assert wait(m, conversation, turn)['state'] == 'completed'
    return turn


def test_feedback_previews_choice_preference_tuner_and_export(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    store = runtime.genui_feedback
    assert store is not None
    store.embedder_factory = Embedder()
    runtime.presentation_transport_factory = None  # No Decisions: learned preferences alone must work.
    grant(m)
    calls = {"previews": 0, "tuner": 0, "instructions": []}

    async def runner(**kwargs):
        name = kwargs['agent_name']
        if name == 'Vault Presentation Previews':
            calls['previews'] += 1
            assert 'never add, guess' in kwargs['instructions']
            tool = kwargs['function_tools'][0]
            for spec in (HEADLINES, TABLE, dict(HEADLINES), {"layout": "html", "fallbackText": "x"}):
                await tool.on_invoke_tool(NS(tool_call_id='p'), json.dumps(spec))
            return 'done'
        if name == 'Vault Presentation Tuner':
            calls['tuner'] += 1
            return kwargs['output_type'](weights={"headlines": 5.0}, guidance={"headlines": "Use for news lists."},
                                         summary="I'll show news as headlines from now on.")
        calls['instructions'].append(kwargs['instructions'])
        return finish(kwargs, 'Here are the stories: Model A ships (Verge); Lab B raises (FT).')

    runtime.runner = runner
    base = f'/conversations/{conversation}/turns'
    turns = []
    for index in range(5):
        turn = send(m, conversation, f'Top AI news today #{index}', f'news-{index}')
        turns.append(turn)
        down = m.post(f'{base}/{turn}/feedback', {'verdict': 'down'}, m.headers)
        assert down.status_code == 200 and down.payload['verdict'] == 'down' and down.payload['shown'] == ['text']
        alternatives = m.post(f'{base}/{turn}/alternatives', {}, m.headers)
        assert alternatives.status_code == 200, alternatives.payload
        layouts = [p['layout'] for p in alternatives.payload['previews']]
        assert layouts == ['headlines', 'table']  # Duplicate and invalid previews were dropped.
        assert m.post(f'{base}/{turn}/alternatives', {}, m.headers).payload['previews'] == alternatives.payload['previews']
        bad = m.post(f'{base}/{turn}/choice', {'layout': 'chart'}, m.headers)
        assert bad.status_code == 400  # Only shown previews can be chosen.
        chosen = m.post(f'{base}/{turn}/choice', {'layout': 'headlines'}, m.headers)
        assert chosen.status_code == 200 and chosen.payload['chosenLayout'] == 'headlines'
    assert calls['previews'] == 5  # Cached per answer.

    # Three agreeing neighbours: the next news request gets the headlines preference without Decisions.
    turn = send(m, conversation, 'Any AI news this morning?', 'news-next')
    context = next(e for e in runtime.store.events(m.principal, conversation, turn) if e['kind'] == 'context')
    presentation = context['payload']['finalPreparation']['presentation']
    assert presentation['preferred'] == 'headlines' and presentation['source'] == 'preference'
    assert 'explicitly chosen the headlines layout' in calls['instructions'][-1]
    other = send(m, conversation, 'How tall is Everest?', 'other')
    assert 'explicitly chosen' not in calls['instructions'][-1]
    del other

    # Tuner: 5 events, 100% headlines replacing text -> one bounded, versioned change with a notice.
    deadline = monotonic() + 10
    while monotonic() < deadline and store.config(m.principal)['version'] == 0:
        sleep(.1)
    config = m.app.handle(method='GET', target='/conversations/genui/presentation', headers=m.headers).payload
    assert config['version'] == 1 and config['noticePending'] is True
    assert config['config']['weights']['headlines'] == 2.0  # Model asked for 5.0; bounded.
    assert config['notice']['summary'].startswith("I'll") and config['notice']['example']['layout'] == 'headlines'
    assert calls['tuner'] >= 1
    sleep(.3)
    assert store.config(m.principal)['version'] == 1  # Pending notice blocks further changes.
    undo = m.post('/conversations/genui/presentation/undo', {'version': 1}, m.headers)
    assert undo.status_code == 200 and undo.payload['version'] == 0
    assert m.post('/conversations/genui/presentation/keep', {'version': 1}, m.headers).status_code == 404

    exported = m.app.handle(method='GET', target='/conversations/genui/feedback/export', headers=m.headers).payload
    assert exported['format'] == 'resono-vault-genui-feedback' and exported['includesRequestText'] is False
    assert len(exported['items']) == 5 and 'request' not in json.dumps(exported['items'])
    assert exported['items'][0]['chosenLayout'] == 'headlines' and exported['items'][0]['previewLayouts'] == ['headlines', 'table']
    with_text = m.app.handle(method='GET', target='/conversations/genui/feedback/export?includeText=1', headers=m.headers).payload
    assert with_text['items'][0]['request'].startswith('Top AI news')
    assert m.app.handle(method='GET', target='/conversations/genui/feedback/export?includeText=yes',
                        headers=m.headers).status_code == 400
    assert m.app.handle(method='GET', target='/conversations/genui/presentation', headers={}).status_code == 403
    assert m.post('/conversations/genui/presentation/reset', {}, {'Cookie': m.headers['Cookie']}).status_code == 403

    reset = m.post('/conversations/genui/presentation/reset', {}, m.headers)
    assert reset.status_code == 200 and reset.payload['removedFeedback'] == 5 and reset.payload['version'] == 0
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_genui_feedback').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM vault_private.vault_genui_presentation_config').fetchone()[0] == 0
        names = {r[0] for r in connection.execute('SELECT tool_name FROM vault_private.vault_voice_tool_invocations')}
    assert not names & {'present_ui'}
