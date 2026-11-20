"""Shared test helpers moved out of test modules (TST-01)."""

import json
from types import SimpleNamespace as NS


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
