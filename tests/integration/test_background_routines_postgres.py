"""PostgreSQL integration tests for BackgroundRoutines, follow-ups, DST/catch-up coalescing, and quiet initiative (Task 7)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.vault_runtime.background_agent.contracts import AutonomyProfile, BackgroundRunRequest
from app.vault_runtime.background_agent.coordination_contracts import (
    ExecutionOutcome,
    OwnerScope,
    WorkRequest,
    WorkScope,
    WorkState,
)
from app.vault_runtime.background_agent.coordinator import BackgroundCoordinator
from app.vault_runtime.background_agent.output_contract import background_output_schema
from app.vault_runtime.background_agent.results import BackgroundResults
from app.vault_runtime.background_agent.routines import BackgroundRoutines
from tests.support.background_authority import components


def _template(
    objective: str = "Morning inbox preparation",
    *,
    effect_bearing: bool = False,
    autonomy: str = "limited",
    tools: list[str] | None = None,
) -> dict[str, object]:
    return {
        "effect_bearing": effect_bearing,
        "request": {
            "objective": objective,
            "instruction_profile": "background-routine",
            "success_criteria": ["Digest compiled accurately"],
            "result_schema": background_output_schema(),
            "autonomy": autonomy,
            "original_request": objective,
            "verification_method": "Verify against inbox state",
            "completion_conditions": ["Digest ready"],
            "requested_tool_names": tools or ["tasks_list"],
        },
        "destination": {"kind": "activity"},
    }


def _setup(context):
    db_url = context[0]
    principal = context[1]
    m, repo, owner, _req, authority, workers = components(context)
    with psycopg.connect(db_url) as conn:
        conn.execute(
            """INSERT INTO vault_private.vault_background_execution_grants
               (grant_id, user_id, workspace_id, purpose, policy_json)
               VALUES ('grant-routine-1', %s, %s, 'Routine standing grant', %s)""",
            (owner.user_id, owner.workspace_id, Jsonb({"tool_names": ["tasks_list"], "resource_policy": {}})),
        )
    routines = BackgroundRoutines(database_url=db_url)
    return {
        "db_url": db_url,
        "principal": principal,
        "owner": owner,
        "repo": repo,
        "authority": authority,
        "workers": workers,
        "routines": routines,
        "grant_id": "grant-routine-1",
    }


def test_routine_create_future_edit_duplicate_ticks_and_concurrent_schedulers(context) -> None:
    env = _setup(context)
    db_url = env["db_url"]
    principal = env["principal"]
    owner = env["owner"]
    routines = env["routines"]

    base_now = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    routine_id = routines.create(
        principal,
        rule={"kind": "cron", "cron": "0 * * * *", "anchor_utc": base_now.isoformat()},
        timezone="UTC",
        template=_template("Hourly prep"),
        grant_id=env["grant_id"],
    )
    assert routine_id

    due_time = datetime(2026, 11, 17, 13, 0, tzinfo=timezone.utc)

    # Concurrent schedulers ticking at the same instant create at most ONE occurrence and ONE work item
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(lambda _: routines.tick(due_time), range(4)))
    assert sum(counts) == 1

    # Duplicate tick at the same instant creates 0 additional occurrences
    assert routines.tick(due_time) == 0

    with psycopg.connect(db_url) as conn:
        occ_count = conn.execute(
            "SELECT count(*) FROM vault_private.vault_background_occurrences WHERE user_id=%s AND workspace_id=%s AND routine_id=%s",
            (owner.user_id, owner.workspace_id, routine_id),
        ).fetchone()[0]
    assert occ_count == 1

    # Future edit increments routine version and updates next_due_at
    new_version = routines.update_schedule(
        principal,
        routine_id,
        rule={"kind": "cron", "cron": "30 * * * *", "anchor_utc": due_time.isoformat()},
        timezone="America/New_York",
    )
    assert new_version == 2
    assert routines.tick(datetime(2026, 11, 17, 13, 30, tzinfo=timezone.utc)) == 1


def test_catch_up_never_coalesces_attempted_or_effect_bearing_work(context) -> None:
    env = _setup(context)
    db_url = env["db_url"]
    principal = env["principal"]
    owner = env["owner"]
    routines = env["routines"]

    anchor = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
    # 1. Read-only recurring routine behind by 3 hours coalesces into 1 occurrence with lateness recorded
    read_routine = routines.create(
        principal,
        rule={"kind": "cron", "cron": "0 * * * *", "anchor_utc": anchor.isoformat()},
        timezone="UTC",
        template=_template("Read-only hourly digest", effect_bearing=False),
        grant_id=env["grant_id"],
    )
    # 2. Effect-bearing routine behind by 3 hours is NOT coalesced and requires revalidation/approval when late
    write_routine = routines.create(
        principal,
        rule={"kind": "cron", "cron": "0 * * * *", "anchor_utc": anchor.isoformat()},
        timezone="UTC",
        template=_template("Effect-bearing hourly send", effect_bearing=True, autonomy="expanded"),
        grant_id=env["grant_id"],
    )

    late_now = datetime(2026, 11, 17, 11, 15, tzinfo=timezone.utc)
    created = routines.tick(late_now)
    assert created == 2

    with psycopg.connect(db_url) as conn:
        read_work = conn.execute(
            "SELECT state, request_json FROM vault_private.vault_background_work WHERE user_id=%s AND workspace_id=%s AND routine_id=%s",
            (owner.user_id, owner.workspace_id, read_routine),
        ).fetchone()
        write_work = conn.execute(
            "SELECT state, request_json FROM vault_private.vault_background_work WHERE user_id=%s AND workspace_id=%s AND routine_id=%s",
            (owner.user_id, owner.workspace_id, write_routine),
        ).fetchone()

    assert read_work is not None
    read_meta = read_work[1]["destination"].get("schedule_meta", {})
    assert read_meta.get("coalesced") is True
    assert read_meta.get("coalesced_count") == 3
    assert read_meta.get("lateness_seconds") > 0

    assert write_work is not None
    write_meta = write_work[1]["destination"].get("schedule_meta", {})
    assert write_meta.get("coalesced") is False
    # Late time-sensitive write is held in waiting_approval / requires_revalidation rather than executing late blindly
    assert write_work[0] == WorkState.WAITING_APPROVAL.value
    assert write_meta.get("requires_revalidation") is True


def test_declined_or_completed_parent_cancels_followup_and_pause_cancel_invalidates_queued_work(
    context,
) -> None:
    env = _setup(context)
    db_url = env["db_url"]
    principal = env["principal"]
    owner = env["owner"]
    repo = env["repo"]
    routines = env["routines"]

    anchor = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    parent_req = WorkRequest(
        request=BackgroundRunRequest(
            run_id="run-parent-1",
            objective="Parent open work",
            instruction_profile="background-default",
            success_criteria=("Done",),
            result_schema=background_output_schema(),
            original_request="Parent open work",
            verification_method="Check",
            completion_conditions=("Done",),
        ),
        grant_id=env["grant_id"],
        local_session_id=None,
        destination={"kind": "activity"},
    )
    parent_work_id = repo.create_work(owner, parent_req, "chat:parent-1")

    # Schedule a follow-up linked to parent_work_id
    followup_id = routines.schedule_followup(
        principal,
        parent_work_id=parent_work_id,
        due_at=anchor + timedelta(hours=2),
        template=_template("Follow up on parent work"),
        grant_id=env["grant_id"],
    )
    assert followup_id

    # Completing or cancelling/declining the parent work cancels the linked follow-up before it fires
    routines.cancel_followups_for_work(owner, parent_work_id, reason="parent_completed")
    assert routines.tick(anchor + timedelta(hours=3)) == 0

    # Also test pause/cancel invalidating already-queued routine work transactionally
    r2 = routines.create(
        principal,
        rule={"kind": "cron", "cron": "0 * * * *", "anchor_utc": anchor.isoformat()},
        timezone="UTC",
        template=_template("Routine to pause"),
        grant_id=env["grant_id"],
    )
    assert routines.tick(anchor + timedelta(hours=1)) == 1
    routines.pause(principal, r2)

    with psycopg.connect(db_url) as conn:
        r2_status = conn.execute(
            "SELECT status FROM vault_private.vault_background_routines WHERE routine_id=%s",
            (r2,),
        ).fetchone()[0]
        w2_state = conn.execute(
            "SELECT state FROM vault_private.vault_background_work WHERE routine_id=%s",
            (r2,),
        ).fetchone()[0]
    assert r2_status == "paused"
    assert w2_state == WorkState.CANCELLED.value


def test_restore_does_not_send_stale_calendar_change(context) -> None:
    env = _setup(context)
    db_url = env["db_url"]
    principal = env["principal"]
    owner = env["owner"]
    routines = env["routines"]

    now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    r_cal = routines.create(
        principal,
        rule={"kind": "cron", "cron": "0 * * * *", "anchor_utc": now.isoformat()},
        timezone="UTC",
        template=_template("Calendar change watcher"),
        grant_id=env["grant_id"],
    )
    # Ingest initial calendar snapshot fingerprint
    first_changed = routines.observe_source_change(
        owner,
        source_kind="calendar_sync",
        source_id="cal-account-1",
        items=[{"event_id": "ev-1", "etag": "v1", "starts_at": "2026-11-18T09:00:00Z"}],
        now=now,
    )
    assert first_changed is True

    # Unchanged calendar sync does not wake model or create a new change event
    unchanged = routines.observe_source_change(
        owner,
        source_kind="calendar_sync",
        source_id="cal-account-1",
        items=[{"event_id": "ev-1", "etag": "v1", "starts_at": "2026-11-18T09:00:00Z"}],
        now=now + timedelta(minutes=5),
    )
    assert unchanged is False

    # Simulate backup restore reconciliation: routines start paused and baseline source fingerprints
    # are reconciled as pre-restore state so stale calendar changes from before restore are not sent
    routines.reconcile_after_restore(
        owner,
        now=now + timedelta(hours=4),
        calendar_snapshots={"cal-account-1": [{"event_id": "ev-1", "etag": "v2", "starts_at": "2026-11-18T10:00:00Z"}]},
    )

    with psycopg.connect(db_url) as conn:
        status = conn.execute(
            "SELECT status FROM vault_private.vault_background_routines WHERE routine_id=%s",
            (r_cal,),
        ).fetchone()[0]
    assert status == "paused"

    # Re-observing the restored snapshot produces False (no stale calendar change notification/work sent)
    stale_after_restore = routines.observe_source_change(
        owner,
        source_kind="calendar_sync",
        source_id="cal-account-1",
        items=[{"event_id": "ev-1", "etag": "v2", "starts_at": "2026-11-18T10:00:00Z"}],
        now=now + timedelta(hours=4, minutes=1),
    )
    assert stale_after_restore is False
    # Paused routine does not fire on tick after restore until explicitly resumed by owner
    assert routines.tick(now + timedelta(hours=5)) == 0
