"""Project existing finalized Voice logs into the shared procedural learning input."""
from hashlib import sha256
import json

from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.memory.evidence import redact_evidence
from app.vault_runtime.system_agents.inventory import AgentKind
from .repository import ReviewConflictError,source_fingerprint
from .reviewer import ReviewInput

USER_FINAL = frozenset({"conversation.item.input_audio_transcription.completed",
                       "conversation.item.input_audio_transcript.completed"})
ASSISTANT_FINAL = frozenset({"response.audio_transcript.done","response.output_audio_transcript.done"})


class VoiceReviewSource:
    def __init__(self, *, database_url, catalog):
        self.database_url,self.catalog = database_url,catalog

    def _connect(self):
        import psycopg
        return psycopg.connect(self.database_url,connect_timeout=5)

    def ensure_schema(self):
        from app.vault_runtime.conversation.schema import ensure_conversation_schema
        with self._connect() as connection, connection.cursor() as cursor:
            ensure_conversation_schema(cursor)
            from app.vault_runtime.conversation.runtime_schema import ensure_voice_review_bridge
            ensure_voice_review_bridge(cursor)

    def load(self, principal, voice_session_id):
        with self._connect() as connection, connection.cursor() as cursor:
            snapshot = self._read(cursor,principal,voice_session_id)
            if not snapshot.sources:
                return None
            # Metadata-only identity bridge. Existing transcript remains authoritative.
            cursor.execute("""INSERT INTO vault_private.vault_conversations
              (conversation_id,user_id,workspace_id,create_key,state,source_voice_session_id)
              VALUES (%s,%s,%s,%s,'sealed',%s) ON CONFLICT(user_id,workspace_id,create_key) DO NOTHING""",
              (voice_session_id,principal.user_id,principal.workspace_id,"voice-review:"+voice_session_id,voice_session_id))
            cursor.execute("""SELECT conversation_id FROM vault_private.vault_conversations
              WHERE user_id=%s AND workspace_id=%s AND source_voice_session_id=%s FOR SHARE""",
              (principal.user_id,principal.workspace_id,voice_session_id))
            if cursor.fetchone()!=(voice_session_id,):
                raise ReviewConflictError("Voice review identity conflict.")
            cursor.execute("""INSERT INTO vault_private.vault_conversation_segments
              (segment_id,conversation_id,user_id,workspace_id,ordinal,state)
              VALUES (%s,%s,%s,%s,0,'sealed') ON CONFLICT(user_id,workspace_id,conversation_id,ordinal) DO NOTHING""",
              (snapshot.segment_id,voice_session_id,principal.user_id,principal.workspace_id))
            cursor.execute("""SELECT segment_id,state FROM vault_private.vault_conversation_segments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND ordinal=0 FOR SHARE""",
              (principal.user_id,principal.workspace_id,voice_session_id))
            if cursor.fetchone()!=(snapshot.segment_id,"sealed"):
                raise ReviewConflictError("Voice review segment identity conflict.")
            return snapshot

    def current(self, cursor, principal, snapshot):
        # No default True: reconstruct from locked current canonical rows and catalog.
        if snapshot.segment_id!="voice-review:"+snapshot.conversation_id:
            return False
        return source_fingerprint(self._read(cursor,principal,snapshot.conversation_id)) == source_fingerprint(snapshot)

    def _read(self,cursor,principal,voice_session_id,bound_existing=None):
        ConversationRepository._require_authority(cursor,principal)
        scope = (principal.user_id,principal.workspace_id,voice_session_id)
        cursor.execute("""SELECT status,transcript_capture_state FROM vault_private.vault_voice_sessions
          WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s FOR SHARE""",scope)
        session = cursor.fetchone()
        if session is None or session[0] not in {"closed","failed","lost"}:
            raise ReviewConflictError("Owned finalized Voice session required.")
        if session[1]=="incomplete":
            raise ReviewConflictError("Incomplete transcript capture cannot be reviewed.")
        cursor.execute("""SELECT entry_id,entry_index,role,event_type,text_content FROM vault_private.vault_transcript_entries
          WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s ORDER BY entry_index LIMIT 1025 FOR SHARE""",scope)
        entries = cursor.fetchall()
        if len(entries)>1024:
            raise ReviewConflictError("Voice transcript requires bounded review partitioning.")
        sources,finals = [],{}
        for identity,index,role,event,text in entries:
            if not text.strip():
                continue
            kind = ("user_final" if event in USER_FINAL else "user_capture") if role=="user" else (
                "assistant_final" if event in ASSISTANT_FINAL else "assistant_capture") if role=="assistant" else "tool_result"
            sources.append(dict(source_id=identity,kind=kind,text=text))
            if kind=="user_final":
                finals[index]=(identity,sha256(text.strip().encode()).hexdigest())
        cursor.execute("""SELECT provider_event_id,evidence_json FROM vault_private.vault_voice_provider_events
          WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s AND evidence_json<>'{}'::jsonb
          ORDER BY provider_event_id LIMIT 1025 FOR SHARE""",scope)
        provider_rows = cursor.fetchall()
        if len(provider_rows)>1024:
            raise ReviewConflictError("Voice provider evidence requires bounded review partitioning.")
        proposals = {}
        for event_id,evidence in provider_rows:
            for proposal in evidence.get("proposals",[]):
                original = dict(origin=evidence["origin"],response_id=evidence["response_id"],**proposal)
                key = json.dumps(original,sort_keys=True,ensure_ascii=False)
                proposals.setdefault(proposal["call_id"],{})[key] = (event_id,original)
        cursor.execute("""SELECT i.invocation_id,i.tool_name,i.effect_class,i.state,i.arguments_redacted,
            i.source_utterance_index,i.source_utterance_fingerprint,r.result_json
            ,i.tool_call_id
          FROM vault_private.vault_voice_tool_invocations i LEFT JOIN vault_private.vault_voice_tool_results r
            ON r.invocation_id=i.invocation_id AND r.user_id=i.user_id AND r.workspace_id=i.workspace_id
          WHERE i.user_id=%s AND i.workspace_id=%s AND i.voice_session_id=%s
          ORDER BY i.prepared_at,i.invocation_id LIMIT 257 FOR SHARE OF i""",scope)
        rows = cursor.fetchall()
        if len(rows)>256:
            raise ReviewConflictError("Voice tool history requires bounded review partitioning.")
        current = {d.name:d for d in self.catalog.definitions_for(AgentKind.VOICE,
            user_id=principal.user_id,workspace_id=principal.workspace_id)}
        observations,capabilities = [],{}
        for identity,name,effect,state,args,index,fingerprint,result,call_id in rows:
            definition = current.get(name)
            capability = definition.tool_id if definition is not None and definition.effect_class==effect else None
            if capability:
                capabilities[capability] = dict(capability_id=capability,description=definition.description,effect=effect)
            request_id = "request:"+identity
            sources.append(dict(source_id=request_id,kind="tool_request",text=json.dumps(
                dict(tool=name,effect=effect,arguments=redact_evidence(args)),sort_keys=True,ensure_ascii=False)))
            proposal_id = request_id
            originals = tuple(proposals.get(call_id,{}).values())
            if len(originals)==1 and originals[0][1]["name"]==name:
                event_id,original = originals[0]
                proposal_id = "provider-proposal:"+sha256((event_id+":"+identity).encode()).hexdigest()
                sources.append(dict(source_id=proposal_id,kind="model_proposal",
                    text=json.dumps(dict(captured_provider=original,executed_request_source_id=request_id,
                        executed_arguments=redact_evidence(args)),sort_keys=True,ensure_ascii=False)))
            result_id,report = None,"none"
            if result is not None:
                text = json.dumps(redact_evidence(result),sort_keys=True,ensure_ascii=False)
                if len(text)<=20000:
                    result_id="result:"+identity
                    sources.append(dict(source_id=result_id,kind="tool_result",text=text))
                    report = "error" if result.get("isError",False) else "non_error"
                else:
                    report="truncated"  # Never misrepresent a clipped result as complete.
            final = finals.get(index)
            observations.append(dict(point_id=identity,final_source_id=final[0] if final and final[1]==fingerprint else None,
                proposal_source_id=proposal_id,result_source_id=result_id,capability_id=capability,
                execution={"succeeded":"completed","failed":"failed","invoking":"invoking",
                           "prepared":"not_requested","effect_unknown":"effect_unknown"}[state],
                tool_report=report,request_outcome="unknown",context_source_ids=[],feedback_source_ids=[],
                reasoning_source_ids=[],answer_source_id=None))
        # Direct user turns are also decision points, without inventing answer causality.
        attributed = {p["final_source_id"] for p in observations}
        for index,(identity,_) in finals.items():
            if identity not in attributed:
                observations.append(dict(point_id="turn:"+identity,final_source_id=identity,proposal_source_id=None,
                    result_source_id=None,capability_id=None,execution="not_requested",tool_report="none",
                    request_outcome="unknown",context_source_ids=[],feedback_source_ids=[],reasoning_source_ids=[],answer_source_id=None))
        # The existing ordered transcript supplies request/answer boundaries.
        # Following user turns are feedback CANDIDATES: the shared analyst must
        # decide whether they express approval, correction or an unrelated request.
        ordered_finals = sorted(finals)
        for point in observations:
            request = point["final_source_id"]
            index = next((i for i, (identity, _) in finals.items() if identity == request), None)
            if index is None:
                continue
            next_index = next((i for i in ordered_finals if i > index), None)
            answers = [identity for identity, entry_index, role, event, text in entries
                if entry_index > index and (next_index is None or entry_index < next_index)
                and role == "assistant" and event in ASSISTANT_FINAL and text.strip()]
            # Multiple final responses cannot be attributed to an individual call
            # merely by position. Keep ambiguity for the shared analyst.
            if len(answers) == 1:
                point["answer_source_id"] = answers[0]
                if next_index is not None:
                    feedback_id = "feedback:" + finals[next_index][0]
                    if not any(s["source_id"] == feedback_id for s in sources):
                        text = next(row[4] for row in entries if row[0] == finals[next_index][0])
                        sources.append(dict(source_id=feedback_id, kind="user_feedback", text=text))
                    point["feedback_source_ids"] = [feedback_id]
        coverage = "complete" if (session[1] == "acknowledged" and observations
            and all(p["final_source_id"] is not None for p in observations)
            and any(s["kind"] == "assistant_final" for s in sources)
            and all(p["answer_source_id"] is not None for p in observations if p["proposal_source_id"] is not None)
            and all(s["kind"] not in {"user_capture", "assistant_capture"} for s in sources)) else "unknown"
        existing_source = getattr(self, "existing_source", None)
        existing = existing_source._existing(cursor, principal, voice_session_id,
            "voice-review:" + voice_session_id, bound_existing) if existing_source is not None else []
        snapshot = ReviewInput.model_validate(dict(conversation_id=voice_session_id,
            segment_id="voice-review:"+voice_session_id,coverage=coverage,sources=sources,observations=observations,
            capabilities=sorted(capabilities.values(),key=lambda c:c["capability_id"]),existing_decisions=existing))
        if sources:
            source_fingerprint(snapshot)  # Reject overflow before identity/model/checkpoint writes.
        return snapshot
