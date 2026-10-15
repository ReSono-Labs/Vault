from dataclasses import replace
from hashlib import sha256
import os

import psycopg
import pytest

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition,ToolInvocationContext,ToolInvocationResult
from app.vault_runtime.voice.tools import LocalToolAuthority,VoiceToolRuntime
from tests.integration.test_voice_runtime_postgres import voice_context,_new_session
from tests.integration.test_conversation_identity_postgres import require_test_database


@pytest.fixture(autouse=True)
def exact_isolated_database():
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Isolated PostgreSQL harness required")
    require_test_database(url)  # Runs before the reused schema-reset fixture.


def test_actual_voice_invocation_preserves_matched_claim_and_replay_does_not_rewrite_it(voice_context):
    url,_,owner,_,memories,voices = voice_context
    voice = _new_session(voices,owner.principal)
    authority = LocalToolAuthority(database_url=url)
    catalog = ToolCatalog(authorizer=authority.authorize)
    calls = []
    def handler(*_):
        calls.append("invoked")
        return ToolInvocationResult("Synthetic outcome",structured_content={"paid":True})
    definition = ToolDefinition(tool_id="builtin.test.decision-source.v1",name="source_test",
        description="Synthetic read",input_schema={"type":"object","properties":{}},handler=handler)
    catalog.register(definition)
    authority.ensure_builtin_grants(user_id=owner.principal.user_id,workspace_id=owner.principal.workspace_id,definitions=(definition,))
    runtime = VoiceToolRuntime(catalog=catalog,authority=authority)
    def entry(index,text,role="user"):
        return memories.append_transcript(user_id=owner.principal.user_id,workspace_id=owner.principal.workspace_id,
            voice_session_id=voice.voice_session_id,entry_index=index,role=role,event_type="synthetic.final",text_content=text)
    original = entry(0,"Check invoice 482")
    later = entry(1,"Check a different invoice")
    entry(2,"Assistant words",role="assistant")
    context = ToolInvocationContext(agent=AgentKind.VOICE,user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,local_session_id=owner.principal.session_id,
        voice_session_id=voice.voice_session_id,tool_call_id="call-1",
        user_utterance_id=original.entry_index,user_utterance=original.text_content)
    assert not runtime.invoke(name=definition.name,arguments={},context=context).is_error
    runtime.invoke(name=definition.name,arguments={},context=replace(context,
        user_utterance_id=later.entry_index,user_utterance=later.text_content))
    assert calls==["invoked"]
    for call_id,index,text in (("missing",None,None),("mismatch",1,"wrong text"),("non-user",2,"Assistant words"),
                               ("bool",True,later.text_content),("missing-index",90,later.text_content)):
        runtime.invoke(name=definition.name,arguments={},context=replace(context,tool_call_id=call_id,
            user_utterance_id=index,user_utterance=text))
    with psycopg.connect(url) as connection:
        rows = connection.execute("SELECT tool_call_id,source_utterance_index,source_utterance_fingerprint FROM vault_private.vault_voice_tool_invocations ORDER BY tool_call_id").fetchall()
        expected = sha256(original.text_content.encode()).hexdigest()
        assert next(r for r in rows if r[0]=="call-1")[1:] == (0,expected)
        assert all(r[1:]==(None,None) for r in rows if r[0]!="call-1")
    voices.ensure_schema()  # Repeat additive installation keeps provenance.
