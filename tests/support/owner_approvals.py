"""Shared test helpers moved out of test modules (TST-01)."""

import psycopg

from app.core.security.tokens import hash_token
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService


def _service(context, **kwargs):
    from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository
    from app.vault_runtime.background_agent.owner_approvals import OwnerApprovals
    CoordinationRepository(database_url=context[0]).ensure_schema()
    return OwnerApprovals(database_url=context[0], **{"poll_seconds": 0.05, **kwargs})


def _identities(context):
    return LocalIdentityService(repository=LocalIdentityRepository(database_url=context[0]), setup_credential_hash=hash_token("setup"))


def _link(context):
    """The owner's paired Link phone session."""
    from app.vault_runtime.link_companion.schema import ensure_link_companion_schema
    link = _identities(context).login(username="owner", password="owner-password").principal
    with psycopg.connect(context[0]) as connection, connection.cursor() as cursor:
        ensure_link_companion_schema(cursor)
        cursor.execute("""INSERT INTO vault_private.link_companion_link (id,display_name,pairing_id,session_id)
            VALUES (1,'Phone','pairing-1',%s) ON CONFLICT (id) DO UPDATE SET session_id=EXCLUDED.session_id""", (link.session_id,))
    return link
