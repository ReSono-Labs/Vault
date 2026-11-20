from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.vault_runtime.background_agent.routines import (
    compute_catch_up_occurrences,
    compute_next_due_utc,
    source_fingerprint_changed,
)


def test_dst_spring_forward_and_fall_back_schedule_calculation() -> None:
    # America/New_York springs forward on 2026-03-08 at 02:00 -> 03:00
    before_spring = datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc)  # 01:30 EST
    next_spring = compute_next_due_utc(
        rule={"kind": "cron", "cron": "30 2 * * *"},
        timezone_name="America/New_York",
        after_utc=before_spring,
    )
    assert next_spring is not None
    assert next_spring.tzinfo is timezone.utc
    assert next_spring > before_spring

    # America/New_York falls back on 2026-11-01 at 02:00 -> 01:00
    before_fall = datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc)  # 00:30 EDT
    next_fall = compute_next_due_utc(
        rule={"kind": "cron", "cron": "30 1 * * *"},
        timezone_name="America/New_York",
        after_utc=before_fall,
    )
    assert next_fall is not None
    assert next_fall.tzinfo is timezone.utc
    assert next_fall > before_fall


def test_catch_up_coalescing_rules_and_lateness_calculation() -> None:
    base_due = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
    now = datetime(2026, 11, 17, 11, 30, tzinfo=timezone.utc)
    hourly_rule = {"kind": "cron", "cron": "0 * * * *"}

    # Read/preparation recurring template coalesces missed unstarted occurrences into one with lateness recorded
    read_template = {
        "effect_bearing": False,
        "manual_retry": False,
        "request": {"objective": "Prepare inbox digest", "autonomy": "limited"},
    }
    coalesced = compute_catch_up_occurrences(
        rule=hourly_rule,
        timezone_name="UTC",
        next_due_utc=base_due,
        now_utc=now,
        template=read_template,
        has_started_or_attempted=False,
    )
    assert len(coalesced.occurrences_to_dispatch) == 1
    assert coalesced.coalesced_count == 4  # 08:00, 09:00, 10:00, 11:00 coalesced
    assert coalesced.lateness_seconds > 0
    assert coalesced.next_due_utc == datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)

    # Effect-bearing or attempted work is NEVER coalesced
    write_template = {
        "effect_bearing": True,
        "manual_retry": False,
        "request": {"objective": "Send daily status email", "autonomy": "expanded"},
    }
    uncoalesced = compute_catch_up_occurrences(
        rule=hourly_rule,
        timezone_name="UTC",
        next_due_utc=base_due,
        now_utc=now,
        template=write_template,
        has_started_or_attempted=False,
    )
    assert uncoalesced.coalesced is False
    assert uncoalesced.requires_revalidation_if_late is True


def test_source_diff_fingerprint_skips_unchanged_sources_and_provider_backoff() -> None:
    state_a = {"messages": [{"id": "m1", "etag": "v1"}]}
    state_b = {"messages": [{"id": "m1", "etag": "v1"}]}
    state_c = {"messages": [{"id": "m1", "etag": "v1"}, {"id": "m2", "etag": "v1"}]}

    changed_1, fp_1 = source_fingerprint_changed(None, state_a)
    assert changed_1 is True
    changed_2, fp_2 = source_fingerprint_changed(fp_1, state_b)
    assert changed_2 is False
    assert fp_2 == fp_1
    changed_3, fp_3 = source_fingerprint_changed(fp_2, state_c)
    assert changed_3 is True
    assert fp_3 != fp_1

