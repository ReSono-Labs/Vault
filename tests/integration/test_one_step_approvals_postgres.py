"""APPROVE-1STEP: the agent prepares a change and calls its confirm tool in the same turn; the owner's
Approve/Decline card is the confirmation. Approve applies the exact prepared change once, Decline or no
answer applies nothing, and a same-turn confirm without a recorded owner approval is still refused."""
from __future__ import annotations

import json
import threading
import time

import psycopg
import pytest

from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository
from app.vault_runtime.background_agent.owner_approvals import OwnerApprovals
from app.vault_runtime.contacts_tools import register_contacts_tools
from app.vault_runtime.conversation_tools.approval_gate import ApprovalGate, ApprovalText
from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory.repository import MemoryConfirmationError, MemoryNotFoundError
from app.vault_runtime.memory.service import MemoryService
from app.vault_runtime.memory.tools import register_memory_tools
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.session_tools.brokers.contacts import contacts_tool_result
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tasks.repository import TaskRepository
from app.vault_runtime.tasks_tools import register_tasks_tools
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.tools import LocalToolAuthority, VoiceToolRuntime
from tests.support.voice_runtime import _new_session


def _gate(database_url, catalog, *, ttl_seconds=300):
    CoordinationRepository(database_url=database_url).ensure_schema()
    records = PersonalDataRepository(database_url=database_url)
    records.ensure_schema()
    approvals = OwnerApprovals(database_url=database_url, poll_seconds=0.05, ttl_seconds=ttl_seconds)
    catalog.set_approval_gate(ApprovalGate(approvals=approvals, text=ApprovalText(database_url=database_url, records=records)))
    return approvals


def _answer(approvals, principal, choice, **where):
    """The owner taps the card (website) when it appears; records what the card showed."""
    shown = []

    def run():
        for _ in range(250):
            question = approvals.pending(principal, **where)
            if question:
                shown.append(question)
                approvals.answer(principal, question["id"], choice, channel="browser")
                return
            time.sleep(0.02)
    thread = threading.Thread(target=run)
    thread.start()
    return thread, shown


def _owner_approval_states(database_url, domain_ref):
    with psycopg.connect(database_url) as connection:
        return [row[0] for row in connection.execute(
            "SELECT state FROM vault_private.vault_background_actions WHERE kind='owner_approval' AND domain_ref=%s",
            (domain_ref,)).fetchall()]


# ── memory, on the Voice path (VoiceToolRuntime → catalog → gate) ───────────────

def _memory_setup(voice_context, *, gated=True, ttl_seconds=300):
    url, _identity, owner, _second, memories, voices = voice_context
    source = memories.append_transcript(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="source-session", entry_index=0, role="user",
        event_type="voice.user.final", text_content="I drive a blue Honda Civic",
    )
    memory = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="source-session",
        candidate=MemoryCandidate(
            subject_id="user", domain="personal", memory_type="fact", memory_key="car",
            content_text="Drives a blue Honda Civic, bought in 2019", source_authority="user_asserted",
            confidence="high", sensitivity="normal", intent="create", visibility="private",
        ),
        evidence=((source.entry_id, "user_statement", "user_asserted", source.text_content),),
    )
    voice = _new_session(voices, owner.principal)
    authority = LocalToolAuthority(database_url=url)
    catalog = ToolCatalog(authorizer=authority.authorize)
    register_memory_tools(catalog=catalog, repository=memories, service=MemoryService(repository=memories))
    for name, effect in (("memory_prepare_correction", "write"), ("memory_prepare_forget", "delete"),
                         ("memory_confirm_action", "write")):
        authority.set_grant(actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
                            tool_name=name, effect_class=effect, voice_enabled=True, background_enabled=False)
    approvals = _gate(url, catalog, ttl_seconds=ttl_seconds) if gated else None
    runtime = VoiceToolRuntime(catalog=catalog, authority=authority)
    utterance = memories.append_transcript_next(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id=voice.voice_session_id, role="user", event_type="voice.user.final",
        text_content="I sold the Civic, I drive a Toyota Corolla now",
    )

    def context(call):
        # Prepare and confirm share this one utterance: the same turn.
        return ToolInvocationContext(
            agent=AgentKind.VOICE, user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            local_session_id=owner.principal.session_id, voice_session_id=voice.voice_session_id,
            tool_call_id=call, user_utterance_id=utterance.entry_index, user_utterance=utterance.text_content,
        )
    return url, owner, memories, memory, voice, catalog, runtime, approvals, context


def _current(memories, owner, memory_id):
    return memories.memory(user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id, memory_id=memory_id)


def test_voice_memory_correction_same_turn_raises_the_card_and_approve_applies_it_once(voice_context):
    url, owner, memories, memory, voice, _catalog, runtime, approvals, context = _memory_setup(voice_context)
    prepared = runtime.invoke(name="memory_prepare_correction", context=context("prepare"), arguments={
        "memoryId": memory.memory_id, "newContent": "Drives a blue Toyota Corolla, bought in 2019"})
    action_id = prepared.structured_content["actionId"]
    thread, shown = _answer(approvals, owner.principal, "allow_once", voice_session_id=voice.voice_session_id)
    confirmed = runtime.invoke(name="memory_confirm_action", arguments={"actionId": action_id}, context=context("confirm"))
    thread.join(timeout=10)
    assert not confirmed.is_error, confirmed.text
    assert shown and shown[0]["title"] == "Update a memory"
    assert shown[0]["detail"] == ["Before: Drives a blue Honda Civic, bought in 2019",
                                  "After: Drives a blue Toyota Corolla, bought in 2019"]
    after = _current(memories, owner, memory.memory_id)
    assert after.content_text == "Drives a blue Toyota Corolla, bought in 2019"
    assert (after.domain, after.memory_type, after.memory_key, after.sensitivity, after.visibility) == (
        memory.domain, memory.memory_type, memory.memory_key, memory.sensitivity, memory.visibility)
    assert _owner_approval_states(url, action_id) == ["completed"]
    # Once: the same prepared action cannot be applied again, even with another approval.
    thread, _ = _answer(approvals, owner.principal, "allow_once", voice_session_id=voice.voice_session_id)
    again = runtime.invoke(name="memory_confirm_action", arguments={"actionId": action_id}, context=context("confirm-2"))
    thread.join(timeout=10)
    assert again.is_error


@pytest.mark.parametrize("choice", ["deny", "timeout"])
def test_voice_memory_correction_declined_or_unanswered_applies_nothing(voice_context, choice):
    _url, owner, memories, memory, voice, _catalog, runtime, approvals, context = _memory_setup(
        voice_context, ttl_seconds=1 if choice == "timeout" else 300)
    prepared = runtime.invoke(name="memory_prepare_correction", context=context("prepare"), arguments={
        "memoryId": memory.memory_id, "newContent": "Drives a blue Toyota Corolla, bought in 2019"})
    thread = None
    if choice == "deny":
        thread, _ = _answer(approvals, owner.principal, "deny", voice_session_id=voice.voice_session_id)
    result = runtime.invoke(name="memory_confirm_action", context=context("confirm"),
                            arguments={"actionId": prepared.structured_content["actionId"]})
    if thread:
        thread.join(timeout=10)
    assert result.is_error and ("denied" in result.text if choice == "deny" else "did not answer" in result.text)
    assert _current(memories, owner, memory.memory_id).content_text == "Drives a blue Honda Civic, bought in 2019"


def test_voice_memory_forget_same_turn_approve_deletes_and_decline_keeps(voice_context):
    _url, owner, memories, memory, voice, _catalog, runtime, approvals, context = _memory_setup(voice_context)
    declined = runtime.invoke(name="memory_prepare_forget", arguments={"memoryId": memory.memory_id}, context=context("p1"))
    thread, _ = _answer(approvals, owner.principal, "deny", voice_session_id=voice.voice_session_id)
    result = runtime.invoke(name="memory_confirm_action", context=context("c1"),
                            arguments={"actionId": declined.structured_content["actionId"]})
    thread.join(timeout=10)
    assert result.is_error and _current(memories, owner, memory.memory_id).memory_id == memory.memory_id

    prepared = runtime.invoke(name="memory_prepare_forget", arguments={"memoryId": memory.memory_id}, context=context("p2"))
    thread, shown = _answer(approvals, owner.principal, "allow_once", voice_session_id=voice.voice_session_id)
    result = runtime.invoke(name="memory_confirm_action", context=context("c2"),
                            arguments={"actionId": prepared.structured_content["actionId"]})
    thread.join(timeout=10)
    assert not result.is_error, result.text
    assert shown[0]["title"] == "Forget a memory" and result.structured_content["action"] == "forgotten"
    with pytest.raises(MemoryNotFoundError):
        _current(memories, owner, memory.memory_id)


def test_same_turn_memory_confirm_without_owner_approval_is_refused(voice_context):
    # No gate: nothing records an owner approval, so the same utterance cannot confirm its own prepare.
    _url, owner, memories, memory, _voice, catalog, _runtime, _approvals, context = _memory_setup(voice_context, gated=False)
    for prepare, arguments in (("memory_prepare_correction", {"memoryId": memory.memory_id, "newContent": "Drives a Corolla"}),
                               ("memory_prepare_forget", {"memoryId": memory.memory_id})):
        prepared = catalog.invoke(prepare, arguments, context=context(f"{prepare}-p"))
        with pytest.raises(MemoryConfirmationError):
            catalog.invoke("memory_confirm_action", {"actionId": prepared.structured_content["actionId"]},
                           context=context(f"{prepare}-c"))
    assert _current(memories, owner, memory.memory_id).content_text == "Drives a blue Honda Civic, bought in 2019"


# ── tasks, on the Chat path ────────────────────────────────────────────────────

def _chat(owner, call, turn="turn-1"):
    return ToolInvocationContext(agent=AgentKind.VOICE, user_id=owner.user_id, workspace_id=owner.workspace_id,
                                 local_session_id=owner.session_id, conversation_id="conversation-1", turn_id=turn,
                                 tool_call_id=call)


def _tasks(context, *, gated=True, ttl_seconds=300):
    url, owner, *_ = context
    repository = TaskRepository(database_url=url)
    repository.ensure_schema()
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_tasks_tools(catalog=catalog, repository=repository)
    approvals = _gate(url, catalog, ttl_seconds=ttl_seconds) if gated else None
    return url, owner, repository, catalog, approvals


def _task_texts(repository, owner):
    return [item.task_text for item in repository.list(user_id=owner.user_id, workspace_id=owner.workspace_id,
                                                  include_completed=True, limit=50)]


def test_task_same_turn_approve_applies_exact_text_once(context):
    url, owner, repository, catalog, approvals = _tasks(context)
    prepared = json.loads(catalog.invoke("tasks_add", {"text": "Call the dentist on Friday"}, context=_chat(owner, "p")).text)
    thread, shown = _answer(approvals, owner, "allow_once", turn_id="turn-1")
    result = catalog.invoke("tasks_confirm_action", {"actionId": prepared["actionId"], "contentHash": prepared["contentHash"]},
                            context=_chat(owner, "c"))
    thread.join(timeout=10)
    assert not result.is_error, result.text
    assert shown[0]["detail"] == ["Call the dentist on Friday"]
    assert _task_texts(repository, owner) == ["Call the dentist on Friday"]
    replay = catalog.invoke("tasks_confirm_action", {"actionId": prepared["actionId"], "contentHash": prepared["contentHash"]},
                            context=_chat(owner, "c2"))
    assert replay.is_error and _task_texts(repository, owner) == ["Call the dentist on Friday"]
    assert _owner_approval_states(url, prepared["actionId"])[0] == "completed"


@pytest.mark.parametrize("choice", ["deny", "timeout"])
def test_task_declined_or_unanswered_applies_nothing(context, choice):
    _url, owner, repository, catalog, approvals = _tasks(context, ttl_seconds=1 if choice == "timeout" else 300)
    prepared = json.loads(catalog.invoke("tasks_add", {"text": "Call the dentist"}, context=_chat(owner, "p")).text)
    thread = _answer(approvals, owner, "deny", turn_id="turn-1")[0] if choice == "deny" else None
    result = catalog.invoke("tasks_confirm_action", {"actionId": prepared["actionId"], "contentHash": prepared["contentHash"]},
                            context=_chat(owner, "c"))
    if thread:
        thread.join(timeout=10)
    assert result.is_error and _task_texts(repository, owner) == []


def test_same_turn_task_confirm_without_owner_approval_is_refused(context):
    _url, owner, repository, catalog, _ = _tasks(context, gated=False)
    CoordinationRepository(database_url=context[0]).ensure_schema()     # the approvals table exists, but has no approval
    prepared = json.loads(catalog.invoke("tasks_add", {"text": "Call the dentist"}, context=_chat(owner, "p")).text)
    result = catalog.invoke("tasks_confirm_action", {"actionId": prepared["actionId"], "contentHash": prepared["contentHash"]},
                            context=_chat(owner, "c"))
    assert result.is_error and "stale" in result.text and _task_texts(repository, owner) == []


# ── contacts, on the Chat path ─────────────────────────────────────────────────

def _contacts(context, *, ttl_seconds=300):
    url, owner, *_ = context
    records = PersonalDataRepository(database_url=url)
    records.ensure_schema()
    catalog = ToolCatalog(authorizer=lambda *_: True)
    register_contacts_tools(catalog=catalog, store=records)
    approvals = _gate(url, catalog, ttl_seconds=ttl_seconds)
    # An existing contact, saved earlier from the website.
    seeded = contacts_tool_result(store=records, account_id=owner.user_id, workspace_id=owner.workspace_id,
                                  voice_realtime_session_id="web-management", tool_call_id="seed-1",
                                  tool_name="contacts_prepare_save",
                                  arguments={"actionType": "create", "firstName": "Ada", "lastName": "Lovelace",
                                             "emailAddress": "ada@example.com", "phoneNumber": "555-0100"})
    contacts_tool_result(store=records, account_id=owner.user_id, workspace_id=owner.workspace_id,
                         voice_realtime_session_id="web-management", tool_call_id="seed-2",
                         tool_name="contacts_confirm_pending", arguments={"pendingActionId": seeded["pendingActionId"]})
    return owner, records, catalog, approvals


def _contact(records, owner):
    items = records.list_private_records(account_id=owner.user_id, workspace_id=owner.workspace_id,
                                         source_table="contacts_entries", limit=10)
    assert len(items) == 1
    return items[0]


def _prepare_phone_change(catalog, records, owner):
    contact = _contact(records, owner)
    prepared = catalog.invoke("contacts_prepare_save", {"actionType": "update", "contactId": contact["sourceId"],
                                                        "phoneNumber": "555-0199"}, context=_chat(owner, "p"))
    assert not prepared.is_error, prepared.text
    return prepared.structured_content["pendingActionId"]


def test_contact_change_same_turn_approve_applies_once_and_keeps_untouched_fields(context):
    owner, records, catalog, approvals = _contacts(context)
    pending_id = _prepare_phone_change(catalog, records, owner)
    thread, shown = _answer(approvals, owner, "allow_once", turn_id="turn-1")
    result = catalog.invoke("contacts_confirm_pending", {"pendingActionId": pending_id}, context=_chat(owner, "c"))
    thread.join(timeout=10)
    assert not result.is_error, result.text
    assert shown[0]["title"] == "Change a contact"
    payload = _contact(records, owner)["sourcePayload"]
    assert (payload["first_name"], payload["last_name"], payload["email_address"], payload["phone_number"]) == (
        "Ada", "Lovelace", "ada@example.com", "555-0199")
    replay = catalog.invoke("contacts_confirm_pending", {"pendingActionId": pending_id}, context=_chat(owner, "c2"))
    assert replay.is_error


@pytest.mark.parametrize("choice", ["deny", "timeout"])
def test_contact_change_declined_or_unanswered_applies_nothing_even_with_the_models_approve_flag(context, choice):
    owner, records, catalog, approvals = _contacts(context, ttl_seconds=1 if choice == "timeout" else 300)
    pending_id = _prepare_phone_change(catalog, records, owner)
    thread = _answer(approvals, owner, "deny", turn_id="turn-1")[0] if choice == "deny" else None
    # The model's own approve flag is not an owner approval: the call still waits for the card.
    result = catalog.invoke("contacts_confirm_pending", {"pendingActionId": pending_id, "approve": True},
                            context=_chat(owner, "c"))
    if thread:
        thread.join(timeout=10)
    assert result.is_error
    assert _contact(records, owner)["sourcePayload"]["phone_number"] == "555-0100"
