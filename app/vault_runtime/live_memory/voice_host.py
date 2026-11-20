"""Actual Voice source adapter into the one shared preparation host; no copied history."""
from types import SimpleNamespace
from hashlib import sha256

from app.vault_runtime.conversation.contracts import InputError
from app.vault_runtime.voice.repository import VoiceSessionRepository

PREFIX="voice-live:"


def voice_id(identity):
    return identity[len(PREFIX):] if identity.startswith(PREFIX) else None


def voice_history_cursor(cursor,scope,session_id,final_id=None):
    VoiceSessionRepository._session_cursor(cursor,user_id=scope.user_id,workspace_id=scope.workspace_id,
        local_session_id=scope.local_session_id,voice_session_id=session_id,require_open=True)
    cutoff=2**63-1
    if final_id is not None:
        cursor.execute("""SELECT entry_index FROM vault_private.vault_transcript_entries
          WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s AND entry_id=%s
            AND role='user' AND event_type IN ('conversation.item.input_audio_transcription.completed',
            'conversation.item.input_audio_transcript.completed')""",
            (scope.user_id,scope.workspace_id,session_id,final_id))
        row=cursor.fetchone()
        if row is None:
            raise InputError("Authoritative Voice final is unavailable.")
        cutoff=row[0]
    cursor.execute("""SELECT entry_index FROM vault_private.vault_transcript_entries
      WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s AND entry_index<%s
      ORDER BY entry_index DESC LIMIT 1""",(scope.user_id,scope.workspace_id,session_id,cutoff))
    row=cursor.fetchone()
    return (row[0]+1 if row else 0),cutoff


class PreparationSources:
    """Channel source routing only. Scheduling, search, decisions and grants stay shared."""
    def __init__(self,chat,sessions):
        self.chat,self.sessions=chat,sessions

    def load(self,principal,identity):
        session_id=voice_id(identity)
        if session_id is None:
            return self.chat.load(principal,identity)
        self.sessions.session(user_id=principal.user_id,workspace_id=principal.workspace_id,
            local_session_id=principal.session_id,voice_session_id=session_id,require_open=True)
        return SimpleNamespace(state="open",segments=(SimpleNamespace(state="open",segment_id=identity),))

    def context_identity(self,cursor,scope,identity):
        session_id=voice_id(identity.conversation_id)
        if session_id is None:
            return self.chat.context_identity_in_transaction(cursor,scope,identity)
        if identity.segment_id!=identity.conversation_id:
            raise InputError("Voice source identity mismatch.")
        history,_=voice_history_cursor(cursor,scope,session_id,identity.turn_id)  # also requires an open session
        if identity.turn_id is None:
            # Live Voice preparation searches only the utterance in progress. Saving that utterance's
            # final transcript and the agent's reply changes the transcript count exactly when
            # selection runs (at the pause), which made every tool choice stale. Memory versions,
            # preference, session and grants stay fenced; transcript history is not an input.
            return 0
        if identity.turn_id is not None:
            cursor.execute("""SELECT text_content FROM vault_private.vault_transcript_entries
              WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s AND entry_id=%s""",
              (scope.user_id,scope.workspace_id,session_id,identity.turn_id))
            if sha256(cursor.fetchone()[0].encode()).hexdigest()!=identity.input_fingerprint:
                raise InputError("Voice final fingerprint changed.")
        return history

    def history(self,principal,identity):
        session_id=voice_id(identity)
        if session_id is None:
            return self.chat.history(principal,identity)
        self.load(principal,identity)
        from app.vault_runtime.decision_routing.contracts import ScopedPrincipalRef
        scope=ScopedPrincipalRef(principal.user_id,principal.workspace_id,principal.session_id)
        with self.chat._connect() as connection,connection.cursor() as cursor:
            self.chat._require_authority(cursor,principal)
            voice_history_cursor(cursor,scope,session_id)
            cursor.execute("""SELECT entry_id,role,text_content FROM vault_private.vault_transcript_entries
              WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s
              ORDER BY entry_index DESC LIMIT 4""",(principal.user_id,principal.workspace_id,session_id))
            return [dict(sourceId=i,role=r,text=t) for i,r,t in reversed(cursor.fetchall())]
