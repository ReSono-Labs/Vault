"""Scoped durable response events and execution ownership over C03A final turns."""
import json
from psycopg.types.json import Jsonb
from uuid import uuid4

from .contracts import ConflictError,InputError,NotFoundError,identifier,text_fingerprint
from .repository import ConversationRepository
from .runtime_schema import ensure_runtime_schema
from .history_projection import assemble_history

MAX_EVENTS = 4096
MAX_EVENT_BYTES = 65536
MAX_TURN_BYTES = 2_097_152
MAX_SEGMENT_TURNS = 32
MAX_SEGMENT_TEXT_BYTES = 48_000


class ConversationRuntimeStore(ConversationRepository):
    def end_session(self,principal,conversation_id,expected_history_version,*,request_review=False,idle_seconds=None,size_only=False):
        from .contracts import history_version
        expected = None if size_only else history_version(expected_history_version)
        conversation_id = identifier(conversation_id)
        scope = self._scope(principal,conversation_id)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            header = self._header(cursor,principal,conversation_id,lock=True)
            if header[6]!="open" or (not size_only and header[4]!=expected):
                raise ConflictError("Conversation history changed before session end.")
            if idle_seconds is not None:
                cursor.execute("""SELECT 1 FROM vault_private.vault_conversations
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s
                    AND activity_at<=now()-%s*interval '1 second' AND activity_session_id=%s""",
                  (*scope,idle_seconds,principal.session_id))
                if cursor.fetchone() is None:
                    raise ConflictError("Chat became active before idle review.")
            cursor.execute("""SELECT segment_id,ordinal FROM vault_private.vault_conversation_segments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND state='open' FOR UPDATE""",scope)
            segment = cursor.fetchone()
            if segment is None:
                raise ConflictError("Conversation has no open segment.")
            cursor.execute("""SELECT state FROM vault_private.vault_conversation_turns
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",(*scope,segment[0]))
            states = [r[0] for r in cursor.fetchall()]
            if any(s in {"submitted","running"} for s in states):
                raise ConflictError("An active response must finish before ending its session.")
            if size_only:
                cursor.execute("""SELECT count(*),coalesce(sum(octet_length(input_text)+event_bytes),0)
                  FROM vault_private.vault_conversation_turns
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",
                  (*scope,segment[0]))
                count,text_bytes=cursor.fetchone()
                if count<MAX_SEGMENT_TURNS and text_bytes<MAX_SEGMENT_TEXT_BYTES:
                    return None
            if not states:
                cursor.execute("""SELECT segment_id,state FROM vault_private.vault_conversation_segments
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND ordinal<%s
                  ORDER BY ordinal DESC LIMIT 1""",(*scope,segment[1]))
                previous = cursor.fetchone()
                if previous and previous[1]=="sealed" and request_review:
                    self._queue_review(cursor,principal,conversation_id,previous[0])
                return dict(segmentId=previous[0] if previous else None,
                    state=previous[1] if previous else "empty",alreadyEnded=True)
            state = "sealed" if all(s=="completed" for s in states) else "incomplete"
            cursor.execute("""UPDATE vault_private.vault_conversation_segments SET state=%s,updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",
              (state,*scope,segment[0]))
            cursor.execute("""UPDATE vault_private.vault_conversation_segments SET
              first_review_ordinal=(SELECT min(ordinal) FROM vault_private.vault_conversation_turns WHERE segment_id=%s),
              last_review_ordinal=(SELECT max(ordinal) FROM vault_private.vault_conversation_turns WHERE segment_id=%s)
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",
              (segment[0],segment[0],*scope,segment[0]))
            cursor.execute("""INSERT INTO vault_private.vault_conversation_segments
              (segment_id,conversation_id,user_id,workspace_id,ordinal,state)
              VALUES(%s,%s,%s,%s,%s,'open')""",(str(uuid4()),conversation_id,principal.user_id,principal.workspace_id,segment[1]+1))
            if state=="sealed" and request_review:
                self._queue_review(cursor,principal,conversation_id,segment[0])
            cursor.execute("""UPDATE vault_private.vault_conversations SET activity_at=NULL
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s""",scope)
            return dict(segmentId=segment[0],state=state,alreadyEnded=False)

    def activity(self,principal,conversation_id):
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            self._header(cursor,principal,conversation_id,lock=True)
            cursor.execute("""UPDATE vault_private.vault_conversations SET activity_at=now(),activity_session_id=%s
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND state='open'""",
              (principal.session_id,*self._scope(principal,conversation_id)))

    def idle_conversations(self,seconds):
        with self._connect() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT c.user_id,c.workspace_id,c.conversation_id,c.activity_session_id,c.history_version
              FROM vault_private.vault_conversations c WHERE c.state='open'
                AND c.activity_at<=now()-%s*interval '1 second'
                AND EXISTS(SELECT 1 FROM vault_private.local_sessions a
                  JOIN vault_private.local_users u ON u.user_id=a.user_id
                  JOIN vault_private.local_workspace_memberships m ON m.user_id=a.user_id AND m.workspace_id=a.active_workspace_id
                  JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
                  WHERE a.session_id=c.activity_session_id AND a.user_id=c.user_id
                    AND a.active_workspace_id=c.workspace_id AND a.status='active' AND a.expires_at>now()
                    AND u.status='active' AND m.status='active' AND w.status='active')
                AND EXISTS(SELECT 1 FROM vault_private.vault_conversation_segments s
                  JOIN vault_private.vault_conversation_turns t USING(user_id,workspace_id,conversation_id,segment_id)
                  WHERE s.user_id=c.user_id AND s.workspace_id=c.workspace_id
                    AND s.conversation_id=c.conversation_id AND s.state='open')
                AND NOT EXISTS(SELECT 1 FROM vault_private.vault_conversation_turns t
                  WHERE t.user_id=c.user_id AND t.workspace_id=c.workspace_id AND t.conversation_id=c.conversation_id
                    AND t.state IN ('submitted','running'))
              ORDER BY c.activity_at LIMIT 32""",(seconds,))
            return cursor.fetchall()

    def consumer_state(self,principal,conversation_id,segment_id,consumer,state=None,detail=None):
        if consumer not in {'memory','decision'} or state not in {None,'pending','completed','failed','disabled'}:
            raise ValueError("Invalid review consumer state.")
        column=consumer+'_review_state'
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            scope=(*self._scope(principal,conversation_id),segment_id)
            if state is not None:
                cursor.execute(f"""UPDATE vault_private.vault_conversation_segments SET {column}=%s,
                    {consumer}_review_result_json=COALESCE(%s,{consumer}_review_result_json)
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
                    AND state='sealed' AND {column}<>'completed'""",(state,Jsonb(detail) if detail is not None else None,*scope))
            cursor.execute(f"""SELECT {column} FROM vault_private.vault_conversation_segments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",scope)
            row=cursor.fetchone()
            if row is None:
                raise NotFoundError("Review segment unavailable.")
            return row[0]

    def review_progress(self,principal,conversation_id):
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            self._header(cursor,principal,conversation_id)
            cursor.execute("""SELECT segment_id,ordinal,state,first_review_ordinal,last_review_ordinal,
                review_state,memory_review_state,decision_review_state,review_attempts,
                memory_review_result_json,decision_review_result_json
              FROM vault_private.vault_conversation_segments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s ORDER BY ordinal DESC LIMIT 50""",
              self._scope(principal,conversation_id))
            keys=('segmentId','ordinal','state','firstTurnOrdinal','lastTurnOrdinal',
                  'reviewState','memoryState','decisionState','attempts','memoryResult','decisionResult')
            return [dict(zip(keys,row)) for row in cursor.fetchall()]

    def _queue_review(self,cursor,principal,conversation_id,segment_id):
        cursor.execute("""UPDATE vault_private.vault_conversation_segments
          SET review_state='queued',review_session_id=%s,
              memory_review_state=CASE WHEN memory_review_state='completed' THEN 'completed' ELSE 'pending' END,
              decision_review_state=CASE WHEN decision_review_state='completed' THEN 'completed' ELSE 'pending' END,
              review_attempts=CASE WHEN review_state='queued' THEN review_attempts ELSE 0 END,review_due_at=now()
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
            AND state='sealed' AND review_state IN ('not_requested','queued','failed','blocked_authority')""",
          (principal.session_id,*self._scope(principal,conversation_id),segment_id))

    def queue_voice_review(self,principal,voice_session_id):
        """Reuse the existing review bridge/intent; never copy Voice transcripts."""
        segment_id='voice-review:'+voice_session_id
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT status,transcript_capture_state FROM vault_private.vault_voice_sessions
              WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s FOR SHARE""",
              (principal.user_id,principal.workspace_id,voice_session_id))
            row=cursor.fetchone()
            if row is None or row[0] not in ('closed','failed','lost') or row[1]=='incomplete':
                raise InputError("Finalized complete-capture Voice source required.")
            cursor.execute("""INSERT INTO vault_private.vault_conversations
              (conversation_id,user_id,workspace_id,create_key,state,source_voice_session_id)
              VALUES(%s,%s,%s,%s,'sealed',%s) ON CONFLICT(user_id,workspace_id,create_key) DO NOTHING""",
              (voice_session_id,principal.user_id,principal.workspace_id,segment_id,voice_session_id))
            cursor.execute("""INSERT INTO vault_private.vault_conversation_segments
              (segment_id,conversation_id,user_id,workspace_id,ordinal,state)
              VALUES(%s,%s,%s,%s,0,'sealed') ON CONFLICT(user_id,workspace_id,conversation_id,ordinal) DO NOTHING""",
              (segment_id,voice_session_id,principal.user_id,principal.workspace_id))
            cursor.execute("""UPDATE vault_private.vault_conversation_segments SET
              review_state=CASE WHEN review_state='completed' THEN review_state ELSE 'queued' END,
              review_session_id=%s,review_due_at=now(),review_attempts=0
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",
              (principal.session_id,*self._scope(principal,voice_session_id),segment_id))
        return segment_id

    def pending_reviews(self):
        # Metadata only; the exact current local principal is resolved before any source read.
        with self._connect() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT user_id,workspace_id,conversation_id,segment_id,review_session_id
              FROM vault_private.vault_conversation_segments WHERE state='sealed'
                AND review_state IN ('queued','running') AND review_due_at<=now()
              ORDER BY review_due_at LIMIT 32""")
            return cursor.fetchall()

    def claim_review(self,principal,conversation_id,segment_id):
        # Caller holds execution_lock('review-dispatch:'+segment_id) through finish.
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""UPDATE vault_private.vault_conversation_segments SET review_state='failed'
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
                AND review_state IN ('queued','running') AND review_attempts>=3""",
              (*self._scope(principal,conversation_id),segment_id))
            cursor.execute("""UPDATE vault_private.vault_conversation_segments
              SET review_state='running',review_attempts=review_attempts+1
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
                AND state='sealed' AND review_session_id=%s AND review_attempts<3
                AND review_state IN ('queued','running') AND review_due_at<=now()
              RETURNING review_attempts""",(*self._scope(principal,conversation_id),segment_id,principal.session_id))
            return cursor.fetchone() is not None

    def finish_review(self,principal,conversation_id,segment_id,*,completed):
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""UPDATE vault_private.vault_conversation_segments
              SET review_state=CASE WHEN %s THEN 'completed' WHEN review_attempts>=3 THEN 'failed' ELSE 'queued' END,
                  review_due_at=now()+interval '30 seconds'
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s
                AND review_state='running' AND review_session_id=%s
              RETURNING review_state,review_attempts""",
              (completed,*self._scope(principal,conversation_id),segment_id,principal.session_id))
            return cursor.fetchone()

    def block_review(self,user_id,workspace_id,conversation_id,segment_id,session_id):
        with self._connect() as connection,connection.cursor() as cursor:
            cursor.execute("""UPDATE vault_private.vault_conversation_segments
              SET review_state='blocked_authority' WHERE user_id=%s AND workspace_id=%s
                AND conversation_id=%s AND segment_id=%s AND review_session_id=%s
                AND review_state IN ('queued','running')""",
              (user_id,workspace_id,conversation_id,segment_id,session_id))

    def ensure_schema(self):
        super().ensure_schema()
        with self._connect() as connection,connection.cursor() as cursor:
            ensure_runtime_schema(cursor)

    def execution_lock(self,turn_id):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,81157))",(turn_id,))
                acquired = cursor.fetchone()[0]
            connection.commit()
            if not acquired:
                raise ConflictError("Turn execution already has an owner.")
            return connection
        except BaseException:
            connection.close()
            raise

    def replay_if_submitted(self,principal,conversation_id,key,text):
        conversation_id,key = identifier(conversation_id),identifier(key)
        fingerprint = text_fingerprint(text)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT turn_id,input_text,input_fingerprint FROM vault_private.vault_conversation_turns
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND submission_key=%s""",
              (*self._scope(principal,conversation_id),key))
            row = cursor.fetchone()
        if row is None:
            return None
        if row[1:]!=(text,fingerprint):
            raise ConflictError("Submission key already belongs to different text.")
        return self.status(principal,conversation_id,row[0])

    def claim(self,principal,turn):
        owner = str(uuid4())
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""UPDATE vault_private.vault_conversation_turns SET state='running',run_owner=%s,updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s AND state='submitted'
              RETURNING turn_id""",(owner,*self._scope(principal,turn.conversation_id),turn.turn_id))
            if cursor.fetchone() is None:
                raise ConflictError("Submitted turn cannot be claimed.")
            self._append(cursor,principal,turn,owner,"waiting",{})
        return owner

    def _append(self,cursor,principal,turn,owner,kind,payload,*,authority=True):
        if authority:
            self._require_authority(cursor,principal)
        encoded = json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":"))
        size = len(encoded.encode())
        if size>MAX_EVENT_BYTES:
            raise InputError("Conversation source event exceeds capture bound.")
        cursor.execute("""SELECT event_sequence,event_bytes FROM vault_private.vault_conversation_turns
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s
            AND run_owner=%s AND state='running' FOR UPDATE""",
          (*self._scope(principal,turn.conversation_id),turn.turn_id,owner))
        row = cursor.fetchone()
        if row is None:
            raise ConflictError("Conversation worker ownership changed.")
        # Reserve terminal/error capacity even when ordinary source budget fills.
        reserve = 0 if kind in {"error","terminal"} else 2
        if row[0]>=MAX_EVENTS-reserve or row[1]+size>MAX_TURN_BYTES-(2048 if reserve else 0):
            raise InputError("Conversation source budget exhausted.")
        sequence = row[0]+1
        cursor.execute("""INSERT INTO vault_private.vault_conversation_events
          (user_id,workspace_id,conversation_id,turn_id,sequence,kind,payload)
          VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)""",
          (*self._scope(principal,turn.conversation_id),turn.turn_id,sequence,kind,encoded))
        cursor.execute("""UPDATE vault_private.vault_conversation_turns SET event_sequence=%s,event_bytes=event_bytes+%s,
          updated_at=now() WHERE turn_id=%s AND run_owner=%s""",(sequence,size,turn.turn_id,owner))
        return sequence

    def append(self,principal,turn,owner,kind,payload):
        with self._connect() as connection,connection.cursor() as cursor:
            return self._append(cursor,principal,turn,owner,kind,payload)

    def finish(self,principal,turn,owner,*,state,answer=None,error_code=None):
        if state not in {"completed","failed","interrupted"}:
            raise ValueError("Invalid final conversation state.")
        with self._connect() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT cancel_requested FROM vault_private.vault_conversation_turns
              WHERE turn_id=%s AND user_id=%s AND workspace_id=%s AND run_owner=%s AND state='running' FOR UPDATE""",
              (turn.turn_id,principal.user_id,principal.workspace_id,owner))
            row = cursor.fetchone()
            if row is None:
                raise ConflictError("Conversation worker ownership changed.")
            if row[0] and state=="completed":
                state,answer,error_code = "interrupted",None,"turn_interrupted"
            if answer is not None:
                self._append(cursor,principal,turn,owner,"assistant_final",{"text":answer})
            if error_code is not None:
                self._append(cursor,principal,turn,owner,"error",{"code":error_code},authority=False)
            self._append(cursor,principal,turn,owner,"terminal",{"state":state},authority=False)
            cursor.execute("""UPDATE vault_private.vault_conversation_turns SET state=%s,source_coverage=%s,updated_at=now()
              WHERE turn_id=%s AND user_id=%s AND workspace_id=%s AND run_owner=%s AND state='running'""",
              (state,"complete" if state=="completed" else "incomplete",turn.turn_id,principal.user_id,principal.workspace_id,owner))

    def canceled(self,principal,turn,owner):
        try:
            with self._connect() as connection,connection.cursor() as cursor:
                self._require_authority(cursor,principal)
                cursor.execute("""SELECT cancel_requested,state,run_owner FROM vault_private.vault_conversation_turns
                  WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s""",
                  (*self._scope(principal,turn.conversation_id),turn.turn_id))
                row = cursor.fetchone()
                return row is None or row!=(False,"running",owner)
        except Exception:
            return True

    def stop_turn(self,principal,conversation_id,turn_id):
        turn = self.turn(principal,conversation_id,turn_id)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""UPDATE vault_private.vault_conversation_turns SET cancel_requested=true,updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s AND state IN ('submitted','running')""",
              (*self._scope(principal,conversation_id),turn_id))
        return turn

    def events(self,principal,conversation_id,turn_id,after=0):
        if type(after) is not int or after<0:
            raise InputError("Event cursor must be a nonnegative integer.")
        self.turn(principal,conversation_id,turn_id)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT sequence,kind,payload FROM vault_private.vault_conversation_events
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s AND sequence>%s
              ORDER BY sequence LIMIT 128""",(*self._scope(principal,conversation_id),turn_id,after))
            return tuple(dict(sequence=r[0],kind=r[1],payload=r[2]) for r in cursor.fetchall())

    def status(self,principal,conversation_id,turn_id):
        turn = self.turn(principal,conversation_id,turn_id)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT state,event_sequence,source_coverage,cancel_requested FROM vault_private.vault_conversation_turns
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s""",
              (*self._scope(principal,conversation_id),turn_id))
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("Conversation turn unavailable.")
        return dict(turnId=turn.turn_id,conversationId=turn.conversation_id,input=turn.input_text,
            historyVersion=turn.history_version,state=row[0],lastSequence=row[1],coverage=row[2],cancelRequested=row[3])

    def display_history(self, principal, conversation_id, *, before=None, limit=40):
        """Page final display text only; model evidence retains its separate reader."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InputError("History page size must be between 1 and 100.")
        if before is not None and (type(before) is not int or not 1 <= before <= 2**63-1):
            raise InputError("Invalid history cursor.")
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_authority(cursor, principal)
            self._header(cursor, principal, conversation_id, lock=False)
            cursor.execute("""SELECT t.turn_id,t.input_text,t.state,
                (SELECT e.payload->>'text' FROM vault_private.vault_conversation_events e
                 WHERE e.user_id=t.user_id AND e.workspace_id=t.workspace_id
                   AND e.conversation_id=t.conversation_id AND e.turn_id=t.turn_id
                   AND e.kind='assistant_final' ORDER BY e.sequence DESC LIMIT 1),t.ordinal,
                (SELECT jsonb_agg(jsonb_build_object('cardId',u.payload->'cardId','card',u.payload->'card',
                   'sources',u.payload->'sources') ORDER BY u.sequence) FROM vault_private.vault_conversation_events u
                 WHERE u.user_id=t.user_id AND u.workspace_id=t.workspace_id
                   AND u.conversation_id=t.conversation_id AND u.turn_id=t.turn_id AND u.kind='ui'),
                extract(epoch FROM t.created_at)::bigint,extract(epoch FROM t.updated_at)::bigint
                FROM vault_private.vault_conversation_turns t
                WHERE t.user_id=%s AND t.workspace_id=%s AND t.conversation_id=%s
                  AND (%s::bigint IS NULL OR t.ordinal<%s)
                ORDER BY t.ordinal DESC LIMIT %s""",
                (*self._scope(principal,conversation_id),before,before,limit+1))
            rows = cursor.fetchall()
        more = len(rows)>limit
        rows = rows[:limit]
        return dict(turns=[dict(turnId=r[0],input=r[1],state=r[2],answer=r[3],createdAt=r[6],updatedAt=r[7],
                                **({"ui":r[5]} if r[5] else {}))
                           for r in reversed(rows)],
                    nextBefore=rows[-1][4] if more and rows else None)

    def turn_conversation(self,principal,turn_id):
        """Owning conversation of a turn inside the principal's scope (for run-id-only status lookups)."""
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT conversation_id FROM vault_private.vault_conversation_turns
              WHERE user_id=%s AND workspace_id=%s AND turn_id=%s""",(principal.user_id,principal.workspace_id,turn_id))
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("Conversation turn unavailable.")
        return str(row[0])

    def final_text(self,principal,conversation_id,turn_id):
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT payload->>'text' FROM vault_private.vault_conversation_events
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s AND kind='assistant_final'
              ORDER BY sequence DESC LIMIT 1""",(*self._scope(principal,conversation_id),turn_id))
            row = cursor.fetchone()
        return row[0] if row else None

    def history(self,principal,conversation_id,*,segment_id=None):
        self.load(principal,conversation_id)
        selected="""WITH selected_turns AS (
          SELECT * FROM vault_private.vault_conversation_turns
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s
            AND (%s::text IS NULL OR segment_id=%s)) """
        scope=(*self._scope(principal,conversation_id),segment_id,segment_id)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            # Reject oversized histories in SQL before loading large canonical
            # tool results or source payloads into the worker's memory.
            cursor.execute(selected+"""SELECT COALESCE(sum(bytes),0) FROM (
              SELECT octet_length(input_text) AS bytes FROM selected_turns
              UNION ALL SELECT octet_length(e.payload::text) FROM vault_private.vault_conversation_events e
                JOIN selected_turns t USING(user_id,workspace_id,conversation_id,turn_id)
                WHERE e.kind IN ('model_response','tool_status','assistant_final')
              UNION ALL SELECT octet_length(r.result_json::text) FROM vault_private.vault_voice_tool_invocations i
                JOIN selected_turns t USING(user_id,workspace_id,conversation_id,turn_id)
                JOIN vault_private.vault_voice_tool_results r ON r.invocation_id=i.invocation_id
                  AND r.user_id=i.user_id AND r.workspace_id=i.workspace_id
              ) AS history_bytes""",scope)
            if cursor.fetchone()[0]>262144:
                raise InputError("Selected conversation context exceeds its bounded history budget.")
            cursor.execute(selected+"""SELECT t.turn_id,t.input_text,t.state,e.payload->>'text'
              FROM selected_turns t LEFT JOIN vault_private.vault_conversation_events e
                ON e.turn_id=t.turn_id AND e.user_id=t.user_id AND e.workspace_id=t.workspace_id AND e.kind='assistant_final'
              ORDER BY t.ordinal LIMIT 257""",scope)
            rows = cursor.fetchall()
            if len(rows)>256:
                raise InputError("Selected conversation context exceeds its bounded history budget.")
            # Rehydrate proposal/result pairs from their canonical owners; never
            # replay calls or copy tool results into a second persistence ledger.
            cursor.execute(selected+"""SELECT e.turn_id,e.sequence,e.kind,e.payload FROM vault_private.vault_conversation_events e
              JOIN selected_turns t USING(user_id,workspace_id,conversation_id,turn_id)
              WHERE e.kind IN ('model_response','tool_status') ORDER BY e.turn_id,e.sequence LIMIT 4097""",scope)
            sources = cursor.fetchall()
            if len(sources)>4096:
                raise InputError("Selected conversation context exceeds its bounded history budget.")
            cursor.execute(selected+"""SELECT i.turn_id,i.tool_call_id,i.tool_name,i.state,r.result_json
              FROM vault_private.vault_voice_tool_invocations i
              JOIN selected_turns t USING(user_id,workspace_id,conversation_id,turn_id)
              LEFT JOIN vault_private.vault_voice_tool_results r
                ON r.invocation_id=i.invocation_id AND r.user_id=i.user_id AND r.workspace_id=i.workspace_id
              ORDER BY i.prepared_at,i.invocation_id LIMIT 4097""",scope)
            results = cursor.fetchall()
        if len(results)>4096:
            raise InputError("Selected conversation context exceeds its bounded history budget.")
        value = assemble_history(rows,sources,results)
        if len(json.dumps(value,ensure_ascii=False).encode())>262144:
            raise InputError("Selected conversation context exceeds its bounded history budget.")
        return value

    def recent(self,principal):
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_authority(cursor,principal)
            cursor.execute("""SELECT conversation_id,title,history_version,state FROM vault_private.vault_conversations
              WHERE user_id=%s AND workspace_id=%s AND create_key NOT LIKE 'voice-review:%%'
              ORDER BY updated_at DESC,conversation_id LIMIT 50""",(principal.user_id,principal.workspace_id))
            return tuple(dict(conversationId=r[0],title=r[1],historyVersion=r[2],state=r[3]) for r in cursor.fetchall())

    def recover_orphans(self):
        # Exclusive per-turn session lock proves there is no live owner. Never
        # replay providers or tools during startup/recovery/history reads.
        with self._connect() as connection:
            # A freshly committed submission may be between insertion and its
            # execution-lock acquisition. Only stale never-started submissions
            # qualify; running turns already acquired the lock before claim.
            rows = connection.execute("""SELECT turn_id FROM vault_private.vault_conversation_turns
              WHERE state='running' OR (state='submitted' AND updated_at<now()-interval '10 minutes')
              ORDER BY updated_at LIMIT 1024""").fetchall()
        for (turn_id,) in rows:
            try:
                lock = self.execution_lock(turn_id)
            except ConflictError:
                continue
            try:
                with self._connect() as connection:
                    changed = connection.execute("""UPDATE vault_private.vault_conversation_turns SET state='interrupted',
                      source_coverage='incomplete',cancel_requested=true,updated_at=now()
                      WHERE turn_id=%s AND state IN ('running','submitted') RETURNING turn_id""",(turn_id,)).fetchone()
                    if changed:
                        connection.execute("""UPDATE vault_private.vault_voice_tool_invocations SET
                          state=CASE WHEN effect_class='read' THEN 'failed' ELSE 'effect_unknown' END,
                          completed_at=CASE WHEN effect_class='read' THEN NULL ELSE now() END,
                          failure_code='conversation_owner_lost',updated_at=now()
                          WHERE turn_id=%s AND state='invoking'""",(turn_id,))
            finally:
                lock.close()
