import json
from types import SimpleNamespace as NS

import pytest

from app.vault_runtime.decision_learning.reconciliation import DecisionReconciler,validate_reconciliation,PROMPT
from app.vault_runtime.decision_learning.repository import ReviewConflictError,source_fingerprint
from app.vault_runtime.decision_learning.reviewer import ReviewOutput,ProceduralReview,DecisionReviewError
from tests.unit.test_decision_learning_reviewer import snapshot,output


def setup(active=True):
    behavior = dict(description="Read invoice payment state",conditions={"all":["Invoice or customer identified"]},
        required_slots=["invoice_id"],capabilities=["accounting.invoice.read"],exclusions=[])
    source = snapshot(existing_decisions=[dict(definition_id="existing",version=1,description=json.dumps(behavior))])
    original = ReviewOutput.model_validate(output())
    principal,claim = NS(user_id="u",workspace_id="w"),object()
    stages,calls,embeddings = {},[],[]
    class Repository:
        def stage(self,*args,name,value=None):
            if value is not None:
                stages[name]=value
            return stages.get(name)
    pointer = NS(generation_id="g" if active else None,epoch=1 if active else 0)
    class Queries:
        activator=NS(current=lambda _:pointer)
        def retrieve(self,*args,**kwargs):
            return NS(generation_id=pointer.generation_id,activation_epoch=pointer.epoch,
                choices=(NS(definition_id="existing"),))
    class Embedder:
        model_key="embeddinggemma:300m"
        def embed(self,text):
            embeddings.append(text)
            return [1.]+[0.]*767
    reconciler = DecisionReconciler(repository=Repository(),queries=Queries(),embedder_factory=lambda *_:Embedder())
    def result(disposition="add_example",**changes):
        proposal = output(disposition=disposition,target_definition_id="existing" if disposition in {"revise","add_example"} else None,
            description=behavior["description"] if disposition=="add_example" else "New distinct behavior")["proposals"][0]
        proposal.update(changes)
        return dict(contract_version=3,assessments=original.model_dump(mode="json")["assessments"],
            proposals=[proposal],rationale="Reuse same action; only another phrasing")
    class Model:
        def review_structured(self,**kwargs):
            calls.append(kwargs)
            return result("add_example" if active else "create"),"configured-model"
    args=dict(principal=principal,claim=claim,snapshot=source,
        review=ProceduralReview(source_fingerprint(source),"configured-model",original),model_runner=Model(),provider="openai")
    return NS(**locals())


def test_search_model_reuse_and_cached_stage_without_repeated_provider_calls():
    m=setup()
    review=m.reconciler.reconcile(**m.args)
    assert review.output.proposals[0].disposition=="add_example"
    assert len(m.embeddings)==len(m.calls)==1
    assert "required_slots" in m.calls[0]["input_text"]
    assert m.reconciler.reconcile(**m.args)==review
    assert len(m.embeddings)==len(m.calls)==1
    assert "invoice payment status versus" in PROMPT.lower() or "invoice payment status" in PROMPT.lower()


def test_first_catalog_still_model_reviews_batch_without_query_embedding():
    m=setup(active=False)
    assert m.reconciler.reconcile(**m.args).output.proposals[0].disposition=="create"
    assert not m.embeddings and len(m.calls)==1


@pytest.mark.parametrize("mode",["revise","create"])
def test_refinement_or_distinct_behavior_is_possible_without_changing_assessments(mode):
    m=setup()
    raw=m.result(mode,conditions=["Invoice or customer identified","Clarify ambiguous customer"])
    validate_reconciliation(m.original,ReviewOutput.model_validate({k:v for k,v in raw.items() if k!="rationale"}),m.source,m.source.existing_decisions)


@pytest.mark.parametrize("change",["assessment","citation","target","example_behavior"])
def test_reconciliation_cannot_improve_assessments_invent_evidence_or_change_example_behavior(change):
    m=setup()
    data=m.result()
    if change=="assessment":
        data["assessments"][0]["usefulness"]["explanation"]="A different assessment"
    elif change=="citation":
        data["proposals"][0]["source_ids"]=["final"]
    elif change=="target":
        data["proposals"][0]["target_definition_id"]="not-retrieved"
    else:
        data["proposals"][0]["conditions"]=["A new condition"]
    with pytest.raises((ValueError,ReviewConflictError,DecisionReviewError)):
        validate_reconciliation(m.original,ReviewOutput.model_validate({k:v for k,v in data.items() if k!="rationale"}),m.source,m.source.existing_decisions)


def test_missing_embedding_and_changed_epoch_fail_closed():
    m=setup()
    m.reconciler.embedder_factory=lambda *_:None
    with pytest.raises(ReviewConflictError,match="embedding"):
        m.reconciler.reconcile(**m.args)
    assert not m.calls and not m.stages
    m=setup()
    m.reconciler.reconcile(**m.args)
    m.pointer.epoch=2
    with pytest.raises(ReviewConflictError,match="catalog"):
        m.reconciler.reconcile(**m.args)
    assert len(m.calls)==1


def test_automatic_revision_cannot_remove_existing_conditions():
    m=setup()
    raw=m.result("revise",conditions=[])
    with pytest.raises(ReviewConflictError,match="safeguards"):
        validate_reconciliation(m.original,ReviewOutput.model_validate({k:v for k,v in raw.items() if k!="rationale"}),m.source,m.source.existing_decisions)


def test_model_failure_does_not_checkpoint_reconciliation():
    m=setup()
    class Unavailable:
        def review_structured(self,**kwargs):
            raise RuntimeError("synthetic provider failure")
    m.args["model_runner"]=Unavailable()
    with pytest.raises(RuntimeError,match="synthetic provider failure"):
        m.reconciler.reconcile(**m.args)
    assert "reconciliation" not in m.stages
