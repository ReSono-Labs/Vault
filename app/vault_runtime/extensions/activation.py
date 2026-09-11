"""Progressive Skill disclosure adapted from R1 skills/activation.py."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.vault_runtime.extensions.filesystem import extension_category_path
from app.vault_runtime.extensions.models import ExtensionKind
from app.vault_runtime.extensions.repository import ExtensionNotFoundError, ExtensionRepository
from app.vault_runtime.extensions.skills import parse_skill, parse_skill_document
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


@dataclass(frozen=True, slots=True)
class SkillSummary:
    extension_id: str
    name: str
    description: str


class SkillActivation:
    def __init__(self, *, repository: ExtensionRepository, extension_root: Path) -> None:
        self._repository = repository
        self._root = extension_root.resolve()

    def list_available(self, *, user_id: str, workspace_id: str, agent: AgentKind) -> tuple[SkillSummary, ...]:
        result: list[SkillSummary] = []
        for record, capability, _effect in self._repository.granted_extensions(
            user_id=user_id, workspace_id=workspace_id, agent=agent,
            kind=ExtensionKind.SKILL,
        ):
            if capability != "":
                continue
            document = parse_skill_document(
                self._direct_path(record.identity) / "SKILL.md",
                expected_directory=record.identity,
            )
            result.append(SkillSummary(record.extension_id, document.name, document.description))
        for record, capability, _effect in self._repository.granted_extensions(
            user_id=user_id, workspace_id=workspace_id, agent=agent,
            kind=ExtensionKind.PLUGIN, capability_prefix="skill:",
        ):
            name = capability.removeprefix("skill:")
            document = parse_skill(self._plugin_path(record.identity, name))
            result.append(SkillSummary(record.extension_id, document.name, document.description))
        return tuple(sorted(result, key=lambda item: (item.name, item.extension_id)))

    def load(self, *, user_id: str, workspace_id: str, agent: AgentKind, extension_id: str, name: str) -> str:
        # Requery every load: revocation, disablement and safe mode take effect immediately.
        available = {(item.extension_id, item.name): item for item in self.list_available(user_id=user_id, workspace_id=workspace_id, agent=agent)}
        if (extension_id, name) not in available:
            raise ExtensionNotFoundError("Agent Skill is not enabled in this local scope")
        for record, capability, _effect in self._repository.granted_extensions(
            user_id=user_id, workspace_id=workspace_id, agent=agent, kind=ExtensionKind.SKILL,
        ):
            if record.extension_id == extension_id and record.identity == name and capability == "":
                return parse_skill_document(
                    self._direct_path(name) / "SKILL.md", expected_directory=name,
                ).instructions
        for record, capability, _effect in self._repository.granted_extensions(
            user_id=user_id, workspace_id=workspace_id, agent=agent,
            kind=ExtensionKind.PLUGIN, capability_prefix="skill:",
        ):
            if record.extension_id == extension_id and capability == f"skill:{name}":
                return parse_skill(self._plugin_path(record.identity, name)).instructions
        raise ExtensionNotFoundError("Agent Skill is not enabled in this local scope")

    def tool_definition(self) -> ToolDefinition:
        """R1 progressive-disclosure loader adapted to local user/workspace scope."""
        return ToolDefinition(
            tool_id="builtin.skill-loader.v1", name="load_agent_skill",
            description="Load the instructions for one relevant enabled Agent Skill by name.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 255}},
                "required": ["name"], "additionalProperties": False,
            },
            handler=self._load_for_context, effect_class="read",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        )

    def _load_for_context(
        self, context: ToolInvocationContext, arguments: dict[str, object]
    ) -> ToolInvocationResult:
        name = str(arguments.get("name", "")).strip()
        matches = tuple(item for item in self.list_available(
            user_id=context.user_id, workspace_id=context.workspace_id, agent=context.agent,
        ) if item.name == name)
        if len(matches) != 1:
            return ToolInvocationResult(
                "The requested Agent Skill is unavailable or ambiguous in this local scope.",
                is_error=True,
            )
        try:
            instructions = self.load(
                user_id=context.user_id, workspace_id=context.workspace_id,
                agent=context.agent, extension_id=matches[0].extension_id, name=name,
            )
        except ExtensionNotFoundError:
            return ToolInvocationResult("The requested Agent Skill is not enabled.", is_error=True)
        return ToolInvocationResult(
            instructions, structured_content={"name": name, "instructions": instructions},
        )

    def _direct_path(self, identity: str) -> Path:
        return self._confined(
            extension_category_path(root=self._root, category="skills", identity=identity) / "current",
        )

    def _plugin_path(self, identity: str, name: str) -> Path:
        return self._confined(
            extension_category_path(root=self._root, category="plugins", identity=identity)
            / "current"
            / "skills"
            / name,
        )

    def _confined(self, path: Path) -> Path:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self._root):
            raise ExtensionNotFoundError("Agent Skill path escapes extension storage")
        return resolved
