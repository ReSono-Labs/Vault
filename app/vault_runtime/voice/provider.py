from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.voice.context import VoiceContextBuilder
from app.vault_runtime.voice.models import VoiceContext, VoiceSession
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import LocalToolAuthority
from app.vault_runtime.voice.modes import GOAL_SUBMIT_TOOL, MODE_SWITCH_TOOL, VoiceModeService


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider_key: str
    display_name: str
    connection_mode: str
    protocol: str
    default_voice_model: str
    default_text_model: str
    default_voice: str
    voices: tuple[str, ...]
    voice_models: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderCredential:
    value: str = field(repr=False)
    auth_method: str = "api_key"

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("provider credential is empty")


@dataclass(frozen=True, slots=True)
class RealtimeSessionRequest:
    model_key: str
    connection_mode: str
    output_modalities: tuple[str, ...] = ("audio",)
    instructions: str | None = None
    tool_definitions: tuple[dict[str, object], ...] = ()
    voice: str | None = None
    input_audio_transcription_model: str | None = None
    turn_detection_type: str | None = None
    turn_detection_create_response: bool | None = None
    turn_detection_interrupt_response: bool | None = None
    audio_format: str | None = None
    audio_rate: int | None = None
    input_noise_reduction_type: str | None = None
    turn_detection_threshold: float | None = None
    turn_detection_prefix_padding_ms: int | None = None
    turn_detection_silence_duration_ms: int | None = None
    tool_choice: str | None = None
    offer_sdp: str | None = None
    voice_session_id: str | None = None
    display_name: str | None = None


@dataclass(frozen=True, slots=True)
class RealtimeSessionResult:
    provider_key: str
    model_key: str
    connection_mode: str
    provider_session_id: str
    session_update_event: dict[str, object]
    client_secret: str | None = field(default=None, repr=False)
    expires_at: int | None = None
    sdp_answer: str | None = None
    protocol: str = "openai-realtime"
    websocket_url: str | None = None
    websocket_protocol: str | None = field(default=None, repr=False)
    input_sample_rate: int | None = None
    output_sample_rate: int | None = None


class RealtimeProvider(Protocol):
    provider_key: str
    descriptor: ProviderDescriptor

    def create_realtime_session(
        self, request: RealtimeSessionRequest, *, credential: ProviderCredential
    ) -> RealtimeSessionResult: ...


class ProviderRegistry:
    def __init__(self, providers: tuple[RealtimeProvider, ...] = ()) -> None:
        self._providers: dict[str, RealtimeProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: RealtimeProvider) -> None:
        key = provider.provider_key.strip()
        if not key or key in self._providers:
            raise ValueError("provider identity collision")
        self._providers[key] = provider

    def require(self, provider_key: str) -> RealtimeProvider:
        provider = self._providers.get(provider_key)
        if provider is None:
            raise ValueError("realtime provider is not configured")
        return provider

    def descriptors(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(provider.descriptor for provider in self._providers.values())


@dataclass(frozen=True, slots=True)
class StartedVoiceSession:
    session: VoiceSession
    context: VoiceContext
    provider: RealtimeSessionResult


class VoiceSessionCoordinator:
    """Voice donor startup order with local authority and credential separation."""

    def __init__(
        self,
        *,
        sessions: VoiceSessionRepository,
        contexts: VoiceContextBuilder,
        tools: ToolCatalog,
        providers: ProviderRegistry,
        tool_authority: LocalToolAuthority | None = None,
        voice_modes: VoiceModeService | None = None,
    ) -> None:
        self._sessions = sessions
        self._contexts = contexts
        self._tools = tools
        self._providers = providers
        self._tool_authority = tool_authority
        self._voice_modes = voice_modes

    def provider_descriptors(self) -> tuple[ProviderDescriptor, ...]:
        return self._providers.descriptors()

    def start(
        self,
        *,
        principal: LocalPrincipal,
        provider_key: str,
        model_key: str,
        connection_mode: str,
        credential: ProviderCredential,
        voice: str | None = None,
        offer_sdp: str | None = None,
    ) -> StartedVoiceSession:
        local = self._sessions.create_session(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            local_session_id=principal.session_id, provider_key=provider_key,
            model_key=model_key, connection_mode=connection_mode,
        )
        context = self._contexts.build(principal=principal, voice_session_id=local.voice_session_id)
        definitions = self._tools.definitions_for(
            AgentKind.VOICE, user_id=principal.user_id, workspace_id=principal.workspace_id,
        )
        if self._tool_authority is not None:
            self._tool_authority.ensure_builtin_grants(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                definitions=definitions,
            )
        primary = tuple(item for item in definitions if item.name != GOAL_SUBMIT_TOOL)
        goal = tuple(item for item in definitions if item.name in {MODE_SWITCH_TOOL, GOAL_SUBMIT_TOOL})
        if self._voice_modes is not None:
            self._voice_modes.open_session(
                local.voice_session_id,
                primary_instructions=context.instructions,
                primary_tools=lambda items=primary: tuple(item.realtime_definition() for item in items),
                goal_intake_tools=lambda items=goal: tuple(item.realtime_definition() for item in items),
            )
        request = RealtimeSessionRequest(
            model_key=model_key,
            connection_mode=connection_mode,
            instructions=context.instructions,
            tool_definitions=tuple(item.realtime_definition() for item in primary),
            voice=voice,
            input_audio_transcription_model="gpt-4o-mini-transcribe",
            turn_detection_type="server_vad",
            turn_detection_create_response=True,
            turn_detection_interrupt_response=False,
            audio_format="audio/pcm", audio_rate=24_000,
            input_noise_reduction_type="near_field",
            turn_detection_threshold=0.92,
            turn_detection_prefix_padding_ms=500,
            turn_detection_silence_duration_ms=1_200,
            tool_choice="auto",
            offer_sdp=offer_sdp,
            voice_session_id=local.voice_session_id,
            display_name=context.display_name,
        )
        provider = self._providers.require(provider_key)
        try:
            result = provider.create_realtime_session(request, credential=credential)
            if (
                result.provider_key != provider_key
                or result.model_key != model_key
                or result.connection_mode != connection_mode
            ):
                raise ValueError("realtime provider returned mismatched session authority")
            opened = self._sessions.mark_transport_open(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,
                voice_session_id=local.voice_session_id,
                provider_session_id=result.provider_session_id,
            )
        except Exception:
            self._sessions.close_session(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,
                voice_session_id=local.voice_session_id, terminal_status="failed",
            )
            raise
        return StartedVoiceSession(opened, context, result)

    def close_modes(self, voice_session_id: str) -> None:
        if self._voice_modes is not None:
            self._voice_modes.close_session(voice_session_id)
