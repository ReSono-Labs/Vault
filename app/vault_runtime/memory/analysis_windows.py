"""Resumable factual model steps; storage/worker/publication remain existing owners."""
import json
from dataclasses import asdict

from .analysis_spans import partition_sources, validate_coverage
from .contracts import MemoryCandidate, MemoryReview, ReviewedMemoryCandidate

ANALYSIS_CONTRACT = 1


def validate_page(review,more,*,model,indexes,excluded=(),spans=None):
    review=review.validated()
    if review.model!=model or type(more) is not bool or len(review.memories)>32:
        raise ValueError("Window output binding changed.")
    if any(i not in indexes for c in review.memories for i in c.source_entry_indexes):
        raise ValueError("Factual window invented citations.")
    if spans is not None and any(c.memory.source_authority!='model_derived'
        and any(spans[i].role=='document' for i in c.source_entry_indexes) for c in review.memories):
        raise ValueError('External attachment evidence requires model-derived authority.')
    keys=[c.memory.memory_key for c in review.memories]
    if len(keys)!=len(set(keys)) or set(keys)&set(excluded) or more and not keys:
        raise ValueError("Factual continuation did not advance.")
    return keys


def encode_review(review):
    return asdict(review)


def decode_review(payload):
    payload=dict(payload)
    payload['memories']=tuple(ReviewedMemoryCandidate(MemoryCandidate(**item['memory']),
        tuple(item['source_entry_indexes'])) for item in payload['memories'])
    return MemoryReview(**payload).validated()


def bounded_review(entries, *, reviewer, model, step):
    """step(key,input,produce) caches validated outputs under source/model fences."""
    windows=partition_sources(entries)
    validate_coverage(entries,windows)
    spans={s.index:s for w in windows for s in w}
    candidates,summaries=[],[]
    for ordinal,window in enumerate(windows):
        transcript='\n'.join(s.formatted for s in window)
        indexes={s.index for s in window}
        excluded=[]
        for page in range(128):
            exclusions=json.dumps(excluded,ensure_ascii=False)
            if len(exclusions)>20000:
                raise ValueError("Dense factual continuation requires further bounded partitioning.")
            text=json.dumps(dict(evidence=transcript,excludedKeys=excluded),ensure_ascii=False)
            def produce():
                reviewed,more=reviewer.review_page(text)
                validate_page(reviewed,more,model=model,indexes=indexes,excluded=excluded,spans=spans)
                return dict(review=encode_review(reviewed),hasMore=more)
            result=step(f'window:{ordinal}:page:{page}',text,produce)
            reviewed=decode_review(result['review'])
            keys=validate_page(reviewed,result['hasMore'],model=model,indexes=indexes,excluded=excluded,spans=spans)
            candidates.extend(reviewed.memories)
            summaries.append(reviewed.summary)
            excluded.extend(keys)
            if not result['hasMore']:
                break
        else:
            raise ValueError("Factual continuation exhausted its bounded page count.")
    # Global citation ordering is original source ordering, independent of windows.
    groups={}
    for candidate in candidates:
        memory=candidate.memory
        groups.setdefault((memory.subject_id,memory.domain,memory.memory_type,memory.memory_key),[]).append(candidate)
    consolidated=[]
    for ordinal,(identity,group) in enumerate(groups.items()):
        group.sort(key=lambda c:max(c.source_entry_indexes))
        result=group[0]
        for offset,candidate in enumerate(group[1:]):
            cited=tuple(sorted(set(result.source_entry_indexes+candidate.source_entry_indexes)))
            text=json.dumps(dict(candidates=[asdict(result),asdict(candidate)],
                evidence=[spans[i].formatted for i in cited]),ensure_ascii=False)
            if len(text)>100000:
                raise ValueError("Canonical-key consolidation requires bounded source continuation.")
            def produce():
                review,more=reviewer.review_page(text,consolidate=True)
                validate_page(review,more,model=model,indexes=cited,spans=spans)
                if more or len(review.memories)!=1:
                    raise ValueError("Consolidation did not complete.")
                m=review.memories[0].memory
                if (m.subject_id,m.domain,m.memory_type,m.memory_key)!=identity:
                    raise ValueError("Consolidation changed canonical identity.")
                return dict(review=encode_review(review),hasMore=more)
            output=step(f'key:{ordinal}:merge:{offset}',text,produce)
            review=decode_review(output['review'])
            if output['hasMore'] or review.model!=model or len(review.memories)!=1:
                raise ValueError("Canonical-key consolidation did not complete.")
            merged=review.memories[0]
            m=merged.memory
            if (m.subject_id,m.domain,m.memory_type,m.memory_key)!=identity or not set(merged.source_entry_indexes)<=set(cited):
                raise ValueError("Consolidation changed source or canonical identity.")
            # Preserve all original attribution, even when the consolidated wording changes.
            result=ReviewedMemoryCandidate(m,cited).validated()
        consolidated.append(result)
    level=0
    while len(summaries)>1 or len(summaries[0])>8000:
        batches,current,size=[],[],0
        for summary in summaries:
            cost=len(json.dumps(summary,ensure_ascii=False))+2
            if current and size+cost>55000:
                batches.append(current)
                current,size=[],0
            current.append(summary)
            size+=cost
        if current:
            batches.append(current)
        reduced=[]
        for ordinal,batch in enumerate(batches):
            text=json.dumps(batch,ensure_ascii=False)
            def produce():
                summary,actual=reviewer.consolidate_summary(text)
                if actual!=model or not isinstance(summary,str) or not 0<len(summary)<=8000:
                    raise ValueError("Summary consolidation output invalid.")
                return dict(summary=summary,model=actual)
            result=step(f'summary:{level}:{ordinal}',text,produce)
            if result['model']!=model or not isinstance(result['summary'],str) or not 0<len(result['summary'])<=8000:
                raise ValueError("Summary consolidation output invalid.")
            reduced.append(result['summary'])
        if level>=32 or (len(reduced)>=len(summaries) and len(summaries)>1):
            raise ValueError("Summary consolidation did not converge.")
        summaries=reduced
        level+=1
    evidence={i:(None,'chat_'+{'user':'user_statement','assistant':'assistant_statement','tool':'tool_result','document':'document_observation'}[s.role],s.text)
              for i,s in spans.items()}
    references={i:s.reference for i,s in spans.items()}
    return MemoryReview(summaries[0],tuple(consolidated),model).validated(),evidence,references
