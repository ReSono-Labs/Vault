"""Read-only indexed queries over Vault's existing scoped memory authority."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from app.vault_runtime.memory.models import MemoryRecord
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.retrieval import EMBEDDING_SIMILARITY_FLOOR

MODEL = "embeddinggemma:300m"
DIMENSIONS = 768
VECTOR_EXPRESSION = "embedding::vector(768)"
VECTOR_PREDICATE = """provider='ollama' AND model='embeddinggemma:300m'
    AND dimensions=768 AND vector_dims(embedding)=768 AND vector_norm(embedding)>0"""
COLUMNS = """m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
    m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
    m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at"""


@dataclass(frozen=True, slots=True)
class QueryOptions:
    # Operator/test choices, not a product SLA or production feature default.
    timeout_ms: int
    ef_search: int
    max_scan_tuples: int

    def __post_init__(self):
        if any(type(value) is not int for value in (self.timeout_ms, self.ef_search, self.max_scan_tuples)):
            raise ValueError("query options must be integers")
        if self.timeout_ms <= 0 or not 1 <= self.ef_search <= 1000 or self.max_scan_tuples <= 0:
            raise ValueError("invalid bounded query options")


def vector_literal(values) -> str:
    if len(values) != DIMENSIONS:
        raise ValueError("query vector must have 768 dimensions")
    numbers = [float(value) for value in values]
    if any(not isfinite(value) or abs(value) > 3.4028234663852886e38 for value in numbers):
        raise ValueError("query vector must contain finite float32 values")
    if not any(abs(value) >= 1.401298464324817e-45 for value in numbers):
        raise ValueError("query vector must be nonzero")
    return "[" + ",".join(map(str, numbers)) + "]"


def vector_version(cursor) -> tuple[int, ...]:
    cursor.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
    row = cursor.fetchone()
    try:
        version = tuple(int(part) for part in row[0].split(".")) if row else ()
    except (ValueError, TypeError):
        version = ()
    if version < (0, 8):
        raise RuntimeError("indexed memory requires pgvector >= 0.8")
    return version


class PgvectorMemoryQueries:
    def __init__(self, *, memories: MemoryRepository, options: QueryOptions):
        self.memories = memories
        self.options = options

    def _configure(self, cursor, *, user_id, workspace_id):
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", (str(self.options.timeout_ms),))
        self.memories._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)

    def authorize(self, *, user_id, workspace_id):
        with self.memories._connect() as connection, connection.cursor() as cursor:
            self._configure(cursor, user_id=user_id, workspace_id=workspace_id)

    def semantic_statement(self, *, exact=False):
        # Alias-free compatible embedding predicates resolve to e (m has none).
        source = f"""FROM vault_private.vault_memory_embeddings e
            JOIN vault_private.vault_memory_records m ON m.memory_id=e.memory_id
            JOIN vault_private.local_workspace_memberships membership
              ON membership.workspace_id=m.workspace_id AND membership.user_id=%s
                AND membership.status='active'
            WHERE {self.memories._scope_sql('m')} AND m.lifecycle_status='active'
              AND {VECTOR_PREDICATE}
              AND e.content_fingerprint=encode(sha256(convert_to(m.content_text,'UTF8')),'hex')"""
        if exact:
            return f"""WITH eligible AS MATERIALIZED (
                SELECT {COLUMNS}, {VECTOR_EXPRESSION} AS query_embedding {source}
            ) SELECT {COLUMNS.replace('m.', '')}, query_embedding <=> %s::vector(768) AS distance
              FROM eligible WHERE query_embedding <=> %s::vector(768) <= %s
              ORDER BY query_embedding <=> %s::vector(768) LIMIT %s"""
        return f"""SELECT {COLUMNS}, {VECTOR_EXPRESSION} <=> %s::vector(768) AS distance
            {source} AND {VECTOR_EXPRESSION} <=> %s::vector(768) <= %s
            ORDER BY {VECTOR_EXPRESSION} <=> %s::vector(768) LIMIT %s"""

    def semantic_parameters(self, *, user_id, workspace_id, literal, limit, floor, exact=False):
        scope = (user_id, workspace_id, user_id)
        tail = (literal, 1.0 - floor, literal, limit)
        return (*scope, literal, *tail) if exact else (literal, *scope, *tail)

    def semantic(self, values, *, user_id, workspace_id, limit=25, floor=EMBEDDING_SIMILARITY_FLOOR, exact=False):
        literal = vector_literal(values)
        bounded = max(1, min(int(limit), 25))
        if not isfinite(floor) or not -1 <= floor <= 1:
            raise ValueError("invalid similarity floor")
        with self.memories._connect() as connection, connection.cursor() as cursor:
            self._configure(cursor, user_id=user_id, workspace_id=workspace_id)
            vector_version(cursor)
            cursor.execute("""SELECT set_config('hnsw.iterative_scan','strict_order',true),
                set_config('hnsw.ef_search',%s,true), set_config('hnsw.max_scan_tuples',%s,true)""",
                (str(self.options.ef_search), str(self.options.max_scan_tuples)))
            parameters = dict(user_id=user_id, workspace_id=workspace_id, literal=literal,
                              limit=bounded, floor=floor)
            cursor.execute(self.semantic_statement(exact=exact),
                           self.semantic_parameters(**parameters, exact=exact))
            rows = cursor.fetchall()
            if not exact and len(rows) < bounded:
                cursor.execute(self.semantic_statement(exact=True),
                               self.semantic_parameters(**parameters, exact=True))
                rows = cursor.fetchall()
            return tuple((MemoryRecord(*row[:16]), 1.0 - float(row[-1])) for row in rows)

    def lexical(self, query, *, user_id, workspace_id):
        with self.memories._connect() as connection, connection.cursor() as cursor:
            self._configure(cursor, user_id=user_id, workspace_id=workspace_id)
            scope = (workspace_id, user_id)
            cursor.execute(f"""SELECT {COLUMNS} FROM vault_private.vault_memory_records m
                WHERE {self.memories._scope_sql('m')} AND m.lifecycle_status='active'
                  AND (lower(m.memory_key)=%s OR lower(m.content_text)=%s)
                ORDER BY m.updated_at DESC,m.memory_id LIMIT 25""",
                (*scope, query.strip().lower(), query.strip().lower()))
            exact = tuple(MemoryRecord(*row) for row in cursor.fetchall())
            cursor.execute(f"""SELECT {COLUMNS} FROM vault_private.vault_memory_records m
                WHERE {self.memories._scope_sql('m')} AND m.lifecycle_status='active'
                  AND to_tsvector('simple',m.content_text) @@ plainto_tsquery('simple',%s)
                ORDER BY ts_rank_cd(to_tsvector('simple',m.content_text),
                    plainto_tsquery('simple',%s)) DESC,m.updated_at DESC,m.memory_id LIMIT 25""",
                (*scope, query, query))
            full_text = tuple(MemoryRecord(*row) for row in cursor.fetchall())
        fallback = self.memories.lexical_memories(user_id=user_id, workspace_id=workspace_id, query=query, limit=25)
        records = {}
        for record in (*exact, *full_text, *fallback):
            records.setdefault(record.memory_id, record)
        return tuple(records.values())[:25]
