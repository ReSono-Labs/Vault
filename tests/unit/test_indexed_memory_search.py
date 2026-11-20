from datetime import UTC, datetime

import pytest

from app.vault_runtime.memory.models import MemoryRecord
from app.vault_runtime.memory.repository import MemoryAuthorizationError
from app.vault_runtime.memory_search.indexed import PgvectorMemorySearchBackend
from app.vault_runtime.memory_search.indexes import IndexMigrationError, ensure_indexes, _normalized
from app.vault_runtime.memory_search.postgres import PgvectorMemoryQueries, QueryOptions, vector_literal, vector_version


OPTIONS = QueryOptions(timeout_ms=2000, ef_search=80, max_scan_tuples=1000)


@pytest.mark.parametrize("values", [[], [1.0], [0.0]*768, [float('nan')]*768,
    [float('inf')]*768, [1e40]*768, [1e-50]*768])
def test_invalid_vector_rejected(values):
    with pytest.raises(ValueError):
        vector_literal(values)


@pytest.mark.parametrize("values", [(0,80,100), (1,0,100), (1,1001,100), (1,80,0), (True,80,100)])
def test_invalid_query_options_rejected(values):
    with pytest.raises(ValueError):
        QueryOptions(*values)


def test_concurrent_migration_rejects_transaction_before_sql():
    connection = type('Connection', (), {'autocommit': False})()
    with pytest.raises(IndexMigrationError):
        ensure_indexes(connection)


def test_index_definition_comparison_preserves_literal_whitespace():
    assert _normalized("WHERE provider = 'openai'")==_normalized("WHERE  provider='openai'")
    assert _normalized("WHERE provider='open ai'")!=_normalized("WHERE provider='openai'")


def test_concurrent_migration_rejects_explicit_transaction_even_with_autocommit():
    connection=type('Connection',(),{'autocommit':True,'info':type('Info',(),{'transaction_status':2})()})()
    with pytest.raises(IndexMigrationError):ensure_indexes(connection)


def _record():
    now = datetime.now(UTC)
    return MemoryRecord('m','w','u','private','user','project','fact','tea','tea',
        'user_asserted','high','normal','active',1,now,now)


class Queries:
    memories = object()
    def __init__(self, *, denied=False, sql_error=False):
        self.denied, self.sql_error = denied, sql_error
        self.calls = []
    def lexical(self, query, **scope):
        self.calls.append('lexical')
        return (_record(),)
    def authorize(self, **scope):
        self.calls.append('authorize')
        if self.denied:
            raise MemoryAuthorizationError('revoked')
    def semantic(self, values, **scope):
        self.calls.append('semantic')
        if self.sql_error:
            raise RuntimeError('SQL failed')
        return ((_record(), 0.8),)


class Embedder:
    model_key = 'embeddinggemma:300m'
    def __init__(self, *, failure=False): self.failure = failure
    def embed(self, query):
        if self.failure: raise RuntimeError('provider down')
        return [1.0]+[0.0]*767


def _backend(queries):
    backend = PgvectorMemorySearchBackend(memories=object(), options=OPTIONS)
    backend._queries = queries
    return backend


def test_existing_exact_lexical_semantic_rank_and_dedup_are_reused():
    queries = Queries()
    result = _backend(queries).retrieve('tea',user_id='u',workspace_id='w',limit=100,embedder=Embedder())
    assert len(result)==1 and result[0].score==1.0
    assert result[0].match_methods==('exact','lexical','semantic')
    assert queries.calls==['lexical','semantic']
    assert PgvectorMemorySearchBackend.repairs_vectors_during_query is False


@pytest.mark.parametrize('embedder',[None,Embedder(failure=True)])
def test_embedding_outage_keeps_lexical_without_python_vector_scan(embedder):
    queries = Queries()
    result = _backend(queries).retrieve('tea',user_id='u',workspace_id='w',limit=8,embedder=embedder)
    assert result[0].match_methods==('exact','lexical')
    assert queries.calls==['lexical','authorize']


def test_revocation_during_embedding_outage_never_returns_earlier_payload():
    with pytest.raises(MemoryAuthorizationError):
        _backend(Queries(denied=True)).retrieve('tea',user_id='u',workspace_id='w',limit=8,embedder=Embedder(failure=True))


def test_sql_failure_propagates_instead_of_silently_reporting_no_match():
    with pytest.raises(RuntimeError,match='SQL failed'):
        _backend(Queries(sql_error=True)).retrieve('tea',user_id='u',workspace_id='w',limit=8,embedder=Embedder())


def test_unsupported_model_is_not_embedded_or_guessed():
    embedder=Embedder(failure=True)
    embedder.model_key='different-model'
    queries=Queries()
    result=_backend(queries).retrieve('tea',user_id='u',workspace_id='w',limit=8,embedder=embedder)
    assert result[0].match_methods==('exact','lexical')
    assert queries.calls==['lexical','authorize']


@pytest.mark.parametrize('version',[None,'0.7.4','not-a-version'])
def test_missing_older_or_unknown_extension_fails_closed(version):
    cursor=type('Cursor',(),{'execute':lambda *_:None,'fetchone':lambda _:None if version is None else (version,)})()
    with pytest.raises(RuntimeError,match='pgvector >= 0.8'):vector_version(cursor)


def test_query_shape_and_bound_values_never_fetch_json_vectors():
    memories = type('Memories',(),{'_scope_sql':lambda self, alias: f'{alias}.workspace_id=%s AND ({alias}.visibility=\'workspace\' OR {alias}.user_id=%s)'})()
    queries = PgvectorMemoryQueries(memories=memories,options=OPTIONS)
    for exact in (True,False):
        sql = queries.semantic_statement(exact=exact)
        params = queries.semantic_parameters(user_id='u',workspace_id="w'; DROP TABLE x",literal='[1]',limit=5,floor=.2,exact=exact)
        assert sql.count('%s')==len(params)==8
        assert 'vector_json' not in sql and 'lifecycle_status' in sql and 'content_fingerprint' in sql
        assert 'DROP TABLE' not in sql
        assert ('MATERIALIZED' in sql) if exact else ('ORDER BY embedding::vector(768) <=>' in sql)
