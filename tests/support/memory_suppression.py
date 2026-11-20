"""Shared test helpers moved out of test modules (TST-01)."""


class SemanticReviewer:
    def __init__(self, candidates, *, judgment=None, hook=None):
        self.candidates=candidates
        self.judgment=judgment
        self.hook=hook
        self.comparisons=[]
    def review(self, _):
        from app.vault_runtime.memory.contracts import MemoryReview,ReviewedMemoryCandidate
        return MemoryReview('Scoped factual review',tuple(ReviewedMemoryCandidate(c,(0,)) for c in self.candidates),'synthetic')
    def review_structured(self, **kwargs):
        import json
        payload=json.loads(kwargs['input_text'])
        self.comparisons.append(payload)
        if self.hook: self.hook()
        pairs=[]
        for candidate in payload['candidates']:
            for forgotten in payload['forgotten']:
                same=candidate['content'] in {'Tea is my favorite drink','Prefers tea and owns a kettle'}
                pairs.append(dict(candidate_index=candidate['index'],forgotten_index=forgotten['index'],
                    judgment=self.judgment or ('same_fact' if same else 'different_fact')))
        return dict(comparisons=pairs),'synthetic'
