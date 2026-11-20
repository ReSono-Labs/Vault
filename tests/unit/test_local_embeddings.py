import io
import json
import pytest
from app.vault_runtime.memory import local_embeddings as module


def test_local_query_and_document_prompts_and_cpu_limits(monkeypatch):
    requests=[]
    def send(request, **kwargs):
        assert request.full_url=='http://127.0.0.1:11435/api/embed'
        assert request.get_header('Authorization') is None
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'embeddings':[[0.1]*768], 'prompt_eval_count':20}).encode())
    monkeypatch.setattr(module,'urlopen',send)
    embedder=module.LocalEmbeddingFactory()('user','workspace')
    assert len(embedder.embed('fact'))==768
    assert len(embedder.embed_query('question'))==768
    assert requests[0]['input']=='title: none | text: fact'
    assert requests[1]['input']=='task: search result | query: question'
    assert all(r['truncate'] is False and r['options']['num_thread']==2 and r['options']['num_batch']==256 for r in requests)


@pytest.mark.parametrize('vectors',[[[0.1]*1536],[[0.0]*768],[[float('nan')]*768],[]])
def test_local_invalid_vectors_fail_without_substitution(monkeypatch,vectors):
    monkeypatch.setattr(module,'urlopen',lambda *a,**k:io.BytesIO(json.dumps({'embeddings':vectors}).encode()))
    with pytest.raises(module.LocalEmbeddingUnavailable):module.LocalEmbeddings().embed('fact')


def test_long_input_splits_only_on_tokenizer_overflow_and_covers_all_text(monkeypatch):
    from urllib.error import HTTPError
    text='first section ' * 80 + 'second section ' * 80
    accepted=[]
    def send(request, **kwargs):
        payload=json.loads(request.data); window=payload['input'].split(' | text: ',1)[1]
        if len(window)>1300:
            raise HTTPError(request.full_url,400,'context',{},io.BytesIO(b'{"error":"the input length exceeds the context length"}'))
        accepted.append(window)
        return io.BytesIO(json.dumps({'embeddings':[[0.1]*768], 'prompt_eval_count':100}).encode())
    monkeypatch.setattr(module,'urlopen',send)
    result=module.LocalEmbeddings().embed(text)
    assert len(accepted)>1 and ''.join(accepted)==text
    assert len(result)==768 and sum(v*v for v in result)==pytest.approx(1)


def test_failed_window_does_not_publish_partial_vector(monkeypatch):
    from urllib.error import HTTPError
    calls=0
    def send(request, **kwargs):
        nonlocal calls
        calls+=1
        if calls==1:
            raise HTTPError(request.full_url,400,'context',{},io.BytesIO(b'{"error":"the input length exceeds the context length"}'))
        if calls==2:
            return io.BytesIO(json.dumps({'embeddings':[[0.1]*768], 'prompt_eval_count':100}).encode())
        raise HTTPError(request.full_url,500,'failed',{},io.BytesIO(b'{"error":"runtime failed"}'))
    monkeypatch.setattr(module,'urlopen',send)
    with pytest.raises(module.LocalEmbeddingUnavailable):module.LocalEmbeddings().embed('long document ' * 80)
    assert calls==3


def test_physical_batch_overflow_is_windowed(monkeypatch):
    from urllib.error import HTTPError
    calls=[]
    def send(request, **kwargs):
        window=json.loads(request.data)['input'].split(' | text: ',1)[1]
        if len(window)>30:
            raise HTTPError(request.full_url,400,'batch',{},io.BytesIO(json.dumps({'error':'input (300 tokens) is too large to process. increase the physical batch size (current batch size: 256)'}).encode()))
        calls.append(window)
        return io.BytesIO(json.dumps({'embeddings':[[0.1]*768], 'prompt_eval_count':20}).encode())
    monkeypatch.setattr(module,'urlopen',send)
    text='a moderately long factual memory statement'
    assert len(module.LocalEmbeddings().embed(text))==768
    assert ''.join(calls)==text
