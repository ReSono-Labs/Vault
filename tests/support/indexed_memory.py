"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

import psycopg

from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory_search.indexes import (
    HNSW_NAME, LEXICAL_NAME, IndexMigrationError, ensure_indexes,
)
from app.vault_runtime.memory_search.postgres import QueryOptions
from tests.support.memory import _entry


# Synthetic operator settings for this test only, not production defaults/SLA.
OPTIONS = QueryOptions(timeout_ms=10000, ef_search=100, max_scan_tuples=20000)


VECTOR = [1.0]+[0.0]*767


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
