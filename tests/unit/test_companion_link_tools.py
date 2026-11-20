from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest

from app.vault_runtime.link_companion.tools import CompanionLinkTools
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.system_agents.inventory import AgentKind


def fixture():
    paired = ['pair-1']
    catalog = ToolCatalog(authorizer=lambda d, c: True)
    grants = SimpleNamespace(ensure_builtin_grants=lambda **kw: None)
    bridge = CompanionLinkTools(catalog=catalog, authority=grants, pairing=lambda: paired[0], timeout=1)
    owner = SimpleNamespace(user_id='owner', workspace_id='ws', session_id='pair-1')
    definitions = [{'name':'card_model','description':'Read card','inputSchema':{'type':'object','properties':{}}}]
    bridge.publish(owner, definitions)
    context = ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id='owner',workspace_id='ws',
        tool_call_id='call',local_session_id='local',execution_id='run')
    return paired,catalog,bridge,owner,context


def test_native_tools_available_to_voice_and_background_only_while_paired():
    paired,catalog,bridge,owner,context=fixture()
    assert [d.name for d in catalog.definitions_for(AgentKind.VOICE,user_id='owner',workspace_id='ws')]==['link_card_model']
    assert not catalog.definitions_for(AgentKind.BACKGROUND,user_id='other',workspace_id='ws')
    paired[0]=None
    assert not catalog.definitions_for(AgentKind.VOICE,user_id='owner',workspace_id='ws')
    assert catalog.invoke('link_card_model',{},context=context).is_error


def test_call_is_claimed_once_and_result_returns_to_original_caller():
    paired,catalog,bridge,owner,context=fixture()
    with ThreadPoolExecutor() as pool:
        future=pool.submit(catalog.invoke,'link_card_model',{},context=context)
        call=bridge.poll(owner,wait=0.5)['calls'][0]
        assert call['name']=='card_model'
        assert not bridge.poll(owner,wait=0)['calls']
        bridge.complete(owner,call['id'],{'content':[{'type':'text','text':'card data'}]})
        assert future.result().text=='card data'


def test_repairing_cannot_complete_old_call():
    paired,catalog,bridge,owner,context=fixture()
    with ThreadPoolExecutor() as pool:
        future=pool.submit(catalog.invoke,'link_card_model',{},context=context)
        call=bridge.poll(owner,wait=0.5)['calls'][0]
        paired[0]='pair-2'
        with pytest.raises(ValueError):bridge.complete(owner,call['id'],{'content':[]})
        assert future.result().is_error


def test_http_tools_routes_require_current_companion_and_not_browser_auth():
    from app.vault_runtime.local_api.app import VaultLocalApiApp
    from app.vault_runtime.link_companion.repository import LinkCompanionAuthorizationError
    class Health:
        def health(self): return {'schemaReady':True}
    class Identity:
        def authenticate(self, session_token):
            if session_token != 'paired-key': raise LinkCompanionAuthorizationError('denied')
            return SimpleNamespace(session_id='pair-1',user_id='owner',workspace_id='ws',is_device_owner=True)
    class Pairing:
        linked='pair-1'
        def link_session_id(self):return self.linked
        def touch_session(self,session):pass
    pairing=Pairing()
    paired,catalog,bridge,owner,context=fixture()
    app=VaultLocalApiApp(store=Health(),token='unused',identity_service=Identity(),link_companion=pairing,link_tools=bridge)
    def poll(token):return app.handle(method='POST',target='/link-companion/tools/poll',
        headers={'Authorization':'Bearer '+token},body=b'{}')
    assert poll('browser-key').status_code==401
    assert poll('paired-key').status_code==200
    pairing.linked=None
    assert poll('paired-key').status_code==401


def test_native_worker_rejects_non_loopback_and_unsafe_credentials(tmp_path):
    from app.vault_runtime.link_companion.host_tools import request, private_json
    for url in ['http://192.168.1.1/mcp','https://example.com/mcp','http://user@127.0.0.1:80/mcp']:
        with pytest.raises(ValueError):request(url,'secret',{})
    p=tmp_path/'settings.json';p.write_text('{}');p.chmod(0o644)
    with pytest.raises(ValueError):private_json(p)
    p.chmod(0o600);assert private_json(p)=={}
    symlink=tmp_path/'alias';symlink.symlink_to(p)
    with pytest.raises(ValueError):private_json(symlink)


def _card_bridge():
    paired = ['pair-1']
    catalog = ToolCatalog(authorizer=lambda d, c: True)
    grants = SimpleNamespace(ensure_builtin_grants=lambda **kw: None)
    bridge = CompanionLinkTools(catalog=catalog, authority=grants, pairing=lambda: paired[0], timeout=1)
    owner = SimpleNamespace(user_id='owner', workspace_id='ws', session_id='pair-1')
    bridge.publish(owner, [{'name': 'chat_card_publish', 'description': 'Attach a live card',
                            'inputSchema': {'type': 'object', 'properties': {}}}])
    return catalog, bridge, owner


def _arguments_sent(catalog, bridge, owner, context):
    with ThreadPoolExecutor() as pool:
        future = pool.submit(catalog.invoke, 'link_chat_card_publish', {'fallback_text': 'A card'}, context=context)
        call = bridge.poll(owner, wait=0.5)['calls'][0]
        bridge.complete(owner, call['id'], {'content': [{'type': 'text', 'text': 'ok'}]})
        future.result()
        return call['arguments']


def test_call_cards_only_from_a_live_voice_call():
    catalog, bridge, owner = _card_bridge()
    voice = ToolInvocationContext(agent=AgentKind.VOICE, user_id='owner', workspace_id='ws',
                                  tool_call_id='call', local_session_id='local', voice_session_id='vs_123')
    assert _arguments_sent(catalog, bridge, owner, voice)['call'] == 'vs_123'
    background = ToolInvocationContext(agent=AgentKind.BACKGROUND, user_id='owner', workspace_id='ws',
                                       tool_call_id='call', local_session_id='local', execution_id='run')
    assert 'call' not in _arguments_sent(catalog, bridge, owner, background)
    # The same tool and text for every Vault runtime: only the arguments differ.
    assert catalog.definitions_for(AgentKind.VOICE, user_id='owner', workspace_id='ws')[0].description .startswith('Link: SHOW A CARD IN THE CONVERSATION NOW')
