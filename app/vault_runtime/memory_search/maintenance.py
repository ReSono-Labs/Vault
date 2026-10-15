"""Own existing index migration/backfill lifecycle, never run repairs in live reads."""
import logging
from threading import Event, Thread

from .indexed import PgvectorMemorySearchBackend
from .indexes import ensure_indexes
from .postgres import QueryOptions


class IndexedMemoryMaintenance:
    def __init__(self, *, database_url, service, identities, enabled=True):
        self.database_url, self.service, self.identities = database_url, service, identities
        self.enabled = enabled
        self.ready, self.stopping = Event(), Event()
        self.state = "building" if enabled else "disabled"
        self._cursors = {}
        self._thread = None

    def start(self):
        if self._thread is not None:
            raise ValueError("Memory maintenance already started.")
        self._thread = Thread(target=self._run, name="vault-memory-index-maintenance", daemon=True)
        self._thread.start()

    def initialize_indexes(self):
        if not self.enabled:
            return
        import psycopg
        with psycopg.connect(self.database_url, connect_timeout=5, autocommit=True) as connection:
            # Statement timeout is administrative and separate from read budgets.
            connection.execute("SET statement_timeout='120s'")
            ensure_indexes(connection)
        self.service._search_backend = PgvectorMemorySearchBackend(memories=self.service._repository,
            options=QueryOptions(timeout_ms=1500, ef_search=100, max_scan_tuples=20000))
        self.state = "ready"
        self.ready.set()

    def repair_batch(self):
        scopes = self.identities.active_storage_identities()
        self._cursors = {k:v for k,v in self._cursors.items() if k in scopes}
        for scope in scopes:
            if self.stopping.is_set():
                return
            advanced = False
            def progress(memory_id):
                nonlocal advanced
                advanced = True
                self._cursors[scope] = memory_id
            stored, failed = self.service.ensure_vectors(user_id=scope[0],workspace_id=scope[1],limit=2,
                after_memory_id=self._cursors.get(scope,""),progress=progress,
                cancel_requested=self.stopping.is_set)
            if not advanced:
                self._cursors[scope] = ""  # Wrap; failed rows retry next traversal without starving later rows.
            if stored or failed:
                logging.getLogger("vault.memory_maintenance").info(
                    "memory_vector_batch stored=%s failed=%s", stored, failed)

    def _run(self):
        try:
            self.initialize_indexes()
        except Exception:
            self.state = "index_failed"
            logging.getLogger("vault.memory_maintenance").error("memory_index_setup_failed")
            return  # Preserve canonical data/legacy reads; no guessed conflicting-index repair.
        while not self.stopping.is_set():
            try:
                self.repair_batch()
            except Exception:
                logging.getLogger("vault.memory_maintenance").warning("memory_vector_batch_unavailable")
            self.stopping.wait(60)

    def close(self):
        self.stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
