"""Offline, fresh-process SDK compatibility probe; never uses a provider credential."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

from agents import Agent, FunctionTool, RunConfig, Runner, RunState, set_tracing_disabled
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from app.vault_runtime.background_agent.checkpoints import approval_fingerprint, validate_sdk_checkpoint


class OfflineModel(Model):
    async def get_response(self, system_instructions, input, *args, **kwargs):
        if isinstance(input, list) and any(item.get("type") == "function_call_output" for item in input):
            output = [ResponseOutputMessage(
                id="message-proof", role="assistant", status="completed", type="message",
                content=[ResponseOutputText(type="output_text", text="finished", annotations=[])],
            )]
        else:
            output = [ResponseFunctionToolCall(
                id="tool-proof", call_id="call-proof", name="publish_brief", type="function_call",
                arguments='{"card_id":"proof-card","text":"brief"}',
            )]
        return ModelResponse(output=output, usage=Usage(requests=1), response_id="response-proof")

    async def stream_response(self, *args, **kwargs):
        raise AssertionError("This offline probe must not open a model stream")
        yield  # Make this the async-iterator implementation the SDK requires.


async def main(mode: str, directory: Path, choice: str = "allow_once") -> None:
    set_tracing_disabled(True)
    provider_key = os.environ.get("VAULT_PROOF_PROVIDER", "openai")

    async def effect(_context, arguments):
        with (directory / "effects.jsonl").open("a") as target:
            target.write(json.dumps(json.loads(arguments), sort_keys=True) + "\n")
        return "saved"

    agent = Agent(
        name="Vault Background Agent", model=OfflineModel(),
        tools=[FunctionTool(
            name="publish_brief", description="Publish the prepared offline test brief",
            params_json_schema={"type": "object", "properties": {
                "card_id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["card_id", "text"], "additionalProperties": False},
            on_invoke_tool=effect, needs_approval=True,
        )],
    )
    config = RunConfig(tracing_disabled=True)
    if mode == "prepare":
        result = await Runner.run(agent, "Prepare a brief", context={"user_id": "proof-user"}, run_config=config)
        assert len(result.interruptions) == 1
        state = result.to_state()
        (directory / "state.json").write_text(json.dumps({
            "version": 1, "provider_key": provider_key, "model_id": "proof-model", "sdk_version": "0.18.3",
            "approval_hash": approval_fingerprint(result.interruptions[0]),
            "state": state.to_json(include_tracing_api_key=False),
        }))
        print(json.dumps({"waiting": True, "effects": (directory / "effects.jsonl").exists()}))
    elif mode == "resume":
        saved = json.loads((directory / "state.json").read_text())
        validate_sdk_checkpoint(saved, provider_key=provider_key, model_id="proof-model", sdk_version="0.18.3")
        state = await RunState.from_json(
            agent, saved["state"],
            context_override={"user_id": "proof-user"},
        )
        # The reloaded state's interruption is obtained through the public result API.
        pending = await Runner.run(agent, state, run_config=config)
        assert len(pending.interruptions) == 1
        if approval_fingerprint(pending.interruptions[0]) != saved["approval_hash"]:
            raise ValueError("SDK approval request changed")
        state = pending.to_state()
        if choice == "allow_once":
            state.approve(pending.interruptions[0])
        else:
            state.reject(pending.interruptions[0])
        result = await Runner.run(agent, state, run_config=config)
        print(json.dumps({"output": result.final_output, "waiting": bool(result.interruptions)}))
    else:
        raise ValueError("Unknown proof mode")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "allow_once"))
