"""Reference-only projection of a completed Chat prefix; never learns drafts."""
import json
from hashlib import sha256

from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.memory.evidence import redact_evidence
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.conversation.history_projection import assemble_history,history_fingerprint
from app.vault_runtime.tools.strict_json import canonical_json_bytes
from .repository import ReviewConflictError, source_fingerprint
from .reviewer import ReviewInput, REVIEW_CONTRACT_VERSION


def _text(value):
    text = json.dumps(redact_evidence(value), sort_keys=True, ensure_ascii=False)
    if len(text.encode()) > 1048576:
        raise ReviewConflictError("Chat evidence requires bounded review partitioning.")
    return text


def project_chat(*, conversation_id, segment_id, turns, events, invocations, definitions,
                 closed=False, target_turn_ids=None,summary_contexts=None,attachment_evidence=None):
    """Rows are scoped/locked by ChatReviewSource; identities, not timing, link them."""
    if not turns:
        return None
    if len(turns) > 256 or len(events) > 4096 or len(invocations) > 256:
        raise ReviewConflictError("Chat history requires bounded review partitioning.")
    sources, observations, capabilities = [], [], {}
    qualified, history_sources = closed, []
    target_turn_ids = set(target_turn_ids) if target_turn_ids is not None else {row[0] for row in turns}
    current = {d.name: d for d in definitions}
    by_turn = {}
    for turn_id, text, state, coverage, event_count, *_ in turns:
        if state != "completed" or coverage != "complete":
            raise ReviewConflictError("Only completed captured Chat prefixes may be reviewed.")
        source_id = "chat-final:" + turn_id
        sources.append(dict(source_id=source_id, kind="user_final", text=text))
        by_turn[turn_id] = dict(final=source_id, expected=event_count, sequence=0,
            context=[], calls={}, statuses={}, answer=None, answer_text=None,
            terminal=False, reasoning=[], supplied={}, model_captured=False)
    for turn_id, sequence, kind, payload in events:
        turn = by_turn.get(turn_id)
        if turn is None or sequence != turn["sequence"] + 1 or turn["terminal"]:
            raise ReviewConflictError("Chat capture is noncontiguous or ambiguous.")
        turn["sequence"] = sequence
        source_id = f"chat-event:{turn_id}:{sequence}"
        if kind == "context":
            version=payload.get('captureVersion')
            current_row=next(row for row in turns if row[0]==turn_id)
            local_segment=current_row[6] if len(current_row)>6 else None
            prefix = []
            for row in turns:
                identity,text = row[:2]
                if version!=3 or len(row)>6 and row[6]==local_segment:
                    prefix.append((identity,text,"running" if identity==turn_id else "completed",
                        None if identity==turn_id else by_turn[identity]["answer_text"]))
                if identity==turn_id:
                    break
            prior = {row[0] for row in prefix[:-1]}
            historical_results = [(r[1],r[2],r[3],r[5],r[7]) for r in invocations if r[1] in prior]
            supplied_ids={row[0] for row in prefix}
            actual = assemble_history(prefix,[row for row in history_sources if row[0] in supplied_ids],historical_results)
            handoff=payload.get('previousSummary')
            valid_handoff=(handoff is None or isinstance(handoff,dict) and summary_contexts is not None
                and summary_contexts.get(handoff.get('segmentId'))==handoff)
            captured = (version in {2,3}
                and (version==2 or local_segment is not None and payload.get('historySegmentId')==local_segment
                    and 'previousSummary' in payload and valid_handoff)
                and payload.get("historyTurnIds")==[r[0] for r in prefix]
                and payload.get("historyFingerprint")==history_fingerprint(actual)
                and type(payload.get("suppliedTools")) is list)
            # Visual/document inputs require original input qualification; metadata
            # alone must never activate an attachment-dependent learned rule.
            expected_attachments=[]
            if attachment_evidence is not None:
                expected_attachments=[dict(meta,turnId=identity) for identity,_,_,_ in prefix
                                      for meta in attachment_evidence[2].get(identity,[])]
            actual_attachments=payload.get('attachments',[])
            attachment_match=(actual_attachments==expected_attachments
                and (not actual_attachments or attachment_evidence is not None))
            qualified = qualified and captured and not turn["context"] and attachment_match
            if captured:
                turn["supplied"] = {d["name"]:d for d in payload["suppliedTools"]}
            sources.append(dict(source_id=source_id, kind="memory_context", text=_text(payload)))
            turn["context"].append(source_id)
            if attachment_match and attachment_evidence is not None:
                turn['context'].extend('attachment:'+a['id']+':'+a['hash'] for a in actual_attachments)
        elif kind == "model_response":
            turn["model_captured"] = True
            history_sources.append((turn_id,sequence,kind,payload))
            qualified = qualified and bool(turn["context"])
            if payload.get("origin") != "server_sdk":
                raise ReviewConflictError("Original Chat model capture required.")
            # Summaries in this response are available to its calls, not prior calls.
            summaries = [item for item in payload.get("output", ()) if item.get("type") == "reasoning"]
            summary_ids = []
            if any(item.get("summary") for item in summaries):
                summary_id = source_id + ":summary"
                sources.append(dict(source_id=summary_id, kind="reasoning_summary", text=_text(summaries)))
                summary_ids.append(summary_id)
            for item in payload.get("output", ()):
                if item.get("type") != "function_call" or item.get("name") == "present_ui":
                    continue  # Display-only cards are not tool decisions to learn from.
                call_id = item["call_id"]
                if call_id in turn["calls"]:
                    raise ReviewConflictError("Original Chat call identity was repeated.")
                proposal_id = "chat-proposal:" + sha256((source_id+":"+call_id).encode()).hexdigest()
                sources.append(dict(source_id=proposal_id, kind="model_proposal", text=_text(item)))
                turn["calls"][call_id] = dict(name=item["name"], proposal=proposal_id,
                    arguments_hash=item.get("arguments_sha256"),
                    context=tuple(turn["context"]), reasoning=tuple(turn["reasoning"] + summary_ids))
            turn["reasoning"].extend(summary_ids)
        elif kind == "assistant_final":
            if turn["answer"] is not None:
                raise ReviewConflictError("Ambiguous Chat final answer.")
            sources.append(dict(source_id=source_id, kind="assistant_final", text=payload["text"]))
            turn["answer"] = source_id
            turn["answer_text"] = payload["text"]
        elif kind == "tool_status":
            history_sources.append((turn_id,sequence,kind,payload))
            call_id = payload.get("callId")
            if call_id is not None:
                if call_id not in turn["calls"] or payload.get("name") != turn["calls"][call_id]["name"]:
                    raise ReviewConflictError("Chat tool status lacks original call linkage.")
                turn["statuses"][call_id] = payload.get("state")
        elif kind == "terminal":
            if payload.get("state") != "completed":
                raise ReviewConflictError("Incomplete Chat terminal capture.")
            turn["terminal"] = True
    attributed, executed = set(), set()
    for invocation_id, turn_id, call_id, name, effect, state, arguments, result, *hashes in invocations:
        turn = by_turn.get(turn_id)
        call = turn["calls"].get(call_id) if turn else None
        if call is None or call["name"] != name:
            raise ReviewConflictError("Chat invocation lacks original call linkage.")
        if (turn_id,call_id) in executed:
            raise ReviewConflictError("Chat call has ambiguous invocation ownership.")
        executed.add((turn_id,call_id))
        qualified = qualified and bool(hashes) and type(call["arguments_hash"]) is str and call["arguments_hash"] == hashes[0]
        definition = current.get(name)
        supplied = turn["supplied"].get(name)
        capability = definition.tool_id if (definition and definition.effect_class == effect
            and (not closed or supplied and supplied.get("toolId")==definition.tool_id
                 and supplied.get("effect")==effect and supplied.get("schemaFingerprint")==sha256(
                     canonical_json_bytes(definition.input_schema)).hexdigest())) else None
        if capability:
            capabilities[capability] = dict(capability_id=capability, description=definition.description, effect=effect)
        request_id = "chat-request:" + invocation_id
        sources.append(dict(source_id=request_id, kind="tool_request",
            text=_text(dict(name=name, arguments=arguments))))
        result_id = "chat-result:" + invocation_id if result is not None else None
        if result_id:
            sources.append(dict(source_id=result_id, kind="tool_result", text=_text(result)))
        if turn_id in target_turn_ids:
            observations.append(dict(point_id=invocation_id, final_source_id=turn["final"],
            proposal_source_id=call["proposal"], result_source_id=result_id, capability_id=capability,
            execution={"succeeded":"completed", "failed":"failed", "invoking":"invoking",
                "prepared":"not_requested", "effect_unknown":"effect_unknown"}[state],
            tool_report="none" if result is None else "error" if result.get("isError", False) else "non_error",
            request_outcome="unknown", context_source_ids=call["context"], feedback_source_ids=[],
                reasoning_source_ids=call["reasoning"], answer_source_id=turn["answer"]))
        attributed.add(turn_id)
    for turn_id, turn in by_turn.items():
        qualified = qualified and bool(turn["context"]) and turn["model_captured"]
        if turn["sequence"] != turn["expected"] or not turn["terminal"] or not turn["answer"]:
            raise ReviewConflictError("Chat final source coverage is incomplete.")
        if turn_id not in target_turn_ids:
            continue
        for call_id, call in turn["calls"].items():
            if (turn_id,call_id) in executed:
                continue
            # Denied proposals have no execution-ledger row. Preserve the failed
            # choice without making its absent result look like a successful call.
            denied = turn["statuses"].get(call_id) == "denied"
            observations.append(dict(point_id="chat-point:"+sha256((turn_id+":"+call_id).encode()).hexdigest(),
                final_source_id=turn["final"], proposal_source_id=call["proposal"],
                result_source_id=None, capability_id=None,
                execution="denied" if denied else "not_requested", tool_report="none",
                request_outcome="unknown", context_source_ids=call["context"],
                feedback_source_ids=[], reasoning_source_ids=call["reasoning"], answer_source_id=turn["answer"]))
            attributed.add(turn_id)
        if turn_id not in attributed:
            observations.append(dict(point_id="chat-turn:"+turn_id, final_source_id=turn["final"],
                proposal_source_id=None, result_source_id=None, capability_id=None,
                execution="not_requested", tool_report="none", request_outcome="unknown",
                context_source_ids=turn["context"], feedback_source_ids=[],
                reasoning_source_ids=turn["reasoning"], answer_source_id=turn["answer"]))
    if attachment_evidence is not None:
        sources.extend(dict(source_id=identity,kind='memory_context',text=text)
                       for identity,_,text in attachment_evidence[0])
    snapshot = ReviewInput.model_validate(dict(conversation_id=conversation_id, segment_id=segment_id,
        coverage="complete" if qualified else "unknown", sources=sources, observations=observations,
        capabilities=sorted(capabilities.values(), key=lambda c:c["capability_id"]), existing_decisions=[]))
    source_fingerprint(snapshot)
    return snapshot


class ChatReviewSource(ConversationRepository):
    def __init__(self, *, database_url, catalog, memories=None, attachments=None):
        super().__init__(database_url=database_url)
        self.catalog = catalog
        self.memories = memories
        self.attachments=attachments

    def load(self, principal, conversation_id):
        with self._connect() as connection, connection.cursor() as cursor:
            return self._read(cursor, principal, conversation_id)

    def load_segment(self, principal, conversation_id, segment_id):
        with self._connect() as connection, connection.cursor() as cursor:
            return self._read(cursor,principal,conversation_id,segment_id=segment_id)

    def qualification_report(self,principal,*,after=None,limit=10):
        """Owned read-only historical audit: no model, tool replay or publication."""
        from .voice_source import VoiceReviewSource
        from app.vault_runtime.conversation.contracts import identifier
        if type(limit) is not int or not 1<=limit<=10:
            raise ValueError('Historical audit page size must be between1 and10.')
        if after is not None:
            after=identifier(after)
        scope=(principal.user_id,principal.workspace_id)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT * FROM (
              SELECT 'chat:'||s.segment_id audit_cursor,s.segment_id,s.conversation_id,s.state,NULL::text voice_id
              FROM vault_private.vault_conversation_segments s JOIN vault_private.vault_conversations c
                USING(user_id,workspace_id,conversation_id)
              WHERE s.user_id=%s AND s.workspace_id=%s AND s.state<>'open' AND c.source_voice_session_id IS NULL
              UNION ALL
              SELECT 'voice:'||voice_session_id,'voice-review:'||voice_session_id,voice_session_id,
                CASE WHEN transcript_capture_state='incomplete' THEN 'incomplete' ELSE 'sealed' END,voice_session_id
              FROM vault_private.vault_voice_sessions WHERE user_id=%s AND workspace_id=%s
                AND status IN ('closed','failed','lost')) sources
              WHERE (%s::text IS NULL OR audit_cursor>%s) ORDER BY audit_cursor LIMIT %s""",
              (*scope,*scope,after,after,limit+1))
            rows=cursor.fetchall()
            items=[]
            for audit_cursor,segment,conversation,state,voice_id in rows[:limit]:
                channel='voice' if voice_id else 'chat'
                item=dict(segmentId=segment,conversationId=conversation,channel=channel,
                    classification='insufficient',publicationEligible=False)
                try:
                    if state!='sealed':
                        raise ReviewConflictError('Incomplete historical capture.')
                    snapshot=(VoiceReviewSource(database_url=self._database_url,catalog=self.catalog)._read(cursor,principal,voice_id)
                        if voice_id else self._read(cursor,principal,conversation,segment_id=segment))
                    if snapshot is None:
                        raise ReviewConflictError('Historical source is empty.')
                    if voice_id:
                        cursor.execute("""SELECT provider_key,model_key FROM vault_private.vault_voice_sessions
                          WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s""",(*scope,voice_id))
                        bindings=[dict(provider=r[0],model=r[1],capabilityVersion='unknown') for r in cursor.fetchall()]
                    else:
                        cursor.execute("""SELECT DISTINCT e.payload->>'provider',e.payload->>'model',e.payload->>'captureVersion'
                          FROM vault_private.vault_conversation_events e JOIN vault_private.vault_conversation_turns t
                            USING(user_id,workspace_id,conversation_id,turn_id)
                          WHERE e.user_id=%s AND e.workspace_id=%s AND e.conversation_id=%s AND t.segment_id=%s
                            AND e.kind='context'""",(*scope,conversation,segment))
                        bindings=[dict(provider=r[0],model=r[1],captureVersion=r[2]) for r in cursor.fetchall()]
                    counts={}
                    for source in snapshot.sources:
                        counts[source.kind]=counts.get(source.kind,0)+1
                    linked=sum(p.final_source_id is not None and p.proposal_source_id is not None
                        and p.result_source_id is not None and p.answer_source_id is not None
                        for p in snapshot.observations)
                    item.update(coverage=snapshot.coverage,sourceCounts=counts,capturedBindings=bindings,
                        decisionPointCount=len(snapshot.observations),linkedOutcomeCount=linked,
                        sourceFingerprint=source_fingerprint(snapshot),
                        representativeSourceRefs=[sha256(s.source_id.encode()).hexdigest()[:16] for s in snapshot.sources[:3]],
                        classification=('linked_outcome_eligible' if snapshot.coverage=='complete' and linked
                            else 'transcript_only_tentative'),
                        missingCausalLinks=sum(p.final_source_id is None or p.answer_source_id is None
                            for p in snapshot.observations),
                        feedbackPointCount=sum(bool(p.feedback_source_ids) for p in snapshot.observations),
                        unknownEffectCount=sum(p.execution=='effect_unknown' for p in snapshot.observations),
                        truncatedResultCount=sum(p.tool_report=='truncated' for p in snapshot.observations))
                except (ValueError,RuntimeError,KeyError,TypeError):
                    item['reason']='original_source_unqualified'
                items.append(item)
            return dict(items=items,nextAfter=rows[limit-1][0] if len(rows)>limit else None,
                readOnly=True,providerCalls=False,toolReplay=False,publication=False)

    def review_parts(self,principal,snapshot):
        if self.attachments is None:
            return []
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT turn_id FROM vault_private.vault_conversation_turns
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",
              (*self._scope(principal,snapshot.conversation_id),snapshot.segment_id))
            _,parts,_=self.attachments.learning_inputs(cursor,principal,snapshot.conversation_id,
                [r[0] for r in cursor.fetchall()])
            return parts

    def current(self, cursor, principal, snapshot):
        current = self._read(cursor, principal, snapshot.conversation_id,segment_id=snapshot.segment_id,
            bound_existing=snapshot.existing_decisions)
        return current is not None and source_fingerprint(current) == source_fingerprint(snapshot)

    @staticmethod
    def _definition_description(row):
        return json.dumps(dict(description=row[2],conditions=row[3],required_slots=row[4],
            capabilities=row[5],exclusions=row[6]),ensure_ascii=False,sort_keys=True)

    def _existing(self,cursor,principal,conversation_id,segment_id,bound):
        scope = (principal.user_id,principal.workspace_id)
        if bound is None:
            cursor.execute("""SELECT source_coverage_json FROM vault_private.vault_decision_reviews
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
              AND learner_contract_version=%s ORDER BY created_at,review_id LIMIT 1""",
              (*scope,conversation_id,segment_id,REVIEW_CONTRACT_VERSION))
            prior = cursor.fetchone()
            if prior:
                bound = prior[0].get("existing_decisions",[])
            else:
                cursor.execute("""SELECT d.definition_id,d.version,d.action_description,d.conditions_json,
                  d.required_slots_json,d.capability_refs_json,d.exclusions_json
                  FROM vault_private.vault_decision_activations a JOIN vault_private.vault_decision_generations g
                  USING(user_id,workspace_id,generation_id) JOIN vault_private.vault_decision_definitions d
                  USING(user_id,workspace_id,generation_id) WHERE a.user_id=%s AND a.workspace_id=%s
                  AND g.state='active' AND d.status='active' ORDER BY d.definition_id LIMIT 129""",scope)
                rows = cursor.fetchall()
                if len(rows)>128:
                    raise ReviewConflictError("Existing decision context requires bounded partitioning.")
                bound = [dict(definition_id=r[0],version=r[1],description=self._definition_description(r)) for r in rows]
        result = [d.model_dump(mode="json") if hasattr(d,"model_dump") else d for d in bound]
        for item in result:
            cursor.execute("""SELECT definition_id,version,action_description,conditions_json,
              required_slots_json,capability_refs_json,exclusions_json FROM vault_private.vault_decision_definitions
              WHERE user_id=%s AND workspace_id=%s AND definition_id=%s AND version=%s""",
              (*scope,item["definition_id"],item["version"]))
            if not any(self._definition_description(r)==item["description"] for r in cursor.fetchall()):
                raise ReviewConflictError("Bound existing decision context is no longer available.")
        return result

    def _read(self, cursor, principal, conversation_id,segment_id=None,bound_existing=None):
        self._require_authority(cursor, principal)
        if segment_id == "voice-review:" + conversation_id:
            voice_source = getattr(self, "voice_source", None)
            if voice_source is None:
                raise ReviewConflictError("Voice source adapter unavailable.")
            return voice_source._read(cursor, principal, conversation_id, bound_existing=bound_existing)
        # The segment SHARE lock below fences new submissions (which lock the
        # header then segment). Do not invert that order from the review
        # repository's already-held segment lock by acquiring a header write lock.
        header = self._header(cursor, principal, conversation_id)
        if header is None:
            raise ReviewConflictError("Owned Chat conversation required.")
        scope = self._scope(principal, conversation_id)
        cursor.execute("""SELECT segment_id,state FROM vault_private.vault_conversation_segments
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND state<>'incomplete'
            AND (%s::text IS NULL OR segment_id=%s)
          ORDER BY ordinal DESC LIMIT 1 FOR SHARE""", (*scope,segment_id,segment_id))
        row = cursor.fetchone()
        if row is None:
            raise ReviewConflictError("Current Chat segment unavailable.")
        segment_id = row[0]
        closed = row[1]=="sealed"
        cursor.execute("""SELECT min(ordinal),max(ordinal) FROM vault_private.vault_conversation_turns
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",(*scope,segment_id))
        lower,upper = cursor.fetchone()
        if upper is None:
            return None
        # New session-scoped captures need no unrelated historical payloads to
        # reconstruct their actual model context. Legacy captures keep full-prefix
        # verification; never silently reinterpret them as segment scoped.
        cursor.execute("""SELECT bool_and(EXISTS(SELECT 1 FROM vault_private.vault_conversation_events e
            WHERE e.user_id=t.user_id AND e.workspace_id=t.workspace_id AND e.conversation_id=t.conversation_id
              AND e.turn_id=t.turn_id AND e.kind='context' AND e.payload->>'captureVersion'='3'
              AND e.payload->>'historySegmentId'=t.segment_id))
          FROM vault_private.vault_conversation_turns t
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",(*scope,segment_id))
        lower_bound=lower if cursor.fetchone()[0] else 0
        # Reject oversized canonical capture in SQL before materializing payloads.
        cursor.execute("""SELECT COALESCE(sum(bytes),0) FROM (
          SELECT octet_length(input_text) bytes FROM vault_private.vault_conversation_turns
            WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND ordinal BETWEEN %s AND %s
          UNION ALL SELECT octet_length(e.payload::text) FROM vault_private.vault_conversation_events e
            JOIN vault_private.vault_conversation_turns t USING(user_id,workspace_id,conversation_id,turn_id)
            WHERE e.user_id=%s AND e.workspace_id=%s AND e.conversation_id=%s AND t.ordinal BETWEEN %s AND %s
          UNION ALL SELECT octet_length(r.result_json::text) FROM vault_private.vault_voice_tool_invocations i
            JOIN vault_private.vault_conversation_turns t ON t.user_id=i.user_id AND t.workspace_id=i.workspace_id
              AND t.conversation_id=i.conversation_id AND t.turn_id=i.turn_id
            JOIN vault_private.vault_voice_tool_results r ON r.user_id=i.user_id AND r.workspace_id=i.workspace_id
              AND r.invocation_id=i.invocation_id WHERE i.user_id=%s AND i.workspace_id=%s
              AND i.conversation_id=%s AND t.ordinal BETWEEN %s AND %s
          ) sizes""", (*scope,lower_bound,upper)*3)
        if cursor.fetchone()[0] > 1048576:
            raise ReviewConflictError("Chat evidence requires bounded review partitioning.")
        cursor.execute("""SELECT turn_id,input_text,state,source_coverage,event_sequence,ordinal,segment_id
          FROM vault_private.vault_conversation_turns WHERE user_id=%s AND workspace_id=%s
            AND conversation_id=%s AND ordinal BETWEEN %s AND %s ORDER BY ordinal LIMIT 257 FOR SHARE""", (*scope,lower_bound,upper))
        turns = cursor.fetchall()
        cursor.execute("""SELECT e.turn_id,e.sequence,e.kind,e.payload FROM vault_private.vault_conversation_events e
          JOIN vault_private.vault_conversation_turns t USING(user_id,workspace_id,conversation_id,turn_id)
          WHERE e.user_id=%s AND e.workspace_id=%s AND e.conversation_id=%s AND t.ordinal BETWEEN %s AND %s
          ORDER BY t.ordinal,e.sequence LIMIT 4097 FOR SHARE OF e""", (*scope,lower_bound,upper))
        events = cursor.fetchall()
        cursor.execute("""SELECT i.invocation_id,i.turn_id,i.tool_call_id,i.tool_name,i.effect_class,
            i.state,i.arguments_redacted,r.result_json,i.arguments_sha256 FROM vault_private.vault_voice_tool_invocations i
          JOIN vault_private.vault_conversation_turns t ON t.user_id=i.user_id AND t.workspace_id=i.workspace_id
            AND t.conversation_id=i.conversation_id AND t.turn_id=i.turn_id
          LEFT JOIN vault_private.vault_voice_tool_results r ON r.user_id=i.user_id AND r.workspace_id=i.workspace_id
            AND r.invocation_id=i.invocation_id WHERE i.user_id=%s AND i.workspace_id=%s
            AND i.conversation_id=%s AND t.ordinal BETWEEN %s AND %s ORDER BY t.ordinal,i.prepared_at,i.invocation_id
          LIMIT 257 FOR SHARE OF i""", (*scope,lower_bound,upper))
        invocations = cursor.fetchall()
        summaries={}
        for turn_id,_,kind,payload in events:
            handoff=payload.get('previousSummary') if kind=='context' and payload.get('captureVersion')==3 else None
            if not isinstance(handoff,dict) or not isinstance(handoff.get('segmentId'),str):
                continue
            # Compare original completed review context, not a newly generated
            # summary. Bound it to the actual earlier segment in this conversation.
            cursor.execute("""SELECT r.segment_id,r.source_fingerprint,r.reviewer_contract_version,r.summary
              FROM vault_private.vault_chat_memory_reviews r
              JOIN vault_private.vault_conversation_segments s USING(user_id,workspace_id,conversation_id,segment_id)
              JOIN vault_private.vault_conversation_turns t ON t.user_id=s.user_id AND t.workspace_id=s.workspace_id
                AND t.conversation_id=s.conversation_id AND t.turn_id=%s
              JOIN vault_private.vault_conversation_segments current ON current.user_id=t.user_id
                AND current.workspace_id=t.workspace_id AND current.conversation_id=t.conversation_id AND current.segment_id=t.segment_id
              WHERE r.user_id=%s AND r.workspace_id=%s AND r.conversation_id=%s AND r.segment_id=%s
                AND r.state='completed' AND s.state='sealed' AND s.ordinal<current.ordinal FOR SHARE OF r,s""",
                (turn_id,*scope,handoff['segmentId']))
            summary=cursor.fetchone()
            if summary:
                summaries[summary[0]]=dict(segmentId=summary[0],sourceFingerprint=summary[1],reviewerContractVersion=summary[2],text=summary[3][:4096])
        definitions = self.catalog.metadata_for(AgentKind.VOICE, user_id=principal.user_id,
                                                   workspace_id=principal.workspace_id)
        attachment_evidence=(self.attachments.learning_inputs(cursor,principal,conversation_id,[t[0] for t in turns])
            if self.attachments is not None else None)
        snapshot = project_chat(conversation_id=conversation_id, segment_id=segment_id,
            turns=turns, events=events, invocations=invocations, definitions=definitions,
            closed=closed,target_turn_ids={t[0] for t in turns if t[5]>=lower},summary_contexts=summaries,
            attachment_evidence=attachment_evidence)
        if snapshot is not None and snapshot.coverage=="complete":
            # Historical context stays inspectable, but removed/changed/forgotten
            # canonical facts cannot qualify a new or active procedural rule.
            current = self.memories is not None
            if current:
                from app.vault_runtime.memory.repository import MemoryNotFoundError
                for _,_,kind,payload in events:
                    if kind!="context":
                        continue
                    for captured in payload.get("memories",()):
                        try:
                            memory = self.memories._memory_by_id_cursor(cursor,user_id=principal.user_id,
                                workspace_id=principal.workspace_id,memory_id=captured["memoryId"],lock=True)
                        except MemoryNotFoundError:
                            current = False
                            break
                        if (memory.lifecycle_status!="active" or memory.current_version!=captured["currentVersion"]
                                or memory.content_text!=captured["content"] or memory.domain!=captured["domain"]
                                or memory.source_authority!=captured["authority"]):
                            current = False
                            break
                    if not current:
                        break
            if not current:
                snapshot = ReviewInput.model_validate(dict(snapshot.model_dump(),coverage="unknown"))
        if snapshot is not None:
            existing = self._existing(cursor,principal,conversation_id,segment_id,bound_existing)
            snapshot = ReviewInput.model_validate(dict(snapshot.model_dump(),existing_decisions=existing))
            source_fingerprint(snapshot)
        return snapshot
