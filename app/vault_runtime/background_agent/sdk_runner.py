from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentTurnObservation:
    model_turns: int
    reasoning_summaries: tuple[str, ...]


async def run_agent_turn(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_text: Any,
    base_url: str | None,
    reasoning_effort: str,
    max_turns: int,
    agent_name: str,
    mcp_server: object | None = None,
    function_tools: list[Any] | None = None,
    observation_sink: Callable[[AgentTurnObservation], None] | None = None,
    output_type: type[Any] | None = None,
    model_response_sink: Callable[[Any], None] | None = None,
    text_delta_sink: Callable[[str], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    model_api: str = "responses",
) -> Any:
    """Run one OpenAI Agents SDK turn and return the final output text.

    The single agent-execution path for every runtime agent (text, memory
    review, and future agents): one provider, one model-settings construction,
    one streamed/subscription vs sync/platform branch. Tracing stays disabled
    and no parallel agent loop is created. Callers own any MCP server
    lifecycle and pass the entered server in.
    """
    from agents import Agent, ModelSettings, RunConfig, RunHooks, Runner, set_tracing_disabled
    from agents.models.openai_provider import OpenAIProvider
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient
    from openai.types.shared import Reasoning

    set_tracing_disabled(True)
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=DefaultAsyncHttpxClient(),
    )
    if model_api not in {"responses", "chat_completions"}:
        await client.close()
        raise ValueError("Unsupported model API.")
    provider = OpenAIProvider(openai_client=client, use_responses=model_api == "responses")
    try:
        model_settings = ModelSettings(
            reasoning=Reasoning(effort=reasoning_effort, summary="auto")
            if reasoning_effort != "none" else None,
            store=False if base_url and model_api == "responses" else None,
        )
        agent = Agent(
            name=agent_name,
            instructions=instructions,
            model=model,
            model_settings=model_settings,
            mcp_servers=[mcp_server] if mcp_server is not None else [],
            tools=function_tools or [],
            output_type=output_type,
        )
        run_config = RunConfig(model_provider=provider)
        class ObservationHooks(RunHooks):
            async def on_llm_start(self, _context, _agent, _system_prompt, _input_items) -> None:
                if cancel_requested is not None and cancel_requested():
                    raise asyncio.CancelledError()

            async def on_llm_end(self, _context, _agent, response) -> None:
                if model_response_sink is not None:
                    # A required source sink must succeed before the SDK can
                    # dispatch this response's tools. Never swallow capture loss.
                    model_response_sink(response)
                _observe((response,), observation_sink)

        if base_url or text_delta_sink is not None or cancel_requested is not None:
            streamed = Runner.run_streamed(
                agent, input=input_text, run_config=run_config, max_turns=max_turns,
                hooks=ObservationHooks(),
            )
            async def watch_cancel():
                while not streamed.is_complete:
                    if cancel_requested is not None and cancel_requested():
                        streamed.cancel(mode="immediate")
                        return
                    await asyncio.sleep(0.1)

            watcher = asyncio.create_task(watch_cancel()) if cancel_requested is not None else None
            events = streamed.stream_events()
            try:
                async for event in events:
                    if text_delta_sink is not None and getattr(event,"type",None)=="raw_response_event":
                        data = event.data
                        if getattr(data,"type",None)=="response.output_text.delta":
                            text_delta_sink(data.delta)
                if cancel_requested is not None and cancel_requested():
                    raise asyncio.CancelledError()
            except BaseException:
                # A failed durable delta/source consumer is not permission for
                # the SDK's background run loop to continue dispatching tools.
                streamed.cancel(mode="immediate")
                try:
                    async for _ in events:
                        pass  # Drain cancellation without delivering lost source.
                except BaseException:
                    pass  # Preserve the original capture/cancellation failure.
                raise
            finally:
                if watcher is not None:
                    watcher.cancel()
                    await asyncio.gather(watcher,return_exceptions=True)
            if streamed.run_loop_exception is not None:
                raise streamed.run_loop_exception
            return streamed.final_output if output_type is not None else str(streamed.final_output)
        result = await Runner.run(
            agent, input=input_text, run_config=run_config, max_turns=max_turns,
            hooks=ObservationHooks(),
        )
        return result.final_output if output_type is not None else str(result.final_output)
    finally:
        await provider.aclose()
        await client.close()


def run_agent_turn_sync(**kwargs) -> str:
    """Synchronous wrapper for callers that do not already run an event loop."""
    return asyncio.run(run_agent_turn(**kwargs))


def _observe(raw_responses: object, sink: Callable[[AgentTurnObservation], None] | None) -> None:
    if sink is None:
        return
    responses = tuple(raw_responses) if isinstance(raw_responses, (list, tuple)) else ()
    summaries: list[str] = []
    for response in responses:
        for item in getattr(response, "output", ()):
            if getattr(item, "type", None) != "reasoning":
                continue
            for summary in getattr(item, "summary", ()):
                text = str(getattr(summary, "text", "")).strip()
                if text:
                    summaries.append(text[:16_384])
    sink(AgentTurnObservation(len(responses), tuple(summaries)))
