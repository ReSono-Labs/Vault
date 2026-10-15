from types import SimpleNamespace

import pytest

from app.vault_runtime.decision_learning.service import DecisionLearningService
from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
from app.vault_runtime.decision_learning.reviewer import DecisionReviewer
from app.vault_runtime.decision_learning.repository import ReviewConflictError
from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from tests.integration.test_conversation_identity_postgres import context
from tests.integration.test_decision_review_repository_postgres import setup
from tests.unit.test_decision_learning_reviewer import output


def configured(context):
    url, _, owner, _, _ = context
    _, source, _ = setup(context)
    current = [True]
    repository = DecisionRuleRepository(database_url=url,source_current=lambda *_: current[0])
    repository.ensure_schema()
    calls = []
    class Credentials:
        def selected_provider(self,**scope):
            assert scope == {"user_id":owner.principal.user_id,"workspace_id":owner.principal.workspace_id}
            return "openai"
        def background_access(self,**scope):
            assert scope["user_id"] == owner.principal.user_id and scope["workspace_id"] == owner.principal.workspace_id
            return SimpleNamespace(value="synthetic-key",auth_method="api_key"),"configured-model"
    def execute(**kwargs):
        calls.append(kwargs)
        return output()
    reviewer = DecisionReviewer(model_runner=OpenAIMemoryReviewer(credentials=Credentials(),
        user_id=owner.principal.user_id,workspace_id=owner.principal.workspace_id,executor=execute))
    return repository,source,reviewer,calls,current


def test_model_review_publication_embeddings_and_duplicate_recovery_without_second_model(context):
    _, _, owner, _, _ = context
    repository,source,reviewer,calls,current = configured(context)
    vectors = []
    class Embedder:
        model_key = "embeddinggemma:300m"
        def embed(self,text):
            vectors.append(text)
            return (1.0,)+(0.0,)*767
    def factory(user,workspace):
        assert (user,workspace) == (owner.principal.user_id,owner.principal.workspace_id)
        return Embedder()
    service = DecisionLearningService(reviewer=reviewer,repository=repository,embedder_factory=factory,lease_seconds=30)
    first = service.run(owner.principal,source,provider="openai")
    assert first.state == "generation_built_inactive" and first.embedded_count == 2 and first.pending_embeddings == 0
    assert len(calls) == 1 and len(vectors) == 2
    second = service.run(owner.principal,source,provider="openai")
    assert second == first and len(calls) == 1 and len(vectors) == 2
    with pytest.raises(ReviewConflictError):
        service.run(owner.principal,source,provider="xai")


def test_embedding_resume_pending_lease_and_source_gate_never_repeat_model(context):
    _, _, owner, _, _ = context
    repository,source,reviewer,calls,current = configured(context)
    available = [False]
    embedder = SimpleNamespace(model_key="embeddinggemma:300m",embed=lambda _:(1.0,)+(0.0,)*767)
    service = DecisionLearningService(reviewer=reviewer,repository=repository,
        embedder_factory=lambda *_:embedder if available[0] else None,lease_seconds=30)
    claim = repository.claim(owner.principal,source,lease_seconds=30)
    assert service.run(owner.principal,source,provider="openai").state == "review_pending"
    assert calls == []
    repository.retryable(owner.principal,claim)
    first = service.run(owner.principal,source,provider="openai")
    assert first.state == "generation_pending_vectors" and first.pending_embeddings == 2
    available[0] = True
    second = service.run(owner.principal,source,provider="openai")
    assert second.generation_id == first.generation_id and second.state == "generation_built_inactive"
    assert len(calls) == 1
    current[0] = False
    with pytest.raises(ReviewConflictError):
        service.run(owner.principal,source,provider="openai")
    assert len(calls) == 1
