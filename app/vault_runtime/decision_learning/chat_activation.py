"""Fail-closed joining gates over existing Chat evidence, reviews and grants."""
from hashlib import sha256

from app.vault_runtime.decision_routing.capabilities import CapabilityBinding, CapabilityReadAdapter
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext
from .repository import source_fingerprint
from .reviewer import REVIEW_CONTRACT_VERSION, ReviewOutput, _validate_output


class ChatActivationGates:
    def __init__(self, *, source, catalog, authority):
        self.source, self.catalog, self.authority = source, catalog, authority

    def capabilities(self, cursor, principal):
        context = ToolInvocationContext(agent=AgentKind.VOICE, user_id=principal.user_id,
            workspace_id=principal.workspace_id, local_session_id=principal.session_id,
            tool_call_id="decision-qualification-only")
        cursor.execute("""SELECT DISTINCT jsonb_array_elements_text(d.capability_refs_json)
          FROM vault_private.vault_decision_definitions d JOIN vault_private.vault_decision_generations g
          USING(user_id,workspace_id,generation_id) WHERE d.user_id=%s AND d.workspace_id=%s
          AND g.state IN ('building','active')""",(principal.user_id,principal.workspace_id))
        required = {r[0] for r in cursor.fetchall()}
        definitions = tuple(d for d in self.catalog.metadata_for(AgentKind.VOICE,
            user_id=principal.user_id, workspace_id=principal.workspace_id) if d.tool_id in required)
        authorized = self.authority.authorized_definitions_in_transaction(definitions,context,cursor)
        ids = {d.tool_id for d in authorized}
        # Identity bindings only. No inferred cross-provider semantic aliases.
        adapter = CapabilityReadAdapter(catalog=self.catalog,
            authorizer=lambda definition, context: definition.tool_id in ids and definition.visible_in(
                user_id=context.user_id,workspace_id=context.workspace_id),
            bindings=tuple(CapabilityBinding(d.tool_id,d.tool_id,"vault-catalog") for d in definitions))
        return adapter.capture(context,definitions=definitions)

    def qualify(self, cursor, principal, rule):
        if not rule.source_review_ids:
            return False
        matched = False
        for review_id in rule.source_review_ids:
            cursor.execute("""SELECT conversation_id,segment_id,source_snapshot_fingerprint,
              learner_contract_version,assessments_json,proposals_json,output_fingerprint,state
              FROM vault_private.vault_decision_reviews
              WHERE user_id=%s AND workspace_id=%s AND review_id=%s FOR SHARE""",
              (principal.user_id,principal.workspace_id,review_id))
            row = cursor.fetchone()
            if not row or row[3]!=REVIEW_CONTRACT_VERSION or row[7]!="completed":
                return False
            try:
                snapshot = self.source._read(cursor,principal,row[0],segment_id=row[1])
                if snapshot is None or snapshot.coverage!="complete" or source_fingerprint(snapshot)!=row[2]:
                    return False
                output = ReviewOutput.model_validate(dict(contract_version=row[3],assessments=row[4],proposals=row[5]))
                if sha256(output.model_dump_json().encode()).hexdigest()!=row[6]:
                    return False
                _validate_output(output,snapshot)
            except (ValueError, RuntimeError, KeyError, TypeError):
                return False
            for proposal in output.proposals:
                if proposal.disposition not in {"create","revise","add_example"}:
                    continue
                if (proposal.description==rule.description and {"all":list(proposal.conditions)}==rule.conditions
                    and tuple(proposal.required_slots)==rule.required_slots
                    and tuple(proposal.capability_ids)==rule.capability_ids
                    and tuple(proposal.exclusions)==rule.exclusions):
                    matched = True
        return matched
