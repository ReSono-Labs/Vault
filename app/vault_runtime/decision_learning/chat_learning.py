"""Completed Chat review joins the existing inactive publisher; never reviews again."""
from dataclasses import asdict
import logging
import json
from hashlib import sha256

from app.vault_runtime.decision_routing.example_index import ensure_example_index
from .service import DecisionLearningService
from .repository import ReviewConflictError, source_fingerprint
from .reviewer import ProceduralReview,ReviewOutput,REVIEW_CONTRACT_VERSION,_validate_output
from .activation import NoQualifiedRuleError


class ChatLearningPublisher:
    def __init__(self,*,database_url,repository,embedder_factory,activator=None):
        self.database_url = database_url
        self.activator = activator
        self.require_reconciliation = False
        self.service = DecisionLearningService(reviewer=None,repository=repository,
            embedder_factory=embedder_factory,lease_seconds=180)

    def ensure_index(self):
        import psycopg
        with psycopg.connect(self.database_url,connect_timeout=5,autocommit=True) as connection:
            connection.execute("SET statement_timeout='120s'")
            ensure_example_index(connection)

    def rebuild(self, *, principal, source, expected_epoch, request_key):
        """Recompile retained qualified reviews using the SAME publisher/compiler.

        Prepare vectors before locking. All derived replacement, source fences,
        qualification and activation then share one transaction. Original reviews,
        conversations, factual memory and suppressions are never deleted.
        """
        if (self.activator is None or type(expected_epoch) is not int or expected_epoch<0
                or not isinstance(request_key,str) or not 1<=len(request_key)<=128
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in request_key)):
            raise ValueError('Scoped rebuild key and expected activation epoch required.')
        repository=self.service.repository
        scope=(principal.user_id,principal.workspace_id)
        policy=f'rebuild:{request_key}:{expected_epoch}'
        with repository._connect() as connection,connection.cursor() as cursor:
            repository._require_authority(cursor,principal)
            cursor.execute('SELECT generation_id,epoch,policy_version FROM vault_private.vault_decision_activations '
                'WHERE user_id=%s AND workspace_id=%s',scope)
            pointer=cursor.fetchone()
            if pointer and pointer[2]==policy:
                return dict(state='rebuilt',generationId=pointer[0],activationEpoch=pointer[1],alreadyCompleted=True)
            if (pointer[1] if pointer else 0)!=expected_epoch:
                raise ReviewConflictError('Active catalog changed before rebuild.')
            cursor.execute("""SELECT review_id,conversation_id,segment_id,source_snapshot_fingerprint,
              model,assessments_json,proposals_json,output_fingerprint FROM vault_private.vault_decision_reviews
              WHERE user_id=%s AND workspace_id=%s AND state='completed' AND learner_contract_version=%s
              ORDER BY created_at,review_id LIMIT 1025""",(*scope,REVIEW_CONTRACT_VERSION))
            rows=cursor.fetchall()
            if len(rows)>1024:
                raise ReviewConflictError('Retained review rebuild requires bounded batches.')
            cursor.execute("""SELECT DISTINCT example_text,embedding::text FROM vault_private.vault_decision_examples
              WHERE user_id=%s AND workspace_id=%s AND provider='ollama' AND model='embeddinggemma:300m'
                AND dimensions=768 AND vector_dims(embedding)=768 AND vector_norm(embedding)>0
                AND embedding_fingerprint=encode(sha256(convert_to(example_text,'UTF8')),'hex') LIMIT 8193""",scope)
            vectors={text:json.loads(vector) for text,vector in cursor.fetchall()}
            if len(vectors)>8192:
                raise ReviewConflictError('Rebuild vector preparation requires bounded batches.')
        reviews,skipped,texts=[],[],set()
        for identity,conversation,segment,fingerprint,model,assessments,proposals,output_hash in rows:
            try:
                snapshot=source.load_segment(principal,conversation,segment)
                if snapshot is None or snapshot.coverage!='complete' or source_fingerprint(snapshot)!=fingerprint:
                    raise ReviewConflictError('Historical source no longer qualifies.')
                output=ReviewOutput.model_validate(dict(contract_version=REVIEW_CONTRACT_VERSION,
                    assessments=assessments,proposals=proposals))
                if sha256(output.model_dump_json().encode()).hexdigest()!=output_hash:
                    raise ReviewConflictError('Retained review output changed.')
                _validate_output(output,snapshot)
            except (ValueError,RuntimeError,KeyError,TypeError):
                skipped.append(identity)
                continue
            changing=[p for p in output.proposals if p.disposition in {'create','revise','add_example'}]
            if not changing:
                continue
            points={p.point_id:p for p in snapshot.observations}
            sources={s.source_id:s for s in snapshot.sources}
            for proposal in changing:
                texts.update(sources[points[p].final_source_id].text for p in proposal.point_ids)
                texts.update(proposal.examples)
            reviews.append((identity,snapshot,ProceduralReview(fingerprint,model,output)))
        missing=texts-vectors.keys()
        if missing:
            embedder=self.service.embedder_factory(*scope)
            if embedder is None or getattr(embedder,'model_key',None)!='embeddinggemma:300m':
                raise ReviewConflictError('Current rebuild embedding provider unavailable.')
            from app.vault_runtime.memory_search.postgres import vector_literal
            for text in sorted(missing):
                vector=embedder.embed(text)
                vector_literal(vector)
                vectors[text]=vector
        with repository._connect() as connection,connection.cursor() as cursor:
            repository._require_authority(cursor,principal)
            cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,73102715))',
                (json.dumps(scope,separators=(',',':')),))
            cursor.execute('SELECT generation_id,epoch,policy_version FROM vault_private.vault_decision_activations '
                'WHERE user_id=%s AND workspace_id=%s FOR UPDATE',scope)
            pointer=cursor.fetchone()
            if pointer and pointer[2]==policy:
                return dict(state='rebuilt',generationId=pointer[0],activationEpoch=pointer[1],alreadyCompleted=True)
            if (pointer[1] if pointer else 0)!=expected_epoch:
                raise ReviewConflictError('Active catalog changed during rebuild preparation.')
            cursor.execute('SELECT pg_advisory_xact_lock_shared(hashtextextended(%s,81008))',(principal.workspace_id,))
            # Invalidation triggers retain the epoch. MVCC keeps this entire
            # replacement invisible until its final successful commit.
            cursor.execute('DELETE FROM vault_private.vault_decision_generations WHERE user_id=%s AND workspace_id=%s',scope)
            compiled=None
            for identity,snapshot,review in reviews:
                result=self.service.publish_completed(principal,snapshot,review_id=identity,review=review,
                    _connection=connection,prepared_vectors=vectors)
                if compiled is not None:
                    self.activator._merge(cursor,scope,compiled,result.generation_id)
                else:
                    cursor.execute("""SELECT 1 FROM vault_private.vault_decision_definitions
                      WHERE user_id=%s AND workspace_id=%s AND generation_id=%s AND version<>1 LIMIT 1""",
                      (*scope,result.generation_id))
                    if cursor.fetchone():
                        raise ReviewConflictError('Retained revision lacks its qualified predecessor.')
                compiled=result.generation_id
            if compiled is not None:
                current=self.activator.current(principal,_connection=connection)
                try:
                    with connection.transaction():
                        self.activator.activate(principal,generation_id=compiled,
                            expected_epoch=current.epoch,policy_version=policy,_connection=connection,_replacement=True)
                except NoQualifiedRuleError:
                    # The replacement has no currently qualified read-only rule.
                    # Keep the pointer empty, never reactivate a stale predecessor.
                    pass
            cursor.execute("""INSERT INTO vault_private.vault_decision_activations
              (user_id,workspace_id,generation_id,epoch,policy_version,actor_user_id)
              VALUES(%s,%s,NULL,1,%s,%s) ON CONFLICT(user_id,workspace_id) DO UPDATE
              SET policy_version=EXCLUDED.policy_version,changed_at=now()""",(*scope,policy,principal.user_id))
            final=self.activator.current(principal,_connection=connection)
            return dict(state='rebuilt',generationId=final.generation_id,activationEpoch=final.epoch,
                reviewCount=len(reviews),unqualifiedReviewIds=skipped,alreadyCompleted=False)

    def __call__(self,*,principal,snapshot,review_id,review):
        if snapshot.coverage!="complete":
            return {"state":"analysis_only"}
        if not any(p.disposition in {"create","add_example","revise"} for p in review.output.proposals):
            return {"state":"no_change"}
        try:
            epoch = self.service.repository.reconciliation_epoch(principal,review_id) if self.require_reconciliation else None
            if self.require_reconciliation:
                pointer = self.activator.current(principal)
                if epoch is None:
                    raise ValueError("Reconciliation checkpoint required before publication.")
                # Already active retry is acknowledged below; a changed catalog
                # cannot publish a new generation against unreviewed rules.
                with self.service.repository._connect() as connection,connection.cursor() as cursor:
                    self.service.repository._require_authority(cursor,principal)
                    cursor.execute("""SELECT generation_id FROM vault_private.vault_decision_generations
                      WHERE user_id=%s AND workspace_id=%s AND review_id=%s""",
                      (principal.user_id,principal.workspace_id,review_id))
                    built = cursor.fetchone()
                if pointer.epoch!=epoch and (not built or pointer.generation_id!=built[0]):
                    raise ValueError("Catalog changed after reconciliation.")
            self.ensure_index()
            result = self.service.publish_completed(principal,snapshot,review_id=review_id,review=review)
        except Exception:
            logging.getLogger("vault.decision_learning").warning("decision_publication_pending")
            raise
        logging.getLogger("vault.decision_learning").info(
            "decision_generation state=%s proposals=%s embedded=%s pending=%s",
            result.state,result.proposal_count,result.embedded_count,result.pending_embeddings)
        response = asdict(result)
        if self.activator is not None and result.state=="generation_built_inactive":
            try:
                pointer = self.activator.current(principal)
                if pointer.generation_id!=result.generation_id:
                    pointer = self.activator.activate(principal,generation_id=result.generation_id,
                        expected_epoch=epoch if self.require_reconciliation else pointer.epoch,
                        policy_version="automatic-qualified-read-only-v1")
                response.update(state="generation_active_read_only",activation_epoch=pointer.epoch)
            except Exception:
                response["activation_state"] = "pending_qualification"
                logging.getLogger("vault.decision_learning").warning("decision_activation_pending")
        return response
