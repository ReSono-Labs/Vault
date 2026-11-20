"""Content-free local JSON diagnostics; never a procedural training source."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from math import isfinite

EVENTS = frozenset({"revision_accepted","draft_skipped","preparation_started","reuse_checked",
    "memory_lookup_complete","decision_lookup_complete","decision_reconsidered","preparation_ready",
    "preparation_stale","preparation_failed","final_reused","final_researched","final_completed",
    "final_timeout","final_canceled","final_preparation_rejected","stream_invalidated","selection_started","selection_completed","memory_delivered","utterance_summary"})
SUMMARY_FIELDS = frozenset({"revisions","memory_updates","tool_updates","selections","deliveries"})
REASONS = frozenset({"off","composing","empty","not_meaningful","current","stale","failed","canceled",
    "timeout","no_candidates","missing_context","unavailable","refusal","no_supported_choice",
    "invalid_response","selected","fresh_memory","not_exact"})


def _id(value):
    return sha256(str(value).encode()).hexdigest()[:24] if value is not None else None


class LiveDiagnostics:
    def __init__(self, *, logger=None):
        if logger is None:
            logger = logging.getLogger("vault.live_decisions")
            if not logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(logging.Formatter("%(message)s"))
                logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
        self.logger = logger

    def review_event(self,event,principal,conversation_id,*,review_id=None,assessment_count=0):
        try:
            if event not in {"review_started","review_completed","review_pending","review_failed","review_skipped_empty"}:
                return
            if type(assessment_count) is not int or not 0<=assessment_count<=256:
                return
            self.logger.info(json.dumps(dict(schema_version=1,timestamp=datetime.now(timezone.utc).isoformat(),
                event=event,user_id=_id(principal.user_id),workspace_id=_id(principal.workspace_id),
                conversation_id=_id(conversation_id),review_id=_id(review_id),assessment_count=assessment_count),
                separators=(",",":")))
        except Exception:
            pass

    def emit(self, event, snapshot, *, reason=None, attempt_id=None, event_sequence=None,
             memory_count=None, decision_count=None, elapsed_ms=None,
             memory_reused=None, decisions_reused=None, definition_id=None, definition_version=None,
             summary=None):
        try:
            if event not in EVENTS or (reason is not None and reason not in REASONS):
                return
            identity = getattr(snapshot, "identity", None) or getattr(snapshot, "input_identity", None)
            scope = snapshot.scope
            row = dict(schema_version=1,timestamp=datetime.now(timezone.utc).isoformat(),event=event,
                user_id=_id(scope.user_id),workspace_id=_id(scope.workspace_id),
                conversation_id=_id(identity.conversation_id),segment_id=_id(identity.segment_id),
                utterance_id=_id(identity.utterance_id),turn_id=_id(identity.turn_id),
                revision=identity.revision,phase="final" if identity.turn_id else "provisional")
            if hasattr(snapshot,"request_id"):
                row["request_id"] = _id(snapshot.request_id)
                row["candidate_kind"] = "learned_rule" if snapshot.generation_id is not None else "catalog_proposal"
                row["generation_id"] = _id(snapshot.generation_id)
                row["candidate_count"] = len(snapshot.candidate_set)
                row["capability_snapshot_id"] = _id(snapshot.capability_snapshot_fingerprint)
            if type(identity.revision) is not int or identity.revision < 0:
                return
            if reason is not None:
                row["reason"] = reason
            if attempt_id is not None:
                row["attempt_id"] = _id(attempt_id)
            if definition_id is not None:
                row["definition_id"] = _id(definition_id)
            if definition_version is not None:
                if type(definition_version) is not int or definition_version < 1:
                    return
                row["definition_version"] = definition_version
            for key,value in (("memory_reused",memory_reused),("decisions_reused",decisions_reused)):
                if value is not None:
                    if type(value) is not bool:
                        return
                    row[key] = value
            for key, value in (("event_sequence",event_sequence),("memory_count",memory_count),("decision_count",decision_count)):
                if value is not None:
                    if type(value) is not int or value < 0:
                        return
                    row[key] = value
            if summary is not None:
                if (type(summary) is not dict or not set(summary) <= SUMMARY_FIELDS
                        or any(type(v) is not int or v < 0 for v in summary.values())):
                    return
                row["summary"] = dict(sorted(summary.items()))
            if elapsed_ms is not None:
                if type(elapsed_ms) not in {float,int} or not isfinite(elapsed_ms) or elapsed_ms < 0:
                    return
                row["elapsed_ms"] = round(elapsed_ms,3)
            self.logger.info(json.dumps(row,separators=(",",":")))
        except Exception:
            pass  # Diagnostics cannot publish, invalidate or fail the actual operation.
