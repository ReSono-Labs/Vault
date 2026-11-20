"""Fenced scoped review leases and immutable proposal completion, no activation."""
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.local_identity.models import LocalPrincipal
from .reviewer import ProceduralReview, ReviewInput, ReviewOutput, REVIEW_CONTRACT_VERSION, _validate_input, _validate_output
from .schema import ensure_review_schema


LEASE_RENEW_SECONDS = 30


class ReviewConflictError(RuntimeError):
    code = "decision_review_conflict"


@dataclass(frozen=True, slots=True)
class ReviewClaim:
    review_id: str
    user_id: str
    workspace_id: str
    token: str
    attempt: int
    source_fingerprint: str


def source_fingerprint(snapshot: ReviewInput) -> str:
    # Reject unchecked model_copy/model_construct changes at the durable boundary.
    ReviewInput.model_validate_json(snapshot.model_dump_json())
    _validate_input(snapshot)
    text = snapshot.model_dump_json()
    if len(text.encode()) > 1048576:
        raise ValueError("Bounded review input required.")
    return sha256(text.encode()).hexdigest()


class DecisionReviewRepository:
    def __init__(self, *, database_url: str,
                 source_current: Callable[[object, LocalPrincipal, ReviewInput], bool],
                 connector=None):
        if not callable(source_current):
            raise ValueError("Current qualified source gate is required.")
        self._database_url, self._source_current, self._connector = database_url, source_current, connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_review_schema(cursor)

    def _require_source(self, cursor, principal, snapshot):
        ConversationRepository._require_authority(cursor, principal)
        cursor.execute("""SELECT 1 FROM vault_private.vault_conversation_segments
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
          AND state <> 'incomplete' FOR SHARE""",
          (principal.user_id, principal.workspace_id, snapshot.conversation_id, snapshot.segment_id))
        if cursor.fetchone() is None or self._source_current(cursor, principal, snapshot) is not True:
            raise ReviewConflictError("Qualified current review source is unavailable.")

    def claim(self, principal: LocalPrincipal, snapshot: ReviewInput, *, lease_seconds: int) -> ReviewClaim | None:
        if type(lease_seconds) is not int or lease_seconds < 1:
            raise ValueError("Explicit positive lease duration required.")
        fingerprint = source_fingerprint(snapshot)
        review_id, token = str(uuid4()), str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_source(cursor, principal, snapshot)
                cursor.execute("""INSERT INTO vault_private.vault_decision_reviews
                  (review_id,user_id,workspace_id,conversation_id,segment_id,source_snapshot_fingerprint,
                   learner_contract_version,state,lease_owner,lease_until,attempts,source_coverage_json)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,'running',%s,clock_timestamp()+%s*interval '1 second',1,%s)
                  ON CONFLICT(user_id,workspace_id,conversation_id,segment_id,source_snapshot_fingerprint,learner_contract_version)
                  DO UPDATE SET state='running',lease_owner=EXCLUDED.lease_owner,lease_until=EXCLUDED.lease_until,
                    attempts=vault_decision_reviews.attempts+1,error_code=NULL,updated_at=now()
                  WHERE vault_decision_reviews.state IN ('queued','retryable') OR
                    (vault_decision_reviews.state='running' AND vault_decision_reviews.lease_until <= clock_timestamp())
                  RETURNING review_id,attempts""",
                  (review_id, principal.user_id, principal.workspace_id, snapshot.conversation_id,
                   snapshot.segment_id, fingerprint, REVIEW_CONTRACT_VERSION, token, lease_seconds,
                   Jsonb({"coverage": snapshot.coverage,
                       "sourceIds":[s.source_id for s in snapshot.sources],
                       "observationIds":[p.point_id for p in snapshot.observations],
                       "existing_decisions":
                       [d.model_dump(mode="json") for d in snapshot.existing_decisions]})))
                row = cursor.fetchone()
                return (ReviewClaim(row[0], principal.user_id, principal.workspace_id, token, row[1], fingerprint)
                        if row else None)

    @staticmethod
    def _claim_scope(principal, claim):
        if (principal.user_id, principal.workspace_id) != (claim.user_id, claim.workspace_id):
            raise ReviewConflictError("Review claim belongs to another scope.")

    def stage(self,principal,claim,snapshot,*,name,value=None):
        """Fenced immutable model-stage checkpoint in existing review metadata."""
        import json
        import re
        if name not in {"analysis","analysis_plan","reconciliation","analysis_source_view"} and not re.fullmatch(r'analysis_(?:window|source)_\d{1,3}_page_\d{1,3}',name):
            raise ValueError("Unknown review stage.")
        self._claim_scope(principal,claim)
        if source_fingerprint(snapshot)!=claim.source_fingerprint:
            raise ReviewConflictError("Stage source changed.")
        if value is not None and len(json.dumps(value).encode())>(1048576 if name=='analysis' else 150000):
            raise ValueError("Bounded review stage required.")
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_source(cursor,principal,snapshot)
            cursor.execute("""SELECT source_coverage_json FROM vault_private.vault_decision_reviews
              WHERE review_id=%s AND user_id=%s AND workspace_id=%s AND state='running'
              AND lease_owner=%s AND attempts=%s AND lease_until>clock_timestamp() FOR UPDATE""",
              (claim.review_id,principal.user_id,principal.workspace_id,claim.token,claim.attempt))
            row = cursor.fetchone()
            if row is None:
                raise ReviewConflictError("Stage lease expired or superseded.")
            # Successful bounded steps renew this same fenced owner, allowing
            # multi-window jobs to progress without a second lease/worker owner.
            cursor.execute("""UPDATE vault_private.vault_decision_reviews SET
              lease_until=GREATEST(lease_until,clock_timestamp()+interval '180 seconds')
              WHERE review_id=%s""",(claim.review_id,))
            prior = row[0].get(name)
            if value is None:
                return prior
            if prior is not None and prior!=value:
                raise ReviewConflictError("Committed stage cannot be replaced.")
            cursor.execute("""UPDATE vault_private.vault_decision_reviews SET source_coverage_json=
              source_coverage_json || %s,updated_at=now() WHERE review_id=%s""",
              (Jsonb({name:value}),claim.review_id))
            return value

    @contextmanager
    def keepalive(self, principal, claim, snapshot):
        """Renew this existing fenced lease while a bounded model call is pending."""
        from threading import Event, Thread
        from time import monotonic
        self.stage(principal, claim, snapshot, name="analysis")
        stop = Event()
        failures = []
        deadline = monotonic() + 600
        def renew():
            while not stop.wait(LEASE_RENEW_SECONDS):
                if monotonic() >= deadline:
                    failures.append(ReviewConflictError('Review execution budget exhausted.'))
                    return
                try:
                    # Existing stage read requalifies source/authority and renews
                    # precisely this owner/attempt. It writes no review output.
                    self.stage(principal, claim, snapshot, name='analysis')
                except Exception as error:
                    failures.append(error)
                    return
        thread = Thread(target=renew, name='vault-review-lease', daemon=True)
        thread.start()
        try:
            yield
            if failures:
                raise failures[0]
            self.stage(principal, claim, snapshot, name="analysis")
            if monotonic() >= deadline:
                raise ReviewConflictError('Review execution budget exhausted.')
        finally:
            stop.set()
            thread.join(timeout=6)

    def reconciliation_epoch(self,principal,review_id):
        with self._connect() as connection,connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor,principal)
            cursor.execute("""SELECT source_coverage_json->'reconciliation' FROM vault_private.vault_decision_reviews
              WHERE user_id=%s AND workspace_id=%s AND review_id=%s AND state='completed'""",
              (principal.user_id,principal.workspace_id,review_id))
            row = cursor.fetchone()
            return row[0]["epoch"] if row and row[0] else None

    def complete(self, principal: LocalPrincipal, claim: ReviewClaim,
                 snapshot: ReviewInput, review: ProceduralReview, *, provider: str) -> bool:
        """Return True on exact acknowledged retry, False on first completion."""
        self._claim_scope(principal, claim)
        fingerprint = source_fingerprint(snapshot)
        if fingerprint != claim.source_fingerprint or fingerprint != review.source_fingerprint:
            raise ReviewConflictError("Review source changed.")
        if not provider.strip() or not review.model.strip():
            raise ValueError("Resolved provider/model required.")
        ReviewOutput.model_validate_json(review.output.model_dump_json())
        _validate_output(review.output, snapshot)
        output_hash = sha256(review.output.model_dump_json().encode()).hexdigest()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_source(cursor, principal, snapshot)
                cursor.execute("""SELECT state,lease_owner,attempts,source_snapshot_fingerprint,
                    output_fingerprint,provider,model,lease_until > clock_timestamp(),learner_contract_version
                  FROM vault_private.vault_decision_reviews WHERE review_id=%s AND user_id=%s AND workspace_id=%s
                  AND conversation_id=%s AND segment_id=%s FOR UPDATE""",
                  (claim.review_id, principal.user_id, principal.workspace_id,
                   snapshot.conversation_id, snapshot.segment_id))
                row = cursor.fetchone()
                if row is None or row[1:4] != (claim.token, claim.attempt, fingerprint):
                    raise ReviewConflictError("Review lease was superseded.")
                if row[8]!=REVIEW_CONTRACT_VERSION:
                    raise ReviewConflictError("Historical reviewer contract requires explicit qualification.")
                if row[0] == "completed":
                    if row[4:7] != (output_hash, provider, review.model):
                        raise ReviewConflictError("Completed review cannot be overwritten.")
                    return True
                if row[0] != "running" or row[7] is not True:
                    raise ReviewConflictError("Review lease expired.")
                cursor.execute("""UPDATE vault_private.vault_decision_reviews SET state='completed',
                    proposals_json=%s,assessments_json=%s,output_fingerprint=%s,provider=%s,model=%s,
                    lease_until=NULL,error_code=NULL,completed_at=now(),updated_at=now()
                  WHERE review_id=%s""", (Jsonb(review.output.model_dump(mode="json")["proposals"]),
                    Jsonb(review.output.model_dump(mode="json")["assessments"]),
                    output_hash, provider, review.model, claim.review_id))
                return False

    def retryable(self, principal: LocalPrincipal, claim: ReviewClaim) -> None:
        self._claim_scope(principal, claim)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ConversationRepository._require_authority(cursor, principal)
                cursor.execute("""UPDATE vault_private.vault_decision_reviews SET state='retryable',
                    lease_until=NULL,error_code='review_failed',updated_at=now()
                  WHERE review_id=%s AND user_id=%s AND workspace_id=%s AND state='running'
                    AND lease_owner=%s AND attempts=%s AND lease_until > clock_timestamp()
                  RETURNING review_id""", (claim.review_id, principal.user_id, principal.workspace_id,
                    claim.token, claim.attempt))
                if cursor.fetchone() is None:
                    raise ReviewConflictError("Review lease was superseded or expired.")

    def get(self, principal: LocalPrincipal, review_id: str):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ConversationRepository._require_authority(cursor, principal)
                cursor.execute("""SELECT state,model,proposals_json,assessments_json,learner_contract_version FROM vault_private.vault_decision_reviews
                  WHERE review_id=%s AND user_id=%s AND workspace_id=%s""",
                  (review_id, principal.user_id, principal.workspace_id))
                row = cursor.fetchone()
                if row is None:
                    raise ReviewConflictError("Review is unavailable in current scope.")
                if row[4]!=REVIEW_CONTRACT_VERSION:
                    raise ReviewConflictError("Historical reviewer contract requires explicit qualification.")
                return row[0], row[1], ReviewOutput.model_validate({"contract_version":row[4],"proposals":row[2],"assessments":row[3]})

    def for_source(self, principal: LocalPrincipal, snapshot: ReviewInput):
        fingerprint = source_fingerprint(snapshot)
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_source(cursor,principal,snapshot)
            cursor.execute("""SELECT review_id,state,provider,model,proposals_json,assessments_json
              FROM vault_private.vault_decision_reviews WHERE user_id=%s AND workspace_id=%s
              AND conversation_id=%s AND segment_id=%s AND source_snapshot_fingerprint=%s
              AND learner_contract_version=%s""",(principal.user_id,principal.workspace_id,
                snapshot.conversation_id,snapshot.segment_id,fingerprint,REVIEW_CONTRACT_VERSION))
            row = cursor.fetchone()
            if row is None:
                return None
            return (*row[:4],ReviewOutput.model_validate({"contract_version":REVIEW_CONTRACT_VERSION,"proposals":row[4],"assessments":row[5]}))
