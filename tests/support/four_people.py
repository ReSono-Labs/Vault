"""One four-person setup for isolation tests (STD-FOURUSER).

The device owner and three users, each with a private workspace, plus one explicitly
shared workspace (owner, Ada and Ben are members; Cy is not). ``cross_private`` runs an
attempt for all 12 ordered (actor, victim) pairs against the victim's private workspace
and returns the pairs where the attempt was NOT refused, so a test asserts ``== []``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import psycopg

from app.core.security.tokens import hash_token
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService

NAMES = ("owner", "ada", "ben", "cy")
SHARED_MEMBERS = ("ada", "ben")


@dataclass(frozen=True)
class Person:
    name: str
    principal: LocalPrincipal

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def private_workspace(self) -> str:
        return self.principal.workspace_id


@dataclass
class FourPeople:
    identities: LocalIdentityService
    people: dict[str, Person]
    shared_workspace: str

    def __getitem__(self, name: str) -> Person:
        return self.people[name]

    @property
    def owner(self) -> Person:
        return self.people["owner"]

    def pairs(self) -> list[tuple[Person, Person]]:
        return [(self.people[a], self.people[b]) for a in NAMES for b in NAMES if a != b]

    def cross_private(self, attempt: Callable[[Person, Person], object]) -> list[str]:
        """Pairs where ``attempt(actor, victim)`` was not refused. Returning anything, even an
        empty list, counts: entering someone's private workspace must raise."""
        allowed = []
        for actor, victim in self.pairs():
            try:
                attempt(actor, victim)
            except Exception:
                continue
            allowed.append(f"{actor.name}->{victim.name}")
        return allowed

    def leave_shared(self, name: str) -> None:
        self.identities.revoke_member(principal=self.owner.principal, workspace_id=self.shared_workspace,
                                      username=name)


def build_four_people(database_url: str) -> FourPeople:
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityService(repository=LocalIdentityRepository(database_url=database_url),
                                      setup_credential_hash=hash_token("setup"))
    identities.ensure_schema()
    owner = identities.bootstrap_owner(setup_credential="setup", username="owner", password="owner-password",
                                       display_name="Owner", experience_style="strict").principal
    people = {"owner": Person("owner", owner)}
    for name in NAMES[1:]:
        identities.create_user(actor=owner, username=name, password=f"{name}-password",
                               display_name=name.title(), experience_style="balanced")
        people[name] = Person(name, identities.login(username=name, password=f"{name}-password").principal)
    shared = identities.create_workspace(principal=owner, display_name="Family")
    for name in SHARED_MEMBERS:
        identities.add_member(principal=owner, workspace_id=shared, username=name)
    assert len({person.private_workspace for person in people.values()}) == 4
    return FourPeople(identities, people, shared)
