"""Scoped background coordination tools for the shared conversation runtime (prompt: coordinator_prompt.py)."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationResult

from .coordination_contracts import OwnerScope
from .coordination_repository import CoordinationRepository


def register_background_conversation_tools(*, catalog, database_url: str, resolve_principal, coordinator) -> None:
    from .routines import BackgroundRoutines

    repository = CoordinationRepository(database_url=database_url)
    routine_service = BackgroundRoutines(database_url=database_url)

    def paired_link(cursor, session_id):
        cursor.execute("SELECT to_regclass('vault_private.link_companion_link') AS binding")
        if cursor.fetchone()["binding"] is None:
            return False
        cursor.execute(
            "SELECT 1 FROM vault_private.link_companion_link WHERE session_id=%s", (session_id,),
        )
        return cursor.fetchone() is not None

    def inspect(context, arguments):
        scope = OwnerScope(context.user_id, context.workspace_id)
        with repository._connect() as connection, connection.cursor() as cursor:
            repository._owner(cursor, scope)
            repository._authority(cursor, scope, context.local_session_id, None)
            cursor.execute(
                """SELECT worker_id, role_key, status, spec_json->>'purpose' AS purpose
                   FROM vault_private.vault_background_workers
                   WHERE user_id=%s AND workspace_id=%s AND status<>'deleted'
                   ORDER BY created_at DESC, worker_id DESC LIMIT 50""",
                (scope.user_id, scope.workspace_id),
            )
            specialists = [dict(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT routine_id, status, timezone, rule_json AS schedule,
                          template_json->'request'->>'objective' AS objective,
                          COALESCE(template_json->'request'->>'goal_type','routine') AS kind,
                          next_due_at
                   FROM vault_private.vault_background_routines
                   WHERE user_id=%s AND workspace_id=%s AND status<>'deleted'
                   ORDER BY created_at DESC, routine_id DESC LIMIT 50""",
                (scope.user_id, scope.workspace_id),
            )
            routines = []
            for row in cursor.fetchall():
                routine = dict(row)
                due = routine["next_due_at"]
                routine["next_due_at"] = due.isoformat() if due else None
                routines.append(routine)
            link = paired_link(cursor, context.local_session_id)
            cursor.execute(
                """SELECT action_id, kind, title, arguments_json->'rule' AS schedule,
                          arguments_json->>'timezone' AS timezone, expires_at AS review_until
                   FROM vault_private.vault_background_actions
                   WHERE user_id=%s AND workspace_id=%s AND state='pending' AND expires_at>now()
                     AND (%s OR COALESCE(origin_conversation_id, origin_json->>'conversation_id')=%s)
                   ORDER BY created_at DESC LIMIT 50""",
                (scope.user_id, scope.workspace_id, link, context.conversation_id),
            )
            pending_approvals = [
                {**row, "review_until": row["review_until"].isoformat()} for row in cursor.fetchall()
            ]
        return ToolInvocationResult(
            "Retrieved specialists, saved routines, and pending approvals available for review.",
            {"specialists": specialists, "routines": routines, "pendingApprovals": pending_approvals,
             "pendingRoutines": [item for item in pending_approvals if item["kind"] == "routine_create"]},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.inspect.v1",
        name="background_inspect",
        description="List pending approvals in this conversation and list specialists and routines with their status and next run.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=inspect,
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    from .contracts import RunLimits
    from .coordination_contracts import WorkerSpec
    from .errors import BackgroundRunConflictError
    from .worker_repository import WorkerRepository

    workers = WorkerRepository(database_url=database_url)

    def propose_specialist(context, arguments):
        scope = OwnerScope(context.user_id, context.workspace_id)
        with repository._connect() as connection, connection.cursor() as cursor:
            repository._authority(cursor, scope, context.local_session_id, None)
        allowed = {
            tool.name for tool in catalog.definitions_for(
                AgentKind.BACKGROUND, user_id=scope.user_id, workspace_id=scope.workspace_id,
            )
        }
        tool_names = tuple(arguments["tool_names"])
        if set(tool_names) - allowed:
            return ToolInvocationResult("Choose tools available to background work in this workspace.", is_error=True)
        spec = WorkerSpec(
            role_key=arguments["role_key"], purpose=arguments["purpose"], instructions=arguments["instructions"],
            tool_names=tool_names, resource_policy={}, limits=RunLimits(),
        )
        if not vault_started(context):
            # Rakazo spawn_bot is approval-exempt when the owner asked in this run.
            try:
                worker_id = workers.create_direct(scope, spec)
            except BackgroundRunConflictError as error:
                return ToolInvocationResult(str(error), is_error=True)
            return ToolInvocationResult(
                "Specialist created. Assign it work with background_start role_key or a routine.",
                {"status": "created", "workerId": worker_id, "roleKey": spec.role_key},
            )
        try:
            action = workers.propose(
                scope,
                spec,
                origin_conversation_id=context.conversation_id,
                origin_turn_id=context.turn_id,
                origin_voice_session_id=context.voice_session_id,
            )
        except BackgroundRunConflictError as error:
            return ToolInvocationResult(str(error), is_error=True)
        return ToolInvocationResult(
            "Specialist proposal is waiting for owner approval. The specialist has not been created yet.",
            {"status": "waiting_approval", "actionId": action.action_id},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.propose-specialist.v1",
        name="background_propose_specialist",
        description=("Create a background specialist with specific instructions and tools. Created at once in a turn "
                     "the owner started; in a turn Vault started it waits for the owner's approval."),
        input_schema={
            "type": "object",
            "properties": {
                "role_key": {"type": "string", "minLength": 1, "maxLength": 80},
                "purpose": {"type": "string", "minLength": 1, "maxLength": 240},
                "instructions": {"type": "string", "minLength": 1, "maxLength": 4000},
                "tool_names": {
                    "type": "array", "items": {"type": "string"}, "uniqueItems": True, "maxItems": 20,
                },
            },
            "required": ["role_key", "purpose", "instructions", "tool_names"],
            "additionalProperties": False,
        },
        handler=propose_specialist,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    def vault_started(context):
        """Whether this call comes from a turn Vault started on its own (no owner message)."""
        if not context.turn_id:
            return False
        with repository._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT submission_key LIKE 'vault-wake:%%' AS vault FROM vault_private.vault_conversation_turns
                   WHERE user_id=%s AND workspace_id=%s AND turn_id=%s""",
                (context.user_id, context.workspace_id, context.turn_id))
            row = cursor.fetchone()
        return bool(row and row["vault"])

    def propose_routine(context, arguments):
        if context.conversation_id is None:
            return ToolInvocationResult("Open the Link chat where this routine should report.", is_error=True)
        principal = resolve_principal(context.user_id, context.workspace_id, context.local_session_id)
        names = arguments["tool_names"]
        timing = [key for key in ("cron", "run_at", "delay_minutes") if key in arguments]
        if len(timing) != 1:
            return ToolInvocationResult("Choose exactly one of cron, run_at, or delay_minutes.", is_error=True)
        reminder = arguments.get("reminder", False)
        mode = timing[0]
        if reminder and (mode == "cron" or names or arguments.get("role_key")):
            return ToolInvocationResult("A plain reminder needs a one-time schedule and no tools or specialist.", is_error=True)
        rule = {"kind": "cron", "cron": arguments["cron"]} if mode == "cron" else {"kind": "once"}
        if mode == "delay_minutes":
            due = datetime.now(timezone.utc) + timedelta(minutes=arguments["delay_minutes"])
            rule["run_at"] = due.isoformat()
        elif mode == "run_at":
            rule["run_at"] = arguments["run_at"]
        available = {
            tool.name for tool in catalog.definitions_for(
                AgentKind.BACKGROUND, user_id=principal.user_id, workspace_id=principal.workspace_id,
            )
        }
        if set(names) - available:
            return ToolInvocationResult("Choose tools available to background work in this workspace.", is_error=True)

        destination = {"kind": "conversation", "conversation_id": context.conversation_id}
        if arguments.get("role_key"):
            destination["role_key"] = arguments["role_key"]
        own = not arguments.get("role_key")
        goal = "reminder" if reminder else ("self_routine" if own else "routine")
        request = {"objective": arguments["objective"], "goal_type": goal,
                   "requested_tool_names": [] if own else names,
                   "context_summary": arguments.get("context_summary", "")}
        if own:
            # Rakazo schedule_create: the bot's own schedule runs as the bot in this chat, with the
            # tools and approvals it has then. Vault wakes the coordinator here when it is due.
            destination["goal_type"] = goal
            if goal == "self_routine":
                destination["internal"] = True
        if own:
            # Vault (2026-11-19): the coordinator's own reminders and routines are saved at once in
            # every turn, including turns Vault started, and reported. Rakazo's outside-run gating was
            # built for a shared bot; here they only wake the coordinator, whose outward steps still ask.
            try:
                routine_id, due = routine_service.create_tool_free(
                    principal, rule=rule, timezone=arguments["timezone"],
                    template={"request": request, "destination": destination},
                    purpose=f"{'Reminder' if reminder else 'Routine'}: {arguments['objective'][:200]}",
                )
            except (BackgroundRunConflictError, BackgroundRunAuthorizationError, KeyError, ValueError) as error:
                return ToolInvocationResult(str(error), is_error=True)
            local = due.astimezone(ZoneInfo(arguments["timezone"])).isoformat()
            return ToolInvocationResult(
                ("Reminder saved. It will post in this chat at the saved time." if reminder else
                 "Routine saved. Each time it is due, Vault wakes you in this chat to do it with your tools."),
                {"status": "scheduled", "routineId": routine_id, "schedule": rule,
                 "timezone": arguments["timezone"], "nextRunAt": due.isoformat(), "nextRunLocal": local},
            )
        if not vault_started(context):
            # The owner asked for this specialist routine in this turn: their request is the decision.
            try:
                routine_id, due = routine_service.create_owner_requested(
                    principal, rule=rule, timezone=arguments["timezone"],
                    template={"request": request, "destination": destination},
                )
            except (BackgroundRunConflictError, BackgroundRunAuthorizationError, KeyError, ValueError) as error:
                return ToolInvocationResult(str(error), is_error=True)
            return ToolInvocationResult(
                "Specialist routine saved. Each time it is due, the specialist runs it with the tools listed.",
                {"status": "scheduled", "routineId": routine_id, "schedule": rule, "timezone": arguments["timezone"],
                 "nextRunAt": due.isoformat(), "nextRunLocal": due.astimezone(ZoneInfo(arguments["timezone"])).isoformat()},
            )
        # A specialist routine set up by a turn Vault started (for example while reading an email or an
        # agent's reply) still waits for the owner, since it hands that specialist scheduled tool access.
        try:
            action = routine_service.propose(
                principal,
                rule=rule,
                timezone=arguments["timezone"],
                template={"request": request, "destination": destination},
                grant_id=None,
                origin_conversation_id=context.conversation_id,
                origin_turn_id=context.turn_id,
            )
        except (BackgroundRunConflictError, KeyError, ValueError) as error:
            return ToolInvocationResult(str(error), is_error=True)
        return ToolInvocationResult(
            "Routine proposal is waiting for owner approval.",
            {"status": "waiting_approval", "actionId": action.action_id,
             "schedule": rule, "timezone": arguments["timezone"]},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.propose-routine.v1",
        name="background_propose_routine",
        description=('Create a reminder or recurring job for yourself in this chat. Use for "remind me in 10 minutes" '
                     'or "every morning send me the AI headlines". Repeats: cron. One-shot: run_at or delay_minutes. '
                     "A repeating job carries out the user's lasting request each time, not a copy of what was decided today. "
                     "Your own schedules, and a specialist's (role_key) routine the owner asks for, are saved immediately; a "
                     "specialist routine set up in a turn Vault started waits for approval."),
        input_schema={
            "type": "object",
            "properties": {
                "objective": {"type": "string", "minLength": 1, "maxLength": 2000},
                "context_summary": {
                    "type": "string", "maxLength": 4000,
                    "description": "Relevant conversation context, sources, and constraints needed for this work.",
                },
                "cron": {"type": "string", "description": "Five-field cron in the specified local timezone."},
                "run_at": {"type": "string", "description": "One-time ISO 8601 date and time with UTC offset."},
                "delay_minutes": {"type": "integer", "minimum": 1, "maximum": 525600,
                                  "description": "Minutes from this request until the one-time run."},
                "reminder": {"type": "boolean", "description": "Deliver the objective as a plain one-time reminder."},
                "timezone": {"type": "string", "description": "IANA timezone such as America/New_York."},
                "role_key": {"type": "string", "description": "Optional existing specialist role."},
                "tool_names": {
                    "type": "array", "items": {"type": "string"}, "uniqueItems": True, "maxItems": 20,
                },
            },
            "required": ["objective", "timezone", "tool_names"],
            "additionalProperties": False,
        },
        handler=propose_routine,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    def follow_up(context, arguments):
        """The coordinator schedules its own wake-up in this chat.

        Donor: Rakazo's run instructions link unfinished work to a one-shot follow-up and cancel it
        when the work closes (run-instructions.prompt.ts, schedule-tools.ts @83db73c). Vault saves it
        as a tool-free one-time routine; when it is due the coordinator is woken here with the note
        and does the work itself with this chat's tools and approvals."""
        if context.conversation_id is None:
            return ToolInvocationResult("Follow-ups belong to a chat.", is_error=True)
        principal = resolve_principal(context.user_id, context.workspace_id, context.local_session_id)
        timing = [key for key in ("run_at", "delay_minutes") if key in arguments]
        if len(timing) != 1:
            return ToolInvocationResult("Choose exactly one of run_at or delay_minutes.", is_error=True)
        timezone_name = arguments.get("timezone") or "America/New_York"
        try:
            ZoneInfo(timezone_name)
        except Exception:
            return ToolInvocationResult("Use an IANA timezone such as America/New_York.", is_error=True)
        if timing[0] == "delay_minutes":
            run_at = (datetime.now(timezone.utc) + timedelta(minutes=arguments["delay_minutes"])).isoformat()
        else:
            run_at = arguments["run_at"]
        rule = {"kind": "once", "run_at": run_at}
        template = {
            "request": {"objective": arguments["note"], "goal_type": "follow_up",
                        "requested_tool_names": [], "context_summary": arguments.get("context_summary", "")},
            "destination": {"kind": "conversation", "conversation_id": context.conversation_id,
                            "internal": True, "goal_type": "follow_up"},
        }
        if arguments.get("work_id"):
            rule["parent_work_id"] = arguments["work_id"]
            template["parent_work_id"] = arguments["work_id"]
        # Vault (2026-11-19): follow-ups are saved at once in every turn, including turns Vault started.
        try:
            routine_id, due = routine_service.create_tool_free(
                principal, rule=rule, timezone=timezone_name, template=template,
                purpose=f"Follow-up: {arguments['note'][:200]}",
            )
        except (BackgroundRunConflictError, BackgroundRunAuthorizationError, ValueError) as error:
            return ToolInvocationResult(str(error), is_error=True)
        return ToolInvocationResult(
            "Follow-up saved. Vault will wake you in this chat at that time with the note.",
            {"status": "scheduled", "routineId": routine_id, "dueAt": due.isoformat(),
             "dueLocal": due.astimezone(ZoneInfo(timezone_name)).isoformat()},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.follow-up.v1",
        name="background_follow_up",
        description=("Wake yourself in this chat later to do or check something: 'in 10 minutes find the "
                     "AI headlines', 'check tomorrow whether the reply came'. One-shot; saved at once, also when you set "
                     "it yourself for an open loop. When it is due you run again here with the note and your tools."),
        input_schema={
            "type": "object",
            "properties": {
                "note": {"type": "string", "minLength": 1, "maxLength": 2000,
                         "description": "What to do or check when woken, written as an instruction to yourself."},
                "context_summary": {"type": "string", "maxLength": 4000,
                                    "description": "Details from this chat the follow-up needs."},
                "delay_minutes": {"type": "integer", "minimum": 1, "maximum": 525600},
                "run_at": {"type": "string", "description": "ISO 8601 date and time with UTC offset."},
                "timezone": {"type": "string", "description": "IANA timezone for reporting the time."},
                "work_id": {"type": "string", "description": ("Optional background work ID from coordinatorState.openWork "
                            "(not a scratchpad item ID); the follow-up is cancelled when that work finishes.")},
            },
            "required": ["note"],
            "additionalProperties": False,
        },
        handler=follow_up,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    def manage_routine(context, arguments):
        from .errors import BackgroundRunAuthorizationError

        principal = resolve_principal(context.user_id, context.workspace_id, context.local_session_id)
        routine_id = arguments["routine_id"]
        operation = arguments["operation"]
        try:
            if operation == "run_now":
                call_key = str(uuid5(NAMESPACE_URL, f"{context.turn_id}:{context.tool_call_id}"))
                work_id, state = routine_service.run_now(
                    principal, routine_id, call_key=call_key, jobs=coordinator.jobs,
                )
                return ToolInvocationResult(
                    "Manual run accepted. The result will go to the routine's saved destination.",
                    {"routineId": routine_id, "workId": work_id, "status": state},
                )
            if operation == "reschedule":
                cron, run_at = arguments.get("cron"), arguments.get("run_at")
                timezone_name = arguments.get("timezone")
                if bool(cron) == bool(run_at) or not timezone_name:
                    return ToolInvocationResult("Provide a timezone and either cron or a one-time run_at.", is_error=True)
                rule = {"kind": "cron", "cron": cron} if cron else {"kind": "once", "run_at": run_at}
                routine_service.update_schedule(principal, routine_id, rule=rule, timezone=timezone_name)
            else:
                operation_handler = {
                    "pause": routine_service.pause, "resume": routine_service.resume, "cancel": routine_service.cancel,
                }[operation]
                operation_handler(principal, routine_id)
        except (BackgroundRunAuthorizationError, BackgroundRunConflictError, KeyError, ValueError) as error:
            return ToolInvocationResult(str(error), is_error=True)
        return ToolInvocationResult(
            "Routine updated. Inspect it to verify its state and next run.",
            {"routineId": routine_id, "operation": operation},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.manage-routine.v1",
        name="background_manage_routine",
        description="Pause, resume, cancel, change the time of, or run an existing routine now after an explicit owner request.",
        input_schema={
            "type": "object",
            "properties": {
                "routine_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "operation": {"type": "string", "enum": ["pause", "resume", "cancel", "reschedule", "run_now"]},
                "cron": {"type": "string"},
                "run_at": {"type": "string"},
                "timezone": {"type": "string"},
            },
            "required": ["routine_id", "operation"],
            "additionalProperties": False,
        },
        handler=manage_routine,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    from uuid import NAMESPACE_URL, uuid5
    from .contracts import BackgroundRunRequest
    from .coordination_contracts import WorkRequest
    from .output_contract import background_output_schema
    from .errors import BackgroundRunAuthorizationError

    def start_work(context, arguments):
        scope = OwnerScope(context.user_id, context.workspace_id)
        destination = {
            "kind": "conversation",
            "conversation_id": context.conversation_id,
            "turn_id": context.turn_id,
        }
        role_key = arguments.get("role_key")
        new_specialist = arguments.get("new_specialist")
        worker_spec = None
        if new_specialist is not None:
            if role_key:
                return ToolInvocationResult("Choose an existing role or propose a new specialist.", is_error=True)
            role_key = new_specialist["role_key"]
            if coordinator._find_approved_worker(scope, role_key) is not None:
                return ToolInvocationResult("That role already exists. Select its role_key directly.", is_error=True)
            names = tuple(new_specialist["tool_names"])
            available = {tool.name for tool in catalog.definitions_for(
                AgentKind.BACKGROUND, user_id=scope.user_id, workspace_id=scope.workspace_id,
            )}
            if set(names) - available:
                return ToolInvocationResult("Choose tools available to background work in this workspace.", is_error=True)
            worker_spec = WorkerSpec(
                role_key=role_key, purpose=new_specialist["purpose"],
                instructions=new_specialist["instructions"], tool_names=names,
                resource_policy={}, limits=RunLimits(),
            )
            if not vault_started(context):
                # Owner-asked: create it now (Rakazo spawn_bot) and assign the work straight away.
                try:
                    workers.create_direct(scope, worker_spec)
                except BackgroundRunConflictError as error:
                    return ToolInvocationResult(str(error), is_error=True)
                worker_spec = None
        elif role_key and coordinator._find_approved_worker(scope, role_key) is None:
            return ToolInvocationResult("That specialist is unavailable.", is_error=True)
        if role_key:
            destination["role_key"] = role_key
        call_key = f"chat:{context.conversation_id}:{context.turn_id}:{context.tool_call_id}"
        objective = arguments["objective"]
        requested_tools = tuple(arguments.get("tool_names", ()))
        if arguments.get("tool_names") == []:
            # The background runtime uses an omitted allowlist to select default tools.
            requested_tools = ("__none__",)
        request = BackgroundRunRequest(
            run_id=str(uuid5(NAMESPACE_URL, call_key)),
            objective=objective,
            instruction_profile="chat-background",
            success_criteria=("Complete the requested work and verify the result.",),
            result_schema=background_output_schema(),
            original_request=objective,
            context_summary=arguments.get("context_summary", ""),
            verification_method="Check the work against the requested outcome.",
            completion_conditions=("Verify and report the outcome.",),
            requested_tool_names=requested_tools,
        )
        try:
            work_id = coordinator.observe(scope, "explicit_goal", call_key, {
                "work_request": WorkRequest(request, None, context.local_session_id, destination),
                "worker_spec": worker_spec,
            })
            outcome = coordinator.plan_dispatch(work_id)
        except (BackgroundRunAuthorizationError, BackgroundRunConflictError) as error:
            return ToolInvocationResult(str(error), is_error=True)
        if outcome.pending_action_id:
            return ToolInvocationResult(
                "The assignment is saved and will start after the specialist is approved.",
                {"workId": work_id, "status": outcome.state.value, "actionId": outcome.pending_action_id},
            )
        return ToolInvocationResult(
            "Background work was accepted. The result will go to this conversation.",
            {"workId": work_id, "status": outcome.state.value},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.start.v1",
        name="background_start",
        description="Queue long-running work, asked for or useful to the owner's goal. Use the coordinator or an approved specialist and return the result to this chat.",
        input_schema={
            "type": "object",
            "properties": {
                "objective": {"type": "string", "minLength": 1, "maxLength": 2000},
                "context_summary": {
                    "type": "string", "maxLength": 4000,
                    "description": "Relevant conversation context, sources, and constraints needed for this work.",
                },
                "role_key": {"type": "string", "description": "Optional approved specialist role."},
                "new_specialist": {
                    "type": "object",
                    "description": "Propose a new specialist and save this assignment behind its approval.",
                    "properties": {
                        "role_key": {"type": "string", "minLength": 1, "maxLength": 80},
                        "purpose": {"type": "string", "minLength": 1, "maxLength": 240},
                        "instructions": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "tool_names": {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "maxItems": 20},
                    },
                    "required": ["role_key", "purpose", "instructions", "tool_names"],
                    "additionalProperties": False,
                },
                "tool_names": {
                    "type": "array", "items": {"type": "string"}, "uniqueItems": True, "maxItems": 20,
                },
            },
            "required": ["objective"],
            "additionalProperties": False,
        },
        handler=start_work,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    def propose_memory_lookup(context, arguments):
        scope = OwnerScope(context.user_id, context.workspace_id)
        with repository._connect() as connection, connection.cursor() as cursor:
            repository._authority(cursor, scope, context.local_session_id, None)
        try:
            action = workers.propose_memory_lookup(
                scope, arguments["role_key"],
                conversation_id=context.conversation_id, turn_id=context.turn_id,
            )
        except BackgroundRunConflictError as error:
            return ToolInvocationResult(str(error), is_error=True)
        if action is None:
            return ToolInvocationResult("This specialist already has read-only memory search in its profile.")
        return ToolInvocationResult(
            "Read-only memory search awaits owner approval.",
            {"status": "waiting_approval", "actionId": action.action_id},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.propose-memory-lookup.v1",
        name="background_propose_memory_lookup",
        description="Request owner approval to add read-only Vault memory search to an existing specialist.",
        input_schema={
            "type": "object",
            "properties": {"role_key": {"type": "string", "minLength": 1, "maxLength": 80}},
            "required": ["role_key"],
            "additionalProperties": False,
        },
        handler=propose_memory_lookup,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    def review_approval(context, arguments):
        scope = OwnerScope(context.user_id, context.workspace_id)
        with repository._connect() as connection, connection.cursor() as cursor:
            repository._authority(cursor, scope, context.local_session_id, None)
            if not paired_link(cursor, context.local_session_id):
                return ToolInvocationResult("Open this approval from your paired Link chat.", is_error=True)
            action_id = arguments.get("action_id")
            cursor.execute(
                """WITH queued AS (
                       SELECT action_id FROM vault_private.vault_background_actions
                       WHERE user_id=%s AND workspace_id=%s
                         AND (%s::text IS NULL OR action_id=%s)
                         AND kind IN ('worker_create','execution_grant','routine_create')
                         AND work_id IS NULL AND state='pending' AND expires_at>now()
                       ORDER BY created_at, action_id LIMIT 20 FOR UPDATE
                   )
                   UPDATE vault_private.vault_background_actions AS action
                   SET origin_json=jsonb_set(action.origin_json,'{link_review_turn_id}',to_jsonb(%s::text)),
                       updated_at=now()
                   FROM queued WHERE action.action_id=queued.action_id
                   RETURNING action.action_id, action.title""",
                (scope.user_id, scope.workspace_id, action_id, action_id, context.turn_id),
            )
            pending = [dict(row) for row in cursor.fetchall()]
        if not pending:
            return ToolInvocationResult("There are no pending approvals to review.", {"items": []})
        return ToolInvocationResult(
            "Link will show these requests one at a time. Each requires its own decision.",
            {"status": "waiting_approval", "items": pending},
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.review-approval.v1",
        name="background_review_approval",
        description="Start a one-at-a-time approval review in paired Link chat. Omit action_id to review pending proposals, or supply an exact ID to review one.",
        input_schema={
            "type": "object",
            "properties": {"action_id": {"type": "string", "minLength": 1, "maxLength": 64}},
            "additionalProperties": False,
        },
        handler=review_approval,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))

    def reopen_routines(context, arguments):
        from .actions import BackgroundActions

        principal = resolve_principal(context.user_id, context.workspace_id, context.local_session_id)
        with repository._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """WITH latest_turn AS (
                       SELECT origin_json->>'turn_id' AS turn_id
                       FROM vault_private.vault_background_actions
                       WHERE user_id=%s AND workspace_id=%s AND kind='routine_create'
                         AND origin_json->>'conversation_id'=%s
                       ORDER BY created_at DESC, action_id DESC LIMIT 1
                   )
                   SELECT action_id, title, state, expires_at<=now() AS expired
                   FROM vault_private.vault_background_actions, latest_turn
                   WHERE user_id=%s AND workspace_id=%s AND kind='routine_create'
                     AND origin_json->>'conversation_id'=%s AND origin_json->>'turn_id'=latest_turn.turn_id
                   ORDER BY created_at, action_id LIMIT 20""",
                (principal.user_id, principal.workspace_id, context.conversation_id,
                 principal.user_id, principal.workspace_id, context.conversation_id),
            )
            proposals = cursor.fetchall()
        actions = BackgroundActions(database_url=database_url)
        items = []
        for row in proposals:
            if row["state"] == "pending" and not row["expired"]:
                items.append({"actionId": row["action_id"], "title": row["title"], "status": "pending"})
            elif row["state"] == "expired" or (row["state"] == "pending" and row["expired"]):
                try:
                    reopened = actions.reopen(principal, row["action_id"], channel="browser",
                                              channel_generation=principal.session_id)
                except BackgroundRunConflictError:
                    continue
                items.append({"actionId": reopened.action_id, "title": reopened.title, "status": "pending"})
        return ToolInvocationResult(
            "These schedules are waiting for approval. Review them in this session.",
            {"items": items},
        ) if items else ToolInvocationResult(
            "No expired or pending schedules from the latest proposal in this chat could be reopened."
        )

    catalog.register(ToolDefinition(
        tool_id="builtin.background.reopen-routines.v1",
        name="background_reopen_routines",
        description="Resubmit expired schedule proposals from this chat's latest setup when the user asks. Each still needs approval.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=reopen_routines,
        effect_class="write",
        audiences=frozenset({AgentKind.VOICE}),
        conversation_only=True,
    ))
