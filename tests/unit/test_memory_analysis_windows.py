import json
import re
from types import SimpleNamespace as NS

import pytest

from app.vault_runtime.memory.analysis_windows import bounded_review
from app.vault_runtime.memory.contracts import MemoryCandidate,MemoryReview,ReviewedMemoryCandidate


def candidate(key,index,content=None):
    return ReviewedMemoryCandidate(MemoryCandidate('u','personal','fact',key,content or key,
        'user_asserted','high','normal','create'),(index,))


def test_dense_pages_resume_without_repeating_successful_model_step():
    calls,cache=[],{}
    def page(text,**_):
        payload=json.loads(text);calls.append(payload)
        if len(calls)==2:
            raise RuntimeError('Synthetic interrupted page')
        start=len(payload['excludedKeys'])
        values=tuple(candidate(f'fact-{i}',0) for i in range(start,min(start+32,40)))
        return MemoryReview('Facts',values,'model'),start+32<40
    def step(key,text,produce):
        if key not in cache:
            cache[key]=produce()
        return cache[key]
    reviewer=NS(review_page=page,consolidate_summary=lambda text:('Facts','model'))
    with pytest.raises(RuntimeError):
        bounded_review([('entry','user','Forty facts')],reviewer=reviewer,model='model',step=step)
    assert len(cache)==1
    review,evidence,refs=bounded_review([('entry','user','Forty facts')],reviewer=reviewer,model='model',step=step)
    assert len(review.memories)==40 and len(calls)==3
    assert evidence[0][2]=='Forty facts' and refs[0]['sourceId']=='entry'


def test_late_correction_consolidates_against_exact_original_global_spans():
    def page(text,consolidate=False):
        payload=json.loads(text)
        if consolidate:
            latest=payload['candidates'][-1]
            return MemoryReview('Corrected',(candidate('same',latest['source_entry_indexes'][0],'new'),),'model'),False
        matches=list(re.finditer(r'\[entryIndex=(\d+)\]',payload['evidence']))
        value='new' if 'CORRECTION' in payload['evidence'] else 'old'
        return MemoryReview('Source',(candidate('same',int(matches[-1][1]),value),),'model'),False
    review,evidence,refs=bounded_review([('early','user','x'*61000),('late','user','CORRECTION')],
        reviewer=NS(review_page=page,consolidate_summary=lambda _:('Corrected','model')),
        model='model',step=lambda key,text,produce:produce())
    assert len(review.memories)==1 and review.memories[0].memory.content_text=='new'
    assert len(review.memories[0].source_entry_indexes)>1
    assert all(i in evidence and i in refs for i in review.memories[0].source_entry_indexes)
    assert any(refs[i]['sourceId']=='late' for i in review.memories[0].source_entry_indexes)


@pytest.mark.parametrize('bad',['citation','repeat','empty_progress'])
def test_invalid_pages_never_checkpoint_as_success(bad):
    saved=[]
    def page(text,**_):
        excluded=json.loads(text)['excludedKeys']
        values=() if bad=='empty_progress' else (candidate('a',99 if bad=='citation' else 0),)
        return MemoryReview('Invalid',values,'model'),True
    def step(key,text,produce):
        result=produce();saved.append(key);return result
    with pytest.raises(ValueError):
        bounded_review([('entry','user','Evidence')],reviewer=NS(review_page=page),model='model',step=step)
    assert len(saved)==(1 if bad=='repeat' else 0)


def test_invalid_summary_model_never_checkpoints_summary():
    saved=[]
    def step(key,text,produce):
        result=produce();saved.append(key);return result
    reviewer=NS(review_page=lambda *args,**kwargs:(MemoryReview('Source',(),'model'),False),
        consolidate_summary=lambda _:('Summary','changed-model'))
    with pytest.raises(ValueError,match='Summary consolidation'):
        bounded_review([('entry','user','x'*61000)],reviewer=reviewer,model='model',step=step)
    assert saved and not any(key.startswith('summary:') for key in saved)
