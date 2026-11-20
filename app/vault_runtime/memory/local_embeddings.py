"""Packaged, CPU-bounded EmbeddingGemma adapter for existing memory owners."""
from __future__ import annotations

import json
from math import isfinite
from urllib.request import Request, urlopen
from threading import Lock

PROVIDER = 'ollama'
MODEL = 'embeddinggemma:300m'
DIMENSIONS = 768
_ENDPOINT = 'http://127.0.0.1:11435/api/embed'
_REQUEST_LOCK = Lock()


class LocalEmbeddingUnavailable(RuntimeError):
    code = 'local_embedding_unavailable'


class LocalEmbeddings:
    model_key = MODEL
    provider_key = PROVIDER
    dimensions = DIMENSIONS

    def __init__(self, *, timeout_seconds=30):
        if not 0 < timeout_seconds <= 30:
            raise ValueError('Embedding timeout must be within 30 seconds.')
        self.timeout_seconds = timeout_seconds

    def with_timeout(self, timeout_seconds):
        return LocalEmbeddings(timeout_seconds=timeout_seconds)

    def embed(self, text):
        return self._encode(text, query=False)

    def embed_query(self, text):
        return self._encode(text, query=True)

    def _encode(self, text, *, query):
        import time
        from urllib.error import HTTPError
        if not isinstance(text, str) or not text.strip() or len(text) > 32768:
            raise LocalEmbeddingUnavailable('Embedding input is empty or exceeds the bound.')
        prefix = 'task: search result | query: ' if query else 'title: none | text: '
        deadline = time.monotonic() + self.timeout_seconds
        if not _REQUEST_LOCK.acquire(timeout=self.timeout_seconds):
            raise LocalEmbeddingUnavailable('Local embedding runtime is busy.')
        vectors = []
        requests = 0
        def encode_window(window):
            nonlocal requests
            requests += 1
            remaining = deadline - time.monotonic()
            if requests > 31 or remaining <= 0:
                raise LocalEmbeddingUnavailable('Local embedding window budget exhausted.')
            body = json.dumps(dict(model=MODEL, input=prefix + window, truncate=False,
                keep_alive=-1, options=dict(num_thread=2, num_ctx=2048, num_batch=256))).encode()
            request = Request(_ENDPOINT, data=body, headers={'Content-Type':'application/json'}, method='POST')
            try:
                with urlopen(request, timeout=remaining) as response:
                    payload = json.loads(response.read(65536))
            except HTTPError as error:
                # Ollama uses the actual model tokenizer, including our prefix.
                # Split only its explicit context overflow; never mask other errors.
                detail = json.loads(error.read(4096)).get('error')
                import re
                overflow = detail == 'the input length exceeds the context length' or (
                    isinstance(detail, str) and re.fullmatch(
                        r'input \(\d+ tokens\) is too large to process\. increase the physical batch size \(current batch size: 256\)', detail)
                    is not None)
                if error.code != 400 or not overflow or len(window) < 2:
                    raise
                middle = len(window) // 2
                boundary = window.rfind(' ', len(window)//4, middle + 1)
                if boundary > 0:
                    middle = boundary + 1
                encode_window(window[:middle])
                encode_window(window[middle:])
                return
            rows = payload.get('embeddings', [])
            if len(rows) != 1 or len(rows[0]) != DIMENSIONS:
                raise ValueError('Invalid local embedding dimensions.')
            vector = [float(value) for value in rows[0]]
            if not all(isfinite(value) for value in vector) or not any(vector):
                raise ValueError('Invalid local embedding values.')
            tokens = payload.get('prompt_eval_count')
            if type(tokens) is not int or not 0 < tokens <= 256:
                raise ValueError('Local embedding token coverage is invalid.')
            vectors.append((vector, tokens))
        try:
            encode_window(text)
            if len(vectors) == 1:
                return vectors[0][0]
            # All windows must succeed. Keep the existing single-vector schema;
            # normalize the token-weighted mean in the same embedding space.
            weight = sum(tokens for _, tokens in vectors)
            pooled = [sum(vector[i] * tokens for vector, tokens in vectors) / weight
                      for i in range(DIMENSIONS)]
            norm = sum(value * value for value in pooled) ** .5
            if not isfinite(norm) or norm == 0:
                raise ValueError('Invalid pooled local embedding.')
            return [value / norm for value in pooled]
        except Exception as error:
            raise LocalEmbeddingUnavailable('Local embedding request failed.') from error
        finally:
            _REQUEST_LOCK.release()


class LocalEmbeddingFactory:
    """Inference has no provider credentials; repositories retain scope authority."""
    def __call__(self, user_id, workspace_id):
        return LocalEmbeddings()


from contextlib import contextmanager


@contextmanager
def packaged_runtime():
    """One private CPU-only Ollama child owned by the package server lifetime."""
    import os
    import subprocess
    import time
    from pathlib import Path
    root = Path('/opt/resono-vault/local-embeddings')
    env = dict(os.environ, OLLAMA_HOST='127.0.0.1:11435', OLLAMA_MODELS=str(root/'models'),
        OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_MAX_QUEUE='2',
        OLLAMA_NO_CLOUD='1', OLLAMA_CONTEXT_LENGTH='2048', OMP_NUM_THREADS='2',
        OLLAMA_KEEP_ALIVE='-1', CUDA_VISIBLE_DEVICES='-1')
    process = subprocess.Popen([str(root/'bin/ollama'), 'serve'], env=env)
    try:
        os.setpriority(os.PRIO_PROCESS, process.pid, 10)
        for _ in range(100):
            if process.poll() is not None:
                raise LocalEmbeddingUnavailable('Packaged embedding runtime exited.')
            try:
                with urlopen('http://127.0.0.1:11435/api/tags',timeout=0.2) as response:
                    models=json.loads(response.read())['models']
                if not any(m['name']==MODEL for m in models):
                    raise LocalEmbeddingUnavailable('Packaged EmbeddingGemma model is missing.')
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise LocalEmbeddingUnavailable('Packaged embedding runtime did not start.')
        LocalEmbeddings().embed("Local embedding runtime ready.")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
