"""Ended Chat adapter into the existing factual reviewer and canonical memory."""
import json
import logging
from dataclasses import asdict
from hashlib import sha256

from psycopg.types.json import Jsonb

from app.vault_runtime.conversation.repository import ConversationRepository
from .openai_reviewer import OpenAIMemoryReviewer,MemoryReviewOverflow
from .contracts import REVIEWER_CONTRACT_VERSION, MemoryCandidate, MemoryReview, ReviewedMemoryCandidate
from .evidence import redact_evidence
from .pipeline import MemoryPipeline
from .analysis_spans import source_reference
from .analysis_windows import bounded_review,decode_review,ANALYSIS_CONTRACT


class ChatMemoryLearning(ConversationRepository):
    def __init__(self, *, database_url, memories, voice_learning, runtime_store, attachments=None):
        super().__init__(database_url=database_url)
        self.memories, self.voice_learning, self.runtime_store = memories, voice_learning, runtime_store
        self.attachments=attachments

    def ensure_schema(self):
        statement = """CREATE TABLE IF NOT EXISTS vault_private.vault_chat_memory_reviews (
          user_id text NOT NULL, workspace_id text NOT NULL, conversation_id text NOT NULL,
          segment_id text NOT NULL, source_fingerprint text NOT NULL CHECK(length(source_fingerprint)=64),
          reviewer_model text NOT NULL, reviewer_contract_version integer NOT NULL,
          summary text NOT NULL, dispositions_json jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY(user_id,workspace_id,conversation_id,segment_id),
          FOREIGN KEY(user_id,workspace_id,conversation_id,segment_id) REFERENCES
            vault_private.vault_conversation_segments(user_id,workspace_id,conversation_id,segment_id)
            ON DELETE CASCADE)"""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement)
            step_statement="""CREATE TABLE IF NOT EXISTS vault_private.vault_chat_memory_analysis_steps (
              user_id text NOT NULL,workspace_id text NOT NULL,conversation_id text NOT NULL,segment_id text NOT NULL,
              step_key text NOT NULL,source_fingerprint text NOT NULL,input_fingerprint text NOT NULL,
              provider text NOT NULL,model text NOT NULL,analysis_contract integer NOT NULL,
              output_json jsonb NOT NULL CHECK(octet_length(output_json::text)<=1048576),
              PRIMARY KEY(user_id,workspace_id,conversation_id,segment_id,step_key),
              FOREIGN KEY(user_id,workspace_id,conversation_id,segment_id) REFERENCES
                vault_private.vault_conversation_segments(user_id,workspace_id,conversation_id,segment_id) ON DELETE CASCADE)"""
            cursor.execute(step_statement)
            upgrades=(
                "ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS state text NOT NULL DEFAULT 'completed' CHECK(state IN ('reviewed','completed'))",
                "ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS provider text",
                "ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS review_json jsonb",
                "ALTER TABLE vault_private.vault_chat_memory_reviews ADD COLUMN IF NOT EXISTS coverage_json jsonb",
            )
            for upgrade in upgrades:
                cursor.execute(upgrade)
            cursor.execute("""INSERT INTO vault_private.local_schema_metadata(schema_key,schema_fingerprint)
              VALUES('chat_memory_reviews_v1',%s) ON CONFLICT(schema_key) DO UPDATE SET
              schema_fingerprint=EXCLUDED.schema_fingerprint,updated_at=now()""",
              (sha256((statement+"\n"+step_statement+"\n"+"\n".join(upgrades)).encode()).hexdigest(),))

    def _model_identity(self,principal):
        credentials=self.voice_learning._credentials
        provider=credentials.selected_provider(user_id=principal.user_id,workspace_id=principal.workspace_id)
        _,model=credentials.background_access(user_id=principal.user_id,workspace_id=principal.workspace_id,
            provider_key=provider)
        return provider,model

    def previous_summary(self,principal,conversation_id,segment_id):
        """Use the already-completed preceding review; no model or history replay."""
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT r.segment_id,r.source_fingerprint,r.reviewer_contract_version,r.summary
              FROM vault_private.vault_chat_memory_reviews r
              JOIN vault_private.vault_conversation_segments s USING(user_id,workspace_id,conversation_id,segment_id)
              JOIN vault_private.vault_conversation_segments current
                ON current.user_id=s.user_id AND current.workspace_id=s.workspace_id
                AND current.conversation_id=s.conversation_id AND current.segment_id=%s
              WHERE r.user_id=%s AND r.workspace_id=%s AND r.conversation_id=%s
                AND r.state='completed' AND s.state='sealed' AND s.ordinal<current.ordinal
              ORDER BY s.ordinal DESC LIMIT 1""",(segment_id,*self._scope(principal,conversation_id)))
            row=cursor.fetchone()
        return dict(segmentId=row[0],sourceFingerprint=row[1],reviewerContractVersion=row[2],text=row[3][:4096]) if row else None

    def _read(self,cursor,principal,conversation_id,segment_id):
        self._require_authority(cursor,principal)
        scope=(*self._scope(principal,conversation_id),segment_id)
        cursor.execute("""SELECT state FROM vault_private.vault_conversation_segments
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s FOR SHARE""",scope)
        row=cursor.fetchone()
        if row is None or row[0]!="sealed":
            raise ValueError("Sealed owned Chat source required for factual review.")
        turns,last=[], -1
        while True:
            cursor.execute("""SELECT turn_id,input_text,state,source_coverage,ordinal FROM vault_private.vault_conversation_turns
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s AND ordinal>%s
              ORDER BY ordinal LIMIT 256 FOR SHARE""",(*scope,last))
            page=cursor.fetchall()
            if not page:
                break
            turns.extend(page)
            last=page[-1][4]
        if not turns or any(t[2:4]!=("completed","complete") for t in turns):
            raise ValueError("Complete Chat capture required for factual review.")
        entries=[]
        for turn_id,text,*_ in turns:
            entries.append(("chat-final:"+turn_id,"user",text))
            if self.attachments is not None:
                documents,_,_=self.attachments.learning_inputs(cursor,principal,conversation_id,[turn_id])
                entries.extend(documents)
            results,offset=[],0
            while True:
                cursor.execute("""SELECT i.invocation_id,r.result_json FROM vault_private.vault_voice_tool_invocations i
                  JOIN vault_private.vault_voice_tool_results r USING(user_id,workspace_id,invocation_id)
                  WHERE i.user_id=%s AND i.workspace_id=%s AND i.conversation_id=%s AND i.turn_id=%s
                  ORDER BY i.prepared_at,i.invocation_id LIMIT 256 OFFSET %s FOR SHARE OF i,r""",
                  (*self._scope(principal,conversation_id),turn_id,offset))
                page=cursor.fetchall()
                if not page:
                    break
                results.extend(page)
                offset+=len(page)
            entries.extend(("chat-result:"+identity,"tool",json.dumps(redact_evidence(result),ensure_ascii=False,sort_keys=True))
                           for identity,result in results)
            cursor.execute("""SELECT sequence,payload FROM vault_private.vault_conversation_events
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s
              AND kind='assistant_final' ORDER BY sequence FOR SHARE""",
              (*self._scope(principal,conversation_id),turn_id))
            answers=cursor.fetchall()
            if len(answers)!=1:
                raise ValueError("Original final Chat answer required for factual review.")
            entries.append((f"chat-event:{turn_id}:{answers[0][0]}","assistant",answers[0][1]["text"]))
        fingerprint=sha256(json.dumps(entries,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        return entries,fingerprint

    def _analysis_step(self,connection,principal,conversation_id,segment_id,fingerprint,provider,model,key,text,produce):
        scope=(*self._scope(principal,conversation_id),segment_id)
        input_hash=sha256(text.encode()).hexdigest()
        binding=(fingerprint,input_hash,provider,model,ANALYSIS_CONTRACT)
        with connection.transaction(),connection.cursor() as cursor:
            _,current=self._read(cursor,principal,conversation_id,segment_id)
            if current!=fingerprint or self._model_identity(principal)!=(provider,model):
                raise ValueError("Factual step source/model changed.")
            cursor.execute("""SELECT source_fingerprint,input_fingerprint,provider,model,analysis_contract,output_json
              FROM vault_private.vault_chat_memory_analysis_steps
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s AND step_key=%s""",(*scope,key))
            row=cursor.fetchone()
            if row:
                if row[:5]!=binding:
                    raise ValueError("Checkpointed factual step binding changed.")
                return row[5]
        output=produce()
        if len(json.dumps(output,ensure_ascii=False).encode())>750000:
            raise ValueError("Factual step checkpoint exceeds its bounded output.")
        with connection.transaction(),connection.cursor() as cursor:
            _,current=self._read(cursor,principal,conversation_id,segment_id)
            if current!=fingerprint or self._model_identity(principal)!=(provider,model):
                raise ValueError("Factual step changed during model work.")
            cursor.execute("""INSERT INTO vault_private.vault_chat_memory_analysis_steps
              (user_id,workspace_id,conversation_id,segment_id,step_key,source_fingerprint,input_fingerprint,
               provider,model,analysis_contract,output_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (*scope,key,*binding,Jsonb(output)))
        return output

    def finalize(self,*,principal,conversation_id,segment_id):
        connection=self.runtime_store.execution_lock("chat-memory:"+segment_id)
        scope=(*self._scope(principal,conversation_id),segment_id)
        try:
            with connection.transaction(),connection.cursor() as cursor:
                entries,fingerprint=self._read(cursor,principal,conversation_id,segment_id)
                cursor.execute("""SELECT source_fingerprint,reviewer_contract_version,state,provider,reviewer_model,review_json
                  FROM vault_private.vault_chat_memory_reviews
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",scope)
                existing=cursor.fetchone()
                if existing:
                    if existing[:2]!=(fingerprint,REVIEWER_CONTRACT_VERSION):
                        raise ValueError("Completed factual source cannot be replaced.")
                    if existing[2]=="completed":
                        return {"state":"completed","alreadyCompleted":True}
            learning=self.voice_learning
            provider,model=self._model_identity(principal)
            reviewer=(learning._reviewer_factory(principal.user_id,principal.workspace_id)
                if learning._reviewer_factory else OpenAIMemoryReviewer(credentials=learning._credentials,
                    user_id=principal.user_id,workspace_id=principal.workspace_id))
            if self.attachments is not None:
                with connection.transaction(),connection.cursor() as cursor:
                    cursor.execute("""SELECT turn_id FROM vault_private.vault_conversation_turns
                      WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",scope)
                    turn_ids=[row[0] for row in cursor.fetchall()]
                    _,parts,_=self.attachments.learning_inputs(cursor,principal,conversation_id,turn_ids)
                if parts:
                    reviewer.with_input_parts(parts)
            transcript="\n".join(f"[entryIndex={i}] [{identity}] {role}: {text}"
                for i,(identity,role,text) in enumerate(entries))
            supports_pages=callable(getattr(reviewer,'review_page',None))
            windowed=supports_pages and (
                (existing is not None and (existing[5] or {}).get('windowed')==ANALYSIS_CONTRACT)
                or (existing is None and (len(transcript)>60000 or len(entries)>768 or any(len(e[2])>16384 for e in entries))))
            evidence_by_index=None
            source_refs=None
            if windowed:
                if existing and (existing[3],existing[4])!=(provider,model):
                    raise ValueError("Checkpointed factual model/provider binding changed.")
                review,evidence_by_index,source_refs=bounded_review(entries,reviewer=reviewer,model=model,
                    step=lambda key,text,produce:self._analysis_step(connection,principal,conversation_id,segment_id,
                        fingerprint,provider,model,key,text,produce))
            elif existing:
                if (existing[3],existing[4])!=(provider,model):
                    raise ValueError("Checkpointed factual model/provider binding changed.")
                review=decode_review(existing[5])
            else:
                if len(entries)>768 or any(len(e[2])>16384 for e in entries):
                    raise ValueError("Legacy factual reviewer cannot process unbounded source.")
                try:
                    review=reviewer.review(transcript).validated()
                    needs_pages=supports_pages and len(review.memories)>=32
                except MemoryReviewOverflow:
                    if not supports_pages:
                        raise
                    needs_pages=True
                if needs_pages:
                    windowed=True
                    review,evidence_by_index,source_refs=bounded_review(entries,reviewer=reviewer,model=model,
                        step=lambda key,text,produce:self._analysis_step(connection,principal,conversation_id,segment_id,
                            fingerprint,provider,model,key,text,produce))
            if review.model!=model or self._model_identity(principal)!=(provider,model):
                raise ValueError("Factual review model/provider changed during analysis.")
            pipeline=MemoryPipeline(repository=self.memories,reviewer=reviewer)
            if evidence_by_index is None and any(any(i>=len(entries) for i in c.source_entry_indexes) for c in review.memories):
                raise ValueError("Factual reviewer invented Chat evidence citations.")
            if any(c.memory.subject_id!=principal.user_id for c in review.memories):
                raise ValueError("Factual review subject crossed the current scope.")
            document_indexes=({i for i,ref in source_refs.items() if ref['role']=='document'}
                if source_refs is not None else {i for i,(_,role,_) in enumerate(entries) if role=='document'})
            if any(c.memory.source_authority!='model_derived' and document_indexes.intersection(c.source_entry_indexes)
                   for c in review.memories):
                raise ValueError('External attachment evidence requires model-derived authority.')
            if not existing:
                payload={'windowed':ANALYSIS_CONTRACT} if windowed else asdict(review)
                if len(json.dumps(payload))>150000:
                    raise ValueError("Factual review checkpoint requires bounded processing.")
                with connection.transaction(),connection.cursor() as cursor:
                    _,current_fingerprint=self._read(cursor,principal,conversation_id,segment_id)
                    if current_fingerprint!=fingerprint or self._model_identity(principal)!=(provider,model):
                        raise ValueError("Chat source changed before factual checkpoint.")
                    cursor.execute("""INSERT INTO vault_private.vault_chat_memory_reviews
                      (user_id,workspace_id,conversation_id,segment_id,source_fingerprint,reviewer_model,
                       reviewer_contract_version,summary,dispositions_json,state,provider,review_json)
                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'[]'::jsonb,'reviewed',%s,%s)""",
                      (*scope,fingerprint,model,review.contract_version,review.summary,provider,Jsonb(payload)))
            if evidence_by_index is None:
                evidence_by_index={i:(None,"chat_"+{"user":"user_statement","tool":"tool_result",
                    "assistant":"assistant_statement","document":"document_observation"}[role],text)
                    for i,(_,role,text) in enumerate(entries)}
                source_refs={i:source_reference(identity,role,text) for i,(identity,role,text) in enumerate(entries)}
            suppression_proofs=pipeline.prepare_review_suppression(user_id=principal.user_id,
                workspace_id=principal.workspace_id,review=review,evidence_by_index=evidence_by_index,
                source_refs_by_index=source_refs,step=lambda key,text,produce:self._analysis_step(connection,
                    principal,conversation_id,segment_id,fingerprint,provider,model,key,text,produce))
            records,dispositions=[],[]
            with connection.transaction(),connection.cursor() as cursor:
                current,current_fingerprint=self._read(cursor,principal,conversation_id,segment_id)
                if current_fingerprint!=fingerprint or self._model_identity(principal)!=(provider,model):
                    raise ValueError("Chat source changed during factual analysis.")
                if evidence_by_index is None:
                    evidence_by_index={i:(None,"chat_"+{"user":"user_statement","tool":"tool_result",
                        "assistant":"assistant_statement","document":"document_observation"}[role],text) for i,(_,role,text) in enumerate(entries)}
                    source_refs={i:source_reference(identity,role,text) for i,(identity,role,text) in enumerate(current)}
                reconciled=pipeline.reconcile_review(user_id=principal.user_id,workspace_id=principal.workspace_id,
                    source_session_id=segment_id,review=review,evidence_by_index=evidence_by_index,connection=connection,
                    source_refs_by_index=source_refs,suppression_proofs=suppression_proofs)
                for candidate,record in zip(review.memories,reconciled):
                    cited_ids=list(dict.fromkeys(source_refs[i]['sourceId'] for i in candidate.source_entry_indexes))
                    if record is None:
                        dispositions.append(dict(state="suppressed",sourceIds=cited_ids))
                        continue
                    records.append(record)
                    dispositions.append(dict(state=record.lifecycle_status,memoryId=record.memory_id,
                        version=record.current_version,sourceIds=cited_ids))
                outcomes={identity:[] for identity,_,_ in current}
                for disposition in dispositions:
                    for identity in disposition['sourceIds']:
                        outcomes[identity].append(disposition['state'])
                coverage=dict(sourceFingerprint=fingerprint,sourceCount=len(current),
                    sources=[dict(sourceId=identity,outcomes=states or ['reviewed_no_memory_proposal'])
                             for identity,states in outcomes.items()])
                cursor.execute("""UPDATE vault_private.vault_chat_memory_reviews SET state='completed',dispositions_json=%s,coverage_json=%s
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
                    AND state='reviewed' AND source_fingerprint=%s""",(Jsonb(dispositions),Jsonb(coverage),*scope,fingerprint))
                if cursor.rowcount!=1:
                    raise ValueError("Factual publication checkpoint changed.")
            try:
                embedder=learning._embedder_factory(principal.user_id,principal.workspace_id) if learning._embedder_factory else None
            except Exception:
                embedder=None
            pipeline.embed_records(user_id=principal.user_id,workspace_id=principal.workspace_id,
                records=records,embedder=embedder,embedding_provider=getattr(embedder,"provider_key","openai") if embedder else None)
            return {"state":"completed","alreadyCompleted":False,"memoryCount":len(records)}
        finally:
            connection.close()

    def run(self,**kwargs):
        try:
            result=self.finalize(**kwargs)
            logging.getLogger(__name__).info("chat_memory_review_completed",extra=self._log_scope(kwargs,result["state"]))
            return result
        except Exception:
            logging.getLogger(__name__).warning("chat_memory_review_failed",extra=self._log_scope(kwargs,"failed"))
            return {"state":"failed","errorCode":"memory_review_failed"}

    @staticmethod
    def _log_scope(kwargs,state):
        principal=kwargs["principal"]
        return dict(review_state=state,user_id=principal.user_id,workspace_id=principal.workspace_id,
            conversation_id=kwargs["conversation_id"],segment_id=kwargs["segment_id"])
