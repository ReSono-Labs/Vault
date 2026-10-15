"""Explicit semantic aliases over the existing current catalog and grants."""
from dataclasses import dataclass
from hashlib import sha256

from app.vault_runtime.tools.strict_json import canonical_json_bytes


@dataclass(frozen=True,slots=True)
class CapabilityBinding:
    capability_id: str
    tool_id: str
    provider_key: str

    def __post_init__(self):
        if any(type(v) is not str or not v or v.strip()!=v or len(v)>256
               for v in (self.capability_id,self.tool_id,self.provider_key)):
            raise ValueError("Explicit bounded capability/tool/provider identities required.")


@dataclass(frozen=True,slots=True)
class ResolvedCapability:
    capability_id: str
    tool_id: str
    tool_name: str
    provider_key: str
    effect: str
    input_schema_json: str


@dataclass(frozen=True,slots=True)
class CapabilitySnapshot:
    fingerprint: str
    resolved: tuple[ResolvedCapability,...]
    unavailable: tuple[str,...]

    def read_only(self, required: tuple[str,...]) -> bool:
        if type(required) is not tuple or not required or len(set(required))!=len(required):
            return False
        current = {r.capability_id:r for r in self.resolved}
        return all(c in current and current[c].effect=="read" for c in required)


class CapabilityReadAdapter:
    def __init__(self, *, catalog, authorizer, bindings: tuple[CapabilityBinding,...]):
        if not callable(authorizer) or type(bindings) is not tuple or any(type(b) is not CapabilityBinding for b in bindings):
            raise ValueError("Explicit immutable bindings and existing grant authorizer required.")
        if len(set(bindings))!=len(bindings):
            raise ValueError("Duplicate capability bindings.")
        self.catalog,self.authorizer,self.bindings = catalog,authorizer,bindings

    def capture(self, context, *, definitions=None) -> CapabilitySnapshot:
        supplied = definitions if definitions is not None else self.catalog.definitions_for(context.agent,
            user_id=context.user_id,workspace_id=context.workspace_id)
        definitions = {d.tool_id:d for d in supplied}
        grouped = {}
        for binding in self.bindings:
            grouped.setdefault(binding.capability_id,[]).append(binding)
        resolved,unavailable = [],[]
        for capability,bindings in sorted(grouped.items()):
            candidates = []
            for binding in bindings:
                definition = definitions.get(binding.tool_id)
                if definition is None:
                    continue
                try:
                    authorized = self.authorizer(definition,context) is True
                except Exception:
                    authorized = False
                if authorized:
                    candidates.append(ResolvedCapability(capability,definition.tool_id,definition.name,
                        binding.provider_key,definition.effect_class,
                        canonical_json_bytes(definition.input_schema).decode()))
            if len(candidates)!=1:
                unavailable.append(capability)
            else:
                resolved.append(candidates[0])
        content = dict(scope=[context.user_id,context.workspace_id,context.local_session_id,context.agent.value],
            bindings=[[b.capability_id,b.tool_id,b.provider_key] for b in self.bindings],
            resolved=[[r.capability_id,r.tool_id,r.tool_name,r.provider_key,r.effect,r.input_schema_json] for r in resolved],
            unavailable=unavailable)
        return CapabilitySnapshot(sha256(canonical_json_bytes(content)).hexdigest(),tuple(resolved),tuple(unavailable))
