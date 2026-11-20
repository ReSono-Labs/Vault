"""Explicit additive index migration; never called by ensure_schema or startup."""
from __future__ import annotations

import re

from app.vault_runtime.memory_search.postgres import VECTOR_EXPRESSION, VECTOR_PREDICATE, vector_version

HNSW_NAME = "ix_vault_memory_embedding_hnsw_768"
LEXICAL_NAME = "ix_vault_memory_content_fts_simple"
INDEX_DDL = {
    HNSW_NAME: f"""CREATE INDEX CONCURRENTLY {HNSW_NAME}
        ON vault_private.vault_memory_embeddings USING hnsw
        (({VECTOR_EXPRESSION}) vector_cosine_ops) WHERE {VECTOR_PREDICATE}""",
    LEXICAL_NAME: f"""CREATE INDEX CONCURRENTLY {LEXICAL_NAME}
        ON vault_private.vault_memory_records USING gin (to_tsvector('simple',content_text))""",
}
# PostgreSQL canonical renderings. Exact comparison fails closed on conflicting
# definitions instead of trusting IF NOT EXISTS or dropping someone else's index.
EXPECTED_DEFINITIONS = {
    HNSW_NAME: f"""CREATE INDEX {HNSW_NAME} ON vault_private.vault_memory_embeddings
        USING hnsw (((embedding)::vector(768)) vector_cosine_ops)
        WHERE ((provider = 'ollama'::text) AND (model = 'embeddinggemma:300m'::text)
        AND (dimensions = 768) AND (vector_dims(embedding) = 768)
        AND (vector_norm(embedding) > (0)::double precision))""",
    LEXICAL_NAME: f"""CREATE INDEX {LEXICAL_NAME} ON vault_private.vault_memory_records
        USING gin (to_tsvector('simple'::regconfig, content_text))""",
}


class IndexMigrationError(RuntimeError):
    pass


def _normalized(definition):
    # Whitespace within SQL literals is meaningful; do not normalize a changed
    # provider/model into an apparently identical partial-index predicate.
    parts = re.split(r"('(?:''|[^'])*')", definition)
    return "".join(part if index % 2 else re.sub(r"\s+", "", part)
                   for index, part in enumerate(parts))


def inventory(connection):
    with connection.cursor() as cursor:
        version = vector_version(cursor)
        cursor.execute("""SELECT count(*), count(*) FILTER (WHERE
            provider='ollama' AND model='embeddinggemma:300m' AND dimensions=768),
            count(*) FILTER (WHERE provider='ollama' AND model='embeddinggemma:300m'
                AND dimensions=768 AND (vector_dims(embedding)<>768 OR vector_norm(embedding)=0))
            FROM vault_private.vault_memory_embeddings""")
        total, compatible, invalid = cursor.fetchone()
        return dict(vector_version=".".join(map(str, version)), total=total,
                    compatible=compatible, invalid=invalid)


def _state(cursor, name):
    cursor.execute("""SELECT i.indisvalid,CASE WHEN i.indexrelid IS NOT NULL THEN pg_get_indexdef(c.oid) END
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_index i ON i.indexrelid=c.oid
        WHERE n.nspname='vault_private' AND c.relname=%s""", (name,))
    return cursor.fetchone()


def ensure_indexes(connection):
    """Caller supplies an authorized administrative autocommit connection.

    Only these exact indexes can be rebuilt, and only when invalid. No data or
    source tables are removed. A failed concurrent build can be retried safely.
    """
    if not connection.autocommit or connection.info.transaction_status != 0:
        raise IndexMigrationError("concurrent index migration requires autocommit")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(73102702)")
        if not cursor.fetchone()[0]:
            raise IndexMigrationError("indexed memory migration is already running")
        try:
            report = inventory(connection)
            if report["invalid"]:
                raise IndexMigrationError("matching embeddings have invalid dimensions or zero norm")
            for name, ddl in INDEX_DDL.items():
                state = _state(cursor, name)
                if state is not None:
                    if state[1] is None or _normalized(state[1]) != _normalized(EXPECTED_DEFINITIONS[name]):
                        raise IndexMigrationError("owned index name has a conflicting definition")
                    if state[0]:
                        continue
                    cursor.execute(f"DROP INDEX CONCURRENTLY vault_private.{name}")
                cursor.execute(ddl)
                state = _state(cursor, name)
                if state is None or not state[0] or _normalized(state[1]) != _normalized(EXPECTED_DEFINITIONS[name]):
                    raise IndexMigrationError("created index did not match the reviewed definition")
            return report
        finally:
            cursor.execute("SELECT pg_advisory_unlock(73102702)")
