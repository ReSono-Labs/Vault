"""Synthetic format demonstrations shared by analysis and reconciliation prompts."""
import json


def _proposal(disposition, *, target=None, conditions=None):
    return {
        "disposition": disposition,
        "target_definition_id": target,
        "description": "Look up a contact using the authorized contacts capability",
        "conditions": conditions or ["User requests contact lookup"],
        "required_slots": ["contact_query"],
        "exclusions": ["Do not modify contacts"],
        "capability_ids": ["demo.contacts.read"],
        "point_ids": ["demo-point"],
        "source_ids": ["demo-request", "demo-result", "demo-answer"],
        "examples": ["Find the contact matching {contact_query}"],
    }


PROPOSAL_EXAMPLES = {
    "create": _proposal("create"),
    "add_example": _proposal("add_example", target="demo-existing-rule"),
    "revise": _proposal("revise", target="demo-existing-rule", conditions=[
        "User requests contact lookup", "Disambiguate multiple matches before selecting a contact"]),
    "insufficient_evidence": {
        **_proposal("insufficient_evidence"),
        "description": "Captured evidence does not establish a reusable successful procedure",
        "conditions": [], "required_slots": [], "exclusions": [],
        "capability_ids": [], "examples": [],
    },
}

_unknown = {"judgment": "unknown", "evidence_source_ids": [],
            "explanation": "No linked user feedback was captured; satisfaction is unknown"}
ASSESSMENT_EXAMPLE = {
    "point_id": "demo-point",
    "request_resolution": {"judgment": "resolved",
        "evidence_source_ids": ["demo-request", "demo-result", "demo-answer"],
        "explanation": "The captured answer fulfills the final lookup request using the matching result"},
    "usefulness": {"judgment": "helpful", "evidence_source_ids": ["demo-request", "demo-result"],
        "explanation": "The lookup supplied the requested contact information"},
    "tool_selection": {"judgment": "correct", "evidence_source_ids": ["demo-request", "demo-result"],
        "explanation": "The authorized read capability matches the contact lookup request"},
    "context_selection": {"judgment": "correct", "evidence_source_ids": ["demo-request", "demo-result"],
        "explanation": "The returned contact matches the identity specified in the final request"},
    "result_quality": {"judgment": "correct", "evidence_source_ids": ["demo-result", "demo-answer"],
        "explanation": "The answer accurately reports the captured matching result"},
    "user_satisfaction": dict(_unknown), "tool_satisfaction": dict(_unknown),
    "context_satisfaction": dict(_unknown), "result_satisfaction": dict(_unknown),
    "failure_stage": "none",
}
REVIEW_EXAMPLE = {"contract_version": 3, "assessments": [ASSESSMENT_EXAMPLE],
                  "proposals": [PROPOSAL_EXAMPLES["create"]]}

FORMAT_EXAMPLES = """
RECORD FORMATTING EXAMPLES — synthetic demonstrations, NEVER session evidence.
Return one JSON object matching the supplied structured schema, no prose/fences.
All fields are required: use JSON null for absent target IDs, [] for empty arrays.
Proposal conditions is an array of strings, not the database's internal {all: ...}
object. Use capability_ids (not capabilities) and target_definition_id (not id).
Full analysis envelope, including an assessment with unknown satisfaction:
""" + json.dumps(REVIEW_EXAMPLE, ensure_ascii=False) + """
Alternative proposal records below demonstrate mutually exclusive classifications,
NOT four proposals to emit together. Assume the retrieved demo-existing-rule has
the create example's exact authoritative behavior. add_example is for another
phrasing of that behavior; revise adds supported disambiguation while retaining
prior applicability/slots/capabilities/exclusions. A truly different operation
uses create with its OWN supported behavior/capability, never this demo by default.
insufficient_evidence does not learn successful behavior. no_change uses the same
proposal fields with disposition=no_change and explains why no update is needed.
""" + json.dumps(PROPOSAL_EXAMPLES, ensure_ascii=False) + """
Replace ALL demo IDs/capabilities with supplied actual references; if unavailable,
defer rather than copy or invent them. Examples use parameter placeholders, not
private customer names or concrete IDs. Generate no database IDs, versions, scope,
activation status or permissions: the validated persistence layer owns those.
For reconciliation, the envelope additionally requires a rationale string, e.g.
"Proposal 1 reuses the retrieved rule: same read action and applicability; only
phrasing differs." Preserve the ACTUAL analysis assessments, citations and example
strings exactly, not the demonstrations. Defer unsafe changes or missing evidence.
"""
