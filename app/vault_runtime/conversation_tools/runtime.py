import asyncio
import json

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext,ToolInvocationResult
from app.vault_runtime.tools.strict_json import parse_json_object_bytes
from app.vault_runtime.voice.tools import canonical_arguments_sha256


class ConversationToolRuntime:
    def __init__(self,*,catalog,authority,store,principal,turn,owner,canceled,genui=False):
        self.catalog,self.authority,self.store = catalog,authority,store
        self.principal,self.turn,self.owner,self.canceled = principal,turn,owner,canceled
        self.original_calls = {}
        # Chat-only display tool: not in the shared catalog, so it never reaches Voice
        # realtime sessions, Decisions candidates, grants or the execution ledger.
        self.genui = genui
        self.used_tools = []
        self.cards = 0

    def observe_calls(self,calls):
        for identity,value in calls.items():
            if identity in self.original_calls:
                raise ValueError("Original call identity was repeated across model responses.")
            self.original_calls[identity] = value

    def definitions(self):
        return tuple(d for d in self.catalog.definitions_for(AgentKind.VOICE,user_id=self.principal.user_id,
            workspace_id=self.principal.workspace_id) if d.tool_id!="builtin.voice.mode-switch.v1")

    def function_tools(self,definitions=None):
        from agents import FunctionTool
        tools = []
        for definition in self.definitions() if definitions is None else definitions:
            async def invoke(context,raw_arguments,*,name=definition.name):
                call_id = getattr(context,"tool_call_id",None)
                args = parse_json_object_bytes(raw_arguments.encode())
                # Worker accounting remains held until asyncio.run drains its
                # default executor, including a canceled synchronous tool effect.
                result = await asyncio.to_thread(self.invoke,name,args,call_id)
                return json.dumps(result.mcp_result(),ensure_ascii=False)
            tools.append(FunctionTool(name=definition.name,description=definition.description,
                params_json_schema=definition.input_schema,on_invoke_tool=invoke,strict_json_schema=False))
        if self.genui:
            tools.append(self._present_tool())
        return tools

    def _present_tool(self):
        from agents import FunctionTool
        from app.vault_runtime.genui import catalog as genui
        async def invoke(context,raw_arguments):
            call_id = getattr(context,"tool_call_id",None)
            args = parse_json_object_bytes(raw_arguments.encode())
            result = await asyncio.to_thread(self.present,args,call_id)
            return json.dumps(result,ensure_ascii=False)
        return FunctionTool(name=genui.TOOL_NAME,description=genui.TOOL_DESCRIPTION,
            params_json_schema=genui.INPUT_SCHEMA,on_invoke_tool=invoke,strict_json_schema=False)

    def present(self,arguments,call_id):
        """Validate one card and append it as a display-only ui event. Performs no action."""
        from uuid import uuid4
        from app.vault_runtime.genui import catalog as genui
        if self.canceled():
            raise asyncio.CancelledError()
        if not isinstance(call_id,str) or self.original_calls.get(call_id)!=(genui.TOOL_NAME,canonical_arguments_sha256(arguments)):
            raise ValueError("Card is not linked to an original captured model proposal.")
        if self.cards>=genui.MAX_CARDS_PER_TURN:
            return dict(shown=False,error="Card limit reached for this reply; answer in text.")
        try:
            card = genui.validate(arguments)
        except genui.SpecError as error:
            return dict(shown=False,error=str(error)+" Fix the card or answer in text.")
        self.cards += 1
        card_id = str(uuid4())
        # Provenance is what actually ran this turn, never what the model claims.
        self.store.append(self.principal,self.turn,self.owner,"ui",dict(cardId=card_id,callId=call_id,
            card=card,sources=list(dict.fromkeys(self.used_tools))))
        return dict(shown=True,cardId=card_id)

    def invoke(self,name,arguments,call_id):
        if self.canceled():
            raise asyncio.CancelledError()
        if not isinstance(call_id,str) or self.original_calls.get(call_id)!=(name,canonical_arguments_sha256(arguments)):
            raise ValueError("Tool dispatch is not linked to an original captured model proposal.")
        context = ToolInvocationContext(agent=AgentKind.VOICE,user_id=self.principal.user_id,
            workspace_id=self.principal.workspace_id,local_session_id=self.principal.session_id,
            conversation_id=self.turn.conversation_id,turn_id=self.turn.turn_id,tool_call_id=call_id,
            user_utterance=self.turn.input_text)
        definition = next((d for d in self.definitions() if d.name==name),None)
        def event(state,**extra):
            self.store.append(self.principal,self.turn,self.owner,"tool_status",dict(callId=call_id,name=name,state=state,**extra))
        if definition is None or not self.authority.authorize(definition,context):
            event("denied")
            return ToolInvocationResult("Tool is not granted in this conversation's current scope.",is_error=True)
        claim = self.authority.prepare_conversation_invocation(context=context,definition=definition,arguments=arguments)
        if claim.disposition=="succeeded" and claim.recovered_result is not None:
            event("replayed",invocationId=claim.invocation_id)
            return claim.recovered_result
        if claim.disposition!="acquired":
            event(claim.disposition,invocationId=claim.invocation_id)
            return ToolInvocationResult("Tool call is active or requires review; it was not repeated.",is_error=True)
        try:
            event("invoking",invocationId=claim.invocation_id,effect=definition.effect_class)
            if self.canceled():
                raise asyncio.CancelledError()
            result = self.catalog.invoke(name,arguments,context=context)
            self.authority.complete(claim=claim,context=context,result=result)
        except BaseException:
            self.authority.fail(claim=claim,effect_class=definition.effect_class,failure_code="conversation_tool_interrupted")
            raise
        # The canonical result is already committed. Capture failure here must
        # fail the turn, never retry or undo an executed effect.
        event("succeeded",invocationId=claim.invocation_id,isError=result.is_error)
        if not result.is_error:
            self.used_tools.append(name)
        return result
