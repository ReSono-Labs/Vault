"""Native Link tools over the existing paired Companion connection.

The host polls once-only calls; Vault never receives the Link tools credential.
"""
from __future__ import annotations

import json
import re
from threading import Condition
from time import monotonic
from uuid import uuid4

from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationResult

_READS = frozenset({'workspace_status', 'card_preflight', 'card_model', 'check',
                   'agent_network_peers', 'agent_network_conversations'})
# Call cards (Link, 2026-11-16): during a live voice call, a chat card goes to the owner's
# phone screen. Only the Voice runtime adds the call's session id; Link accepts it only for
# the call it is relaying right now, so Vault Chat keeps chat cards as they are.
_CALL_CARD_TOOLS = frozenset({'chat_card_publish'})
# Link's card guide (its link-cards skill), the same for Vault Chat and Vault Voice.
_CARD_TOOLS = frozenset({'card_preflight', 'card_publish', 'chat_card_publish', 'chat_card_update'})
# Which publish tool, said first (the same for Vault Chat and Vault Voice): the model reads the
# start of a description, and Link's own text only names the surface later.
_CARD_LEAD = {
    'card_publish': 'HOME SCREEN ONLY (not the conversation; to show a card now use link_chat_card_publish). ',
    'chat_card_publish': ('SHOW A CARD IN THE CONVERSATION NOW, in a chat or a call (not the Home screen).'
                          ' No ids needed: leave operation_ref and turn_token out; Vault fills them in. '),
}
_CARD_GUIDE = (' Before building a card: call link_workspace_status once and build only from the'
               ' components in its catalog (each has "id" and "component", the root is a Card); then'
               ' check it with link_card_preflight and fix what it reports before publishing.')


def _voice_call(context):
    """The tool runs inside a live Voice call (never for Chat, whose context cannot carry one)."""
    from app.vault_runtime.system_agents.inventory import AgentKind
    return getattr(context, 'agent', None) == AgentKind.VOICE and bool(getattr(context, 'voice_session_id', None))


class CompanionLinkTools:
    def __init__(self, *, catalog, authority, pairing, timeout=45):
        self.catalog, self.authority, self.pairing = catalog, authority, pairing
        self.timeout = timeout
        self.condition = Condition()
        self.calls = {}
        self.session = None
        self.seen = 0.0
        self.owner = None
        self.names = set()

    def _current(self, session):
        return bool(session and self.pairing() == session)

    def status(self):
        ready = bool(self._current(self.session) and monotonic() - self.seen < 15)
        return {'ready': ready, 'tools': len(self.names) if ready else 0}

    def available(self, user, workspace):
        return bool(self.owner == (user, workspace) and self._current(self.session)
                    and monotonic() - self.seen < 15)

    def publish(self, principal, tools):
        if not self._current(principal.session_id):
            raise ValueError('Link Companion is not paired')
        if not isinstance(tools, list) or len(tools) > 64:
            raise ValueError('Invalid Link tool list')
        definitions = []
        names = set()
        for tool in tools:
            name = tool.get('name')
            if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', name) or name in names:
                raise ValueError('Invalid Link tool name')
            names.add(name)
            schema = tool.get('inputSchema')
            if not isinstance(schema, dict):
                raise ValueError('Invalid Link tool schema')
            definitions.append(ToolDefinition(
                tool_id=f'builtin.link.{name}.v1', name=f'link_{name}',
                description='Link: ' + _CARD_LEAD.get(name, '') + str(tool.get('description') or name)[:2000]
                            + (_CARD_GUIDE if name in _CARD_TOOLS else ''),
                input_schema=schema, effect_class='read' if name in _READS else 'delete' if name in {'card_archive', 'location_archive'} else 'write',
                handler=lambda context, arguments, n=name: self.invoke(n, arguments, context),
                scope_user_id=principal.user_id, scope_workspace_id=principal.workspace_id,
                availability=self.available,
            ))
        self.catalog.replace_capability_source('builtin.link-companion', tuple(definitions))
        self.authority.ensure_builtin_grants(user_id=principal.user_id, workspace_id=principal.workspace_id,
                                             definitions=tuple(definitions))
        with self.condition:
            if self.session != principal.session_id:
                self.calls.clear()
            self.session = principal.session_id
            self.owner = (principal.user_id, principal.workspace_id)
            self.names = names
            self.seen = monotonic()
            self.condition.notify_all()
        return {'ready': True, 'tools': len(definitions)}

    def invoke(self, name, arguments, context):
        if not self.available(context.user_id, context.workspace_id) or name not in self.names:
            return ToolInvocationResult('Link tools unavailable: Companion is unpaired or offline.', is_error=True)
        if name in _CALL_CARD_TOOLS and _voice_call(context):
            arguments = {**arguments, 'call': context.voice_session_id}
        if len(json.dumps(arguments).encode()) > 65536:
            return ToolInvocationResult('Link tool arguments exceed the limit.', is_error=True)
        call_id = str(uuid4())
        with self.condition:
            if len(self.calls) >= 32:
                return ToolInvocationResult('Link tools are busy.', is_error=True)
            call = {'id': call_id, 'name': name, 'arguments': arguments, 'session': self.session,
                    'claimed': False, 'result': None}
            self.calls[call_id] = call
            end = monotonic() + self.timeout
            self.condition.notify_all()
            try:
                while call['result'] is None and monotonic() < end and self._current(call['session']):
                    self.condition.wait(min(0.25, max(0, end-monotonic())))
                result = call['result']
                if result is None or not self._current(call['session']):
                    return ToolInvocationResult('Link tool outcome unknown or Companion unpaired; not retried.', is_error=True)
                text = '\n'.join(str(i.get('text', '')) for i in result.get('content', [])
                                 if isinstance(i, dict) and i.get('type') == 'text')
                return ToolInvocationResult(text or json.dumps(result), structured_content=result,
                                            is_error=result.get('isError') is True)
            finally:
                self.calls.pop(call_id, None)

    def poll(self, principal, wait=1):
        if principal.session_id != self.session or not self._current(principal.session_id):
            raise ValueError('Link Companion binding changed')
        with self.condition:
            self.seen = monotonic()
            until = monotonic() + min(max(wait, 0), 2)
            while not any(not c['claimed'] for c in self.calls.values()) and monotonic() < until:
                self.condition.wait(max(0, until-monotonic()))
            if not self._current(principal.session_id):
                raise ValueError('Link Companion unpaired')
            out = []
            for call in self.calls.values():
                if not call['claimed'] and call['session'] == principal.session_id:
                    call['claimed'] = True
                    out.append({k: call[k] for k in ('id', 'name', 'arguments')})
            return {'calls': out}

    def complete(self, principal, call_id, result):
        if not isinstance(result, dict) or len(json.dumps(result).encode()) > 4*1024*1024:
            raise ValueError('Invalid Link result')
        with self.condition:
            call = self.calls.get(call_id)
            if not call or not call['claimed'] or call['session'] != principal.session_id or not self._current(principal.session_id):
                raise ValueError('Link call expired or pairing changed')
            if call['result'] is None:
                call['result'] = result
            self.condition.notify_all()
            return {'ok': True}
