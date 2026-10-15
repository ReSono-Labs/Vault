import json
from copy import deepcopy

import pytest

from app.vault_runtime.decision_learning.analysis_windows import review_windows
from app.vault_runtime.decision_learning.reviewer import DecisionReviewer,ReviewInput,DecisionReviewError
from tests.unit.test_decision_learning_reviewer import snapshot,output,runner


def cache_stage(cache):
    def stage(key,value=None):
        if value is not None:
            cache[key]=value
        return cache.get(key)
    return stage


def test_assessment_windows_resume_and_union_exact_behavior_without_hiding_late_source():
    data=snapshot().model_dump(mode='json')
    data['observations']=[dict(data['observations'][0],point_id=f'p{i}') for i in range(21)]
    data['sources'].append(dict(source_id='late-correction',kind='user_correction',text='Late correction must remain visible'))
    source=ReviewInput.model_validate(data)
    calls,cache=[],{}
    def execute(**kwargs):
        payload=json.loads(kwargs['input_text']);calls.append(payload)
        assert payload['evidence']['sources'][-1]['source_id']=='late-correction'
        if len(calls)==2:
            raise RuntimeError('Interrupted window')
        ids=[p['point_id'] for p in payload['evidence']['observations']]
        result=output(point_ids=ids)
        result['assessments']=[dict(deepcopy(result['assessments'][0]),point_id=i) for i in ids]
        return dict(result,has_more=False)
    arguments=dict(reviewer=DecisionReviewer(model_runner=runner(execute)),model='configured-model',provider='openai',stage=cache_stage(cache))
    with pytest.raises(RuntimeError):
        review_windows(source,**arguments)
    assert len(cache)==1
    review=review_windows(source,**arguments)
    assert len(calls)==3 and len(review.output.assessments)==21
    assert len(review.output.proposals)==1 and len(review.output.proposals[0].point_ids)==21


@pytest.mark.parametrize('bad',[None,'repeat','changed_assessment','model'])
def test_dense_continuation_and_invalid_pages_never_save_as_success(bad):
    cache={}
    calls=[]
    def execute(**kwargs):
        payload=json.loads(kwargs['input_text']);calls.append(payload)
        excluded=payload['excluded_behavior_keys']
        start=len(excluded)
        result=output(disposition='no_change')
        result['proposals']=[dict(result['proposals'][0],description=f'Behavior {i}') for i in range(start,min(start+32,40))]
        if start and bad=='repeat':
            result['proposals'][0]['description']='Behavior 0'
        if start and bad=='changed_assessment':
            result['assessments'][0]['request_resolution']['explanation']='Rewritten outcome'
        return dict(result,has_more=start+32<40)
    reviewer=DecisionReviewer(model_runner=runner(execute))
    expected='wrong-model' if bad=='model' else 'configured-model'
    arguments=dict(reviewer=reviewer,model=expected,provider='openai',stage=cache_stage(cache))
    if bad:
        with pytest.raises(DecisionReviewError):
            review_windows(snapshot(),**arguments)
        assert len(cache)==(0 if bad=='model' else 1)
    else:
        review=review_windows(snapshot(),**arguments)
        assert len(review.output.proposals)==40 and len(cache)==2
        assert calls[1]['excluded_behavior_keys'][0]['behavior']['description']=='Behavior 0'
        assert calls[1]['fixed_assessments']==review.output.model_dump(mode='json')['assessments']


def test_oversized_full_source_is_not_silently_hidden_by_assessment_partition():
    source=snapshot().model_dump(mode='json')
    source['sources']=[dict(source_id=f's{i}',kind='user_final',text='x'*19000) for i in range(6)]+source['sources']
    with pytest.raises(DecisionReviewError,match='input budget'):
        review_windows(ReviewInput.model_validate(source),reviewer=None,model='configured-model',provider='openai',stage=cache_stage({}))


def test_large_source_windows_resume_read_every_character_and_preserve_late_correction():
    data=snapshot().model_dump(mode='json')
    data['sources'].extend(dict(source_id=f'large-{i}',kind='tool_result',text='x'*24000) for i in range(5))
    data['sources'].append(dict(source_id='late',kind='user_correction',text='The earlier answer was wrong; use the revised customer.'))
    source=ReviewInput.model_validate(data)
    cache,calls={},[]
    interrupted=[False]
    def execute(**kwargs):
        payload=json.loads(kwargs['input_text']);calls.append((kwargs['agent_name'],payload))
        if kwargs['agent_name']=='Vault Decisions Source Review':
            if len(calls)==2 and not interrupted[0]:
                interrupted[0]=True
                raise RuntimeError('Source scan interrupted')
            return dict(reviewed_span_indexes=[s['span_index'] for s in payload['sources']],has_more=False,
                excerpts=[dict(span_index=s['span_index'],start=s['start'],end=s['start']+min(100,len(s['text'])),
                    text=s['text'][:100]) for s in payload['sources']])
        assert kwargs['agent_name']=='Vault Decisions Window Review'
        late=next(s for s in payload['evidence']['sources'] if s['source_id']=='late')
        assert late['reviewed_excerpts'][0]['text']==data['sources'][-1]['text']
        return dict(output(disposition='no_change'),has_more=False)
    arguments=dict(reviewer=DecisionReviewer(model_runner=runner(execute)),model='configured-model',
        provider='openai',stage=cache_stage(cache))
    with pytest.raises(RuntimeError,match='could not complete'):
        review_windows(source,**arguments)
    first_input=calls[0][1]
    review=review_windows(source,**arguments)
    assert review.source_fingerprint
    assert sum(payload==first_input for _,payload in calls)==1
    successful=[payload for name,payload in calls if name=='Vault Decisions Source Review']
    spans={s['span_index']:s for payload in successful for s in payload['sources']}
    for original in data['sources']:
        pieces=sorted((s for s in spans.values() if s['source_id']==original['source_id']),key=lambda s:s['start'])
        assert ''.join(s['text'] for s in pieces)==original['text']
    assert 'analysis_source_view' in cache
    # Retry must not model either source scans or final assessment again.
    count=len(calls)
    assert review_windows(source,**arguments)==review
    assert len(calls)==count


@pytest.mark.parametrize('fault',['omitted_span','fabricated_excerpt','nonadvancing'])
def test_source_window_invalid_evidence_never_becomes_a_checkpoint(fault):
    data=snapshot().model_dump(mode='json')
    data['sources'].append(dict(source_id='large',kind='tool_result',text='x'*110000))
    def execute(**kwargs):
        payload=json.loads(kwargs['input_text'])
        spans=payload['sources']
        return dict(reviewed_span_indexes=[s['span_index'] for s in spans][1:] if fault=='omitted_span'
            else [s['span_index'] for s in spans],has_more=fault=='nonadvancing',
            excerpts=[dict(span_index=spans[0]['span_index'],start=spans[0]['start'],end=spans[0]['start']+3,
                text='BAD')] if fault=='fabricated_excerpt' else [])
    cache={}
    with pytest.raises(DecisionReviewError):
        review_windows(ReviewInput.model_validate(data),reviewer=DecisionReviewer(model_runner=runner(execute)),
            model='configured-model',provider='openai',stage=cache_stage(cache))
    assert not cache
