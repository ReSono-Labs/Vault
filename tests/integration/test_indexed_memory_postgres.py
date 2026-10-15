from __future__ import annotations

from hashlib import sha256
import json
import os
import random
import subprocess
import time
from urllib.parse import urlsplit

import psycopg
import pytest

from tests.integration.test_memory_postgres import memory_context, _entry
from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory.repository import MemoryAuthorizationError
from app.vault_runtime.memory.service import MemoryService
from app.vault_runtime.memory_search.indexed import PgvectorMemorySearchBackend
from app.vault_runtime.memory_search.indexes import HNSW_NAME, LEXICAL_NAME, IndexMigrationError, ensure_indexes
from app.vault_runtime.memory_search.postgres import PgvectorMemoryQueries, QueryOptions, vector_literal


# Synthetic operator settings for this test only, not production defaults/SLA.
OPTIONS = QueryOptions(timeout_ms=10000, ef_search=100, max_scan_tuples=20000)
VECTOR = [1.0]+[0.0]*767


@pytest.fixture(autouse=True)
def _isolated_indexed_target():
    url=os.getenv('VAULT_TEST_DATABASE_URL','')
    if not url:pytest.skip('VAULT_TEST_DATABASE_URL is required')
    target=urlsplit(url)
    assert (target.hostname,target.port,target.path,target.username)==(
        '127.0.0.1',55436,'/resono_vault_test','vault_test')


def _memory(memories, principal, key, *, visibility='private', vector=VECTOR, model='embeddinggemma:300m'):
    entry = _entry(memories, principal, session=f'sql-{key}', index=0, text=f'Synthetic {key} evidence')
    record = memories.reconcile_memory(user_id=principal.user_id,workspace_id=principal.workspace_id,
        voice_session_id=f'sql-{key}',candidate=MemoryCandidate(subject_id='user',domain='project',
            memory_type='fact',memory_key=key,content_text=f'Synthetic {key} memory',source_authority='user_asserted',
            confidence='high',sensitivity='normal',intent='create',visibility=visibility),
        evidence=((entry.entry_id,'user_statement','user_asserted',entry.text_content),))
    if vector is not None:
        memories.store_embedding(user_id=principal.user_id,workspace_id=principal.workspace_id,
            memory_id=record.memory_id,provider='ollama',model=model,embedding=vector,content_text=record.content_text)
    return record


def _install(url):
    with psycopg.connect(url,autocommit=True) as connection:
        try:
            return ensure_indexes(connection)
        except IndexMigrationError:
            print(connection.execute("SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indexrelid IN (to_regclass(%s),to_regclass(%s))",
                (f'vault_private.{HNSW_NAME}',f'vault_private.{LEXICAL_NAME}')).fetchall())
            raise


def _queries(memories, options=OPTIONS):
    return PgvectorMemoryQueries(memories=memories,options=options)


def _scope(principal):
    return dict(user_id=principal.user_id,workspace_id=principal.workspace_id)


def test_indexes_repeat_and_real_service_sql_backend(memory_context, monkeypatch):
    url,_service,owner,_second,memories = memory_context
    record = _memory(memories,owner.principal,'tea')
    assert _install(url)['compatible']==1
    assert _install(url)['invalid']==0
    monkeypatch.setattr(memories,'embeddings_for',lambda **_: pytest.fail('Python vector scan'))
    class Embedder:
        model_key='embeddinggemma:300m'
        def embed(self, text): return VECTOR
    backend = PgvectorMemorySearchBackend(memories=memories,options=OPTIONS)
    service = MemoryService(repository=memories,search_backend=backend,embedder_factory=lambda *_: Embedder())
    monkeypatch.setattr(service,'ensure_vectors',lambda **_: pytest.fail('interactive vector repair'))
    matches = service.search(**_scope(owner.principal),query='tea')
    assert matches[0].memory.memory_id==record.memory_id
    assert matches[0].match_methods==('exact','lexical','semantic')
    assert matches[0].memory.current_version==1


def test_sql_private_shared_wrong_scope_and_revocation(memory_context):
    url,service,owner,second,memories = memory_context
    private = _memory(memories,owner.principal,'owner-private')
    shared = _memory(memories,owner.principal,'shared',visibility='workspace')
    foreign = _memory(memories,second.principal,'foreign')
    _install(url)
    queries = _queries(memories)
    assert {m.memory_id for m,_ in queries.semantic(VECTOR,**_scope(owner.principal))}=={private.memory_id,shared.memory_id}
    assert {m.memory_id for m,_ in queries.semantic(VECTOR,**_scope(second.principal))}=={foreign.memory_id}
    service.add_member(principal=owner.principal,workspace_id=owner.principal.workspace_id,username='second')
    scope = dict(user_id=second.principal.user_id,workspace_id=owner.principal.workspace_id)
    assert {m.memory_id for m,_ in queries.semantic(VECTOR,**scope)}=={shared.memory_id}
    assert {m.memory_id for m in queries.lexical('Synthetic',**scope)}=={shared.memory_id}
    service.revoke_member(principal=owner.principal,workspace_id=owner.principal.workspace_id,username='second')
    for method in (lambda:queries.semantic(VECTOR,**scope),lambda:queries.lexical('Synthetic',**scope)):
        with pytest.raises(MemoryAuthorizationError): method()
    with pytest.raises(MemoryAuthorizationError):
        queries.semantic(VECTOR,user_id=owner.principal.user_id,workspace_id=second.principal.workspace_id)


def test_semantic_guards_and_exact_underfill(memory_context,monkeypatch):
    url,_service,owner,_second,memories = memory_context
    eligible = _memory(memories,owner.principal,'eligible')
    stale = _memory(memories,owner.principal,'stale')
    inactive = _memory(memories,owner.principal,'inactive')
    othermodel = _memory(memories,owner.principal,'other-model',model='other-model')
    otherprovider = _memory(memories,owner.principal,'other-provider')
    dimensions = _memory(memories,owner.principal,'other-dimensions',vector=[1.0,0.0])
    missing = _memory(memories,owner.principal,'missing',vector=None)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_embeddings SET content_fingerprint='stale' WHERE memory_id=%s",(stale.memory_id,))
        connection.execute("UPDATE vault_private.vault_memory_records SET lifecycle_status='superseded' WHERE memory_id=%s",(inactive.memory_id,))
        connection.execute("UPDATE vault_private.vault_memory_embeddings SET provider='another' WHERE memory_id=%s",(otherprovider.memory_id,))
    _install(url)
    zero = _memory(memories,owner.principal,'zero',vector=[0.0]*768)
    queries = _queries(memories)
    calls=[]; original=queries.semantic_statement
    def statement(*,exact=False): calls.append(exact);return original(exact=exact)
    monkeypatch.setattr(queries,'semantic_statement',statement)
    matches = queries.semantic(VECTOR,**_scope(owner.principal))
    assert calls==[False,True]
    assert [m.memory_id for m,_ in matches]==[eligible.memory_id]
    assert queries.semantic(VECTOR,**_scope(owner.principal),exact=True)==matches
    memories.delete_memory(**_scope(owner.principal),memory_id=eligible.memory_id)
    assert not queries.semantic(VECTOR,**_scope(owner.principal))
    assert {othermodel.memory_id,otherprovider.memory_id,dimensions.memory_id,missing.memory_id,zero.memory_id}.issubset(
        {m.memory_id for m in queries.lexical('Synthetic',**_scope(owner.principal))})
    with pytest.raises(IndexMigrationError,match='invalid dimensions'):_install(url)


def test_migration_advisory_lock_denies_concurrent_operator(memory_context):
    url,*_=memory_context
    with psycopg.connect(url,autocommit=True) as connection:
        connection.execute('SELECT pg_advisory_lock(73102702)')
        try:
            with pytest.raises(IndexMigrationError,match='already running'):_install(url)
        finally:
            connection.execute('SELECT pg_advisory_unlock(73102702)')


def test_migration_rejects_bad_matching_dimensions_and_wrong_name(memory_context):
    url,_service,owner,_second,memories=memory_context
    bad=_memory(memories,owner.principal,'bad',vector=[1.0,0.0])
    with psycopg.connect(url) as connection:
        connection.execute('UPDATE vault_private.vault_memory_embeddings SET dimensions=768 WHERE memory_id=%s',(bad.memory_id,))
    with pytest.raises(IndexMigrationError,match='invalid dimensions'):_install(url)
    # Even malformed stored identity cannot trigger an unsafe cast in SQL lookup.
    assert not _queries(memories).semantic(VECTOR,**_scope(owner.principal))
    with psycopg.connect(url) as connection:
        connection.execute('UPDATE vault_private.vault_memory_embeddings SET dimensions=2 WHERE memory_id=%s',(bad.memory_id,))
        connection.execute(f'CREATE INDEX {HNSW_NAME} ON vault_private.vault_memory_embeddings(memory_id)')
    with pytest.raises(IndexMigrationError,match='conflicting definition'):_install(url)
    with psycopg.connect(url) as connection:
        assert 'USING btree' in connection.execute('SELECT pg_get_indexdef(%s::regclass)',(f'vault_private.{HNSW_NAME}',)).fetchone()[0]


def test_isolated_backup_restore_preserves_canonical_sources(memory_context,tmp_path):
    url,_service,owner,_second,memories=memory_context
    _memory(memories,owner.principal,'backup')
    tables=('vault_memory_records','vault_memory_record_versions','vault_memory_evidence',
        'vault_transcript_entries','vault_memory_embeddings')
    def snapshot():
        with psycopg.connect(url) as connection:
            return {table: connection.execute(f'SELECT row_to_json(t) FROM vault_private.{table} t').fetchall() for table in tables}
    before=snapshot()
    backup=tmp_path/'synthetic-memory.dump'
    with backup.open('wb') as output:
        subprocess.run(['docker','exec','resono-vault-test-postgres','pg_dump','-U','vault_test',
            '-d','resono_vault_test','--schema=vault_private','--format=custom','--no-owner','--no-acl'],stdout=output,check=True)
    _install(url)
    with backup.open('rb') as source:
        subprocess.run(['docker','exec','-i','resono-vault-test-postgres','pg_restore','-U','vault_test',
            '-d','resono_vault_test','--clean','--if-exists','--no-owner','--no-acl','--exit-on-error'],stdin=source,check=True,capture_output=True)
    assert snapshot()==before
    _install(url)


def _bulk(memories,url,principal,count=4000):
    rng=random.Random(731027)
    vectors=[]
    for _ in range(count):vectors.append([rng.uniform(-1,1) for _ in range(12)]+[0.0]*756)
    with psycopg.connect(url) as connection:
        with connection.cursor().copy('COPY vault_private.vault_memory_records (memory_id,workspace_id,user_id,visibility,subject_id,domain,memory_type,memory_key,content_text,source_authority,confidence,sensitivity) FROM STDIN') as copy:
            for i in range(count):
                copy.write_row((f'benchmark-{i}',principal.workspace_id,principal.user_id,'private','user','project','fact',f'key-{i}',f'Synthetic benchmark item {i}','user_asserted','high','normal'))
        with connection.cursor().copy('COPY vault_private.vault_memory_embeddings (memory_id,provider,model,dimensions,vector_json,embedding,content_fingerprint) FROM STDIN') as copy:
            for i,vector in enumerate(vectors):
                literal=vector_literal(vector)
                copy.write_row((f'benchmark-{i}','ollama','embeddinggemma:300m',768,literal,literal,sha256(f'Synthetic benchmark item {i}'.encode()).hexdigest()))
    return vectors


def test_actual_interrupted_concurrent_index_recovers(memory_context):
    url,_service,owner,_second,memories=memory_context
    _bulk(memories,url,owner.principal)
    with psycopg.connect(url,autocommit=True) as connection:
        connection.execute("SET statement_timeout='50ms'")
        with pytest.raises(psycopg.errors.QueryCanceled):ensure_indexes(connection)
        connection.execute('SET statement_timeout=0')
        row=connection.execute('SELECT indisvalid FROM pg_index WHERE indexrelid=%s::regclass',(f'vault_private.{HNSW_NAME}',)).fetchone()
        assert row==(False,)
        assert ensure_indexes(connection)['compatible']==4000
        assert ensure_indexes(connection)['invalid']==0


def test_natural_hnsw_plan_and_scoped_exact_recall(memory_context,capsys):
    url,service,owner,second,memories=memory_context
    vectors=_bulk(memories,url,owner.principal)
    report=_install(url)
    with psycopg.connect(url) as connection:
        connection.execute('ANALYZE vault_private.vault_memory_records')
        connection.execute('ANALYZE vault_private.vault_memory_embeddings')
    queries=_queries(memories)
    scope=_scope(owner.principal)
    query=vectors[23]
    parameters=queries.semantic_parameters(**scope,literal=vector_literal(query),limit=10,floor=.2)
    with psycopg.connect(url) as connection,connection.cursor() as cursor:
        queries._configure(cursor,**scope)
        cursor.execute("SET LOCAL hnsw.iterative_scan='strict_order'")
        cursor.execute('SET LOCAL hnsw.ef_search=100')
        cursor.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+queries.semantic_statement(),parameters)
        plan=cursor.fetchone()[0][0]
        serialized=json.dumps(plan)
        assert HNSW_NAME in serialized,serialized
        index_bytes=connection.execute('SELECT pg_relation_size(%s::regclass)',(f'vault_private.{HNSW_NAME}',)).fetchone()[0]
        cursor.execute("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT memory_id FROM vault_private.vault_memory_records WHERE to_tsvector('simple',content_text) @@ plainto_tsquery('simple','23')")
        lexical_plan=cursor.fetchone()[0][0]
        assert LEXICAL_NAME in json.dumps(lexical_plan)
    recalls=[]; timings=[]
    for number in (23,125,799,2100):
        started=time.perf_counter();ann=queries.semantic(vectors[number],**scope,limit=10);ann_ms=(time.perf_counter()-started)*1000
        started=time.perf_counter();exact=queries.semantic(vectors[number],**scope,limit=10,exact=True);exact_ms=(time.perf_counter()-started)*1000
        ann_ids={m.memory_id for m,_ in ann};exact_ids={m.memory_id for m,_ in exact}
        overlap=len(ann_ids&exact_ids)/len(exact_ids)
        recalls.append(overlap);timings.append((round(ann_ms,2),round(exact_ms,2)))
        assert len(ann)==len(exact)==10
        assert all(m.workspace_id==owner.principal.workspace_id for m,_ in ann)
    assert min(recalls)>.0 # Measurement, not an invented production acceptance threshold.
    # Heavy post-index scope filtering: only 20/4000 rows shared with this member.
    service.add_member(principal=owner.principal,workspace_id=owner.principal.workspace_id,username='second')
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET visibility='workspace' WHERE memory_id=ANY(%s)",([f'benchmark-{i}' for i in range(20)],))
        connection.execute('ANALYZE vault_private.vault_memory_records')
    member_scope=dict(user_id=second.principal.user_id,workspace_id=owner.principal.workspace_id)
    filtered_ann=queries.semantic(vectors[23],**member_scope,limit=10,floor=-1)
    filtered_exact=queries.semantic(vectors[23],**member_scope,limit=10,floor=-1,exact=True)
    assert len(filtered_ann)==len(filtered_exact)==10
    assert all(m.visibility=='workspace' for m,_ in filtered_ann)
    filtered_ids={m.memory_id for m,_ in filtered_ann}
    filtered_reference={m.memory_id for m,_ in filtered_exact}
    filtered_overlap=len(filtered_ids&filtered_reference)/10
    print(json.dumps(dict(rows=report['compatible'],extension=report['vector_version'],
        natural_hnsw=True,execution_ms=plan['Execution Time'],planning_ms=plan['Planning Time'],
        index_bytes=index_bytes,recall_at_10=recalls,ann_exact_ms=timings,
        natural_gin=True,shared_hit_blocks=plan['Plan'].get('Shared Hit Blocks'),
        shared_read_blocks=plan['Plan'].get('Shared Read Blocks'),
        filtered_visible_rows=20,filtered_recall_at_10=filtered_overlap),sort_keys=True))
    captured=capsys.readouterr(); print(captured.out)
