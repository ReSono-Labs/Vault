"""One independently retryable procedural unit; worker/process belongs to caller."""
from dataclasses import dataclass

from .reviewer import ProceduralReview
from .repository import ReviewConflictError, source_fingerprint


@dataclass(frozen=True, slots=True)
class LearningResult:
    state: str
    review_id: str | None = None
    generation_id: str | None = None
    proposal_count: int = 0
    embedded_count: int = 0
    pending_embeddings: int = 0
    error_code: str | None = None


class DecisionLearningService:
    def __init__(self, *, reviewer, repository, embedder_factory, lease_seconds: int):
        if not callable(embedder_factory) or type(lease_seconds) is not int or lease_seconds < 1:
            raise ValueError("Scoped embedding availability and explicit lease budget required.")
        self.reviewer,self.repository,self.embedder_factory,self.lease_seconds = reviewer,repository,embedder_factory,lease_seconds

    def run(self, principal, snapshot, *, provider: str) -> LearningResult:
        if self.reviewer is None:
            raise ValueError("Review execution requires an actual reviewer; use publish_completed for committed reviews.")
        if type(provider) is not str or not provider.strip():
            raise ValueError("Call-bound provider identity required.")
        # Claim/source qualification failure must surface, never invoke a model.
        claim = self.repository.claim(principal,snapshot,lease_seconds=self.lease_seconds)
        if claim is None:
            stored = self.repository.for_source(principal,snapshot)
            if stored is None or stored[1] != "completed":
                return LearningResult("review_pending",review_id=stored[0] if stored else None)
            review_id,state,stored_provider,model,output = stored
            if stored_provider != provider:
                raise ReviewConflictError("Completed reviewer provider differs from current call binding.")
            review = ProceduralReview(source_fingerprint(snapshot),model,output)
        else:
            review_id = claim.review_id
            try:
                review = self.reviewer.review(snapshot)
                self.repository.complete(principal,claim,snapshot,review,provider=provider)
            except Exception:
                try:
                    self.repository.retryable(principal,claim)
                except ReviewConflictError:
                    pass  # Expired/reclaimed worker cannot mutate another lease.
                return LearningResult("review_failed",review_id=review_id,error_code="decision_review_failed")
        return self.publish_completed(principal,snapshot,review_id=review_id,review=review)

    def publish_completed(self,principal,snapshot,*,review_id,review,_connection=None,prepared_vectors=None):
        """Reuse the existing durable publication/vector stage without a model call."""
        # Publication failure leaves completed review intact for recovery; no
        # successful generation response is returned if source/capability changed.
        options={} if _connection is None else dict(_connection=_connection)
        generation = self.repository.publish(principal,review_id=review_id,snapshot=snapshot,review=review,**options)
        examples = self.repository.examples(principal,generation,**options)
        pending = [(identity,text) for identity,text,has_vector in examples if not has_vector]
        embedded = len(examples)-len(pending)
        if pending and prepared_vectors is not None:
            for identity,text in pending:
                if text not in prepared_vectors:
                    raise ReviewConflictError('Rebuild vector preparation is incomplete.')
                self.repository.store_vector(principal,generation_id=generation,example_id=identity,
                    snapshot=snapshot,example_text=text,vector=prepared_vectors[text],provider='ollama',
                    model='embeddinggemma:300m',**options)
                embedded+=1
        elif pending:
            if _connection is not None:
                raise ReviewConflictError('Embedding calls cannot run inside a rebuild transaction.')
            try:
                embedder = self.embedder_factory(principal.user_id,principal.workspace_id)
            except Exception:
                embedder = None
            if embedder is not None and getattr(embedder,"model_key",None) == "embeddinggemma:300m":
                for identity,text in pending:
                    try:
                        vector = embedder.embed(text)  # No repository locks held.
                        self.repository.store_vector(principal,generation_id=generation,example_id=identity,
                            snapshot=snapshot,example_text=text,vector=vector,provider="ollama",model=embedder.model_key)
                        embedded += 1
                    except Exception:
                        continue  # Remains honestly pending, no fabricated vector.
        remaining = len(examples)-embedded
        return LearningResult("generation_pending_vectors" if remaining else "generation_built_inactive",
            review_id,generation,len(review.output.proposals),embedded,remaining)
