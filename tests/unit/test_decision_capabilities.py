from dataclasses import replace

import pytest

from app.vault_runtime.decision_routing.capabilities import CapabilityBinding, CapabilityReadAdapter
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition,ToolInvocationContext


CONTEXT = ToolInvocationContext(agent=AgentKind.VOICE,user_id="u",workspace_id="w",local_session_id="s",tool_call_id="actual-input-request")


def definition(tool_id="plugin.invoice.v1",name="invoice",**changes):
    return ToolDefinition(tool_id=tool_id,name=name,description="Invoice lookup",input_schema={"type":"object","properties":{}},
        handler=lambda *_:pytest.fail("Eligibility must not invoke a handler"),**changes)


def test_actual_catalog_replace_remove_schema_effect_and_grants_change_fingerprint():
    granted = [True]
    authorize = lambda *_:granted[0]
    catalog = ToolCatalog(authorizer=authorize)
    tool = definition()
    catalog.replace_capability_source("provider",(tool,))
    adapter = CapabilityReadAdapter(catalog=catalog,authorizer=authorize,
        bindings=(CapabilityBinding("accounting.invoice.read",tool.tool_id,"explicit-provider"),))
    first = adapter.capture(CONTEXT)
    assert first.read_only(("accounting.invoice.read",))
    catalog.replace_capability_source("provider",(replace(tool,input_schema={"type":"object","properties":{"invoice":{"type":"string"}}}),))
    changed = adapter.capture(CONTEXT)
    assert changed.fingerprint!=first.fingerprint
    catalog.replace_capability_source("provider",(replace(tool,effect_class="write"),))
    assert not adapter.capture(CONTEXT).read_only(("accounting.invoice.read",))
    granted[0]=False
    denied = adapter.capture(CONTEXT)
    assert denied.resolved==() and denied.unavailable==("accounting.invoice.read",)
    granted[0]=True
    catalog.remove_capability_source("provider")
    assert adapter.capture(CONTEXT).resolved==()


def test_ambiguous_and_foreign_provider_fail_closed_without_inference():
    catalog = ToolCatalog(authorizer=lambda *_:True)
    a,b = definition(),definition("other.v1","other",scope_user_id="u",scope_workspace_id="w")
    catalog.register(a)
    catalog.register(b)
    adapter = CapabilityReadAdapter(catalog=catalog,authorizer=lambda *_:True,
        bindings=(CapabilityBinding("invoice",a.tool_id,"a"),CapabilityBinding("invoice",b.tool_id,"b")))
    assert adapter.capture(CONTEXT).unavailable==("invoice",)
    catalog.remove_capability_source("not-a-provider")
    # The foreign scoped provider disappears; exact remaining binding resolves.
    assert len(adapter.capture(replace(CONTEXT,user_id="foreign")).resolved)==1
    foreign_only = CapabilityReadAdapter(catalog=catalog,authorizer=lambda *_:True,
        bindings=(CapabilityBinding("invoice",b.tool_id,"b"),))
    assert foreign_only.capture(replace(CONTEXT,user_id="foreign")).resolved==()


def test_invalid_duplicate_mapping_and_authorizer_error():
    catalog = ToolCatalog(authorizer=lambda *_:True)
    tool = definition()
    catalog.register(tool)
    binding = CapabilityBinding("invoice",tool.tool_id,"provider")
    with pytest.raises(ValueError):
        CapabilityReadAdapter(catalog=catalog,authorizer=None,bindings=(binding,))
    with pytest.raises(ValueError):
        CapabilityReadAdapter(catalog=catalog,authorizer=lambda *_:True,bindings=(binding,binding))
    def fail(*_):
        raise RuntimeError("secret")
    current = CapabilityReadAdapter(catalog=catalog,authorizer=fail,bindings=(binding,)).capture(CONTEXT)
    assert current.resolved==() and not current.read_only(("invoice",))
