"""Mounted independent post-session capability using canonical Voice sources."""
from dataclasses import dataclass,field

from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.decision_routing.diagnostics import LiveDiagnostics
from .repository import DecisionReviewRepository,ReviewConflictError
from .reviewer import DecisionReviewer,ProceduralReview,ReviewOutput,DecisionReviewOverflow
from .repository import source_fingerprint
from .voice_source import VoiceReviewSource
from .analysis_windows import review_windows,CONTRACT as WINDOW_CONTRACT


@dataclass(frozen=True,slots=True)
class BoundReviewAccess:
    user_id: str
    workspace_id: str
    provider: str
    credential: object = field(repr=False)
    model: str

    def selected_provider(self,*,user_id,workspace_id):
        self._scope(user_id,workspace_id)
        return self.provider

    def background_access(self,*,user_id,workspace_id,provider_key):
        self._scope(user_id,workspace_id)
        if provider_key!=self.provider:
            raise ValueError("Review provider binding changed.")
        return self.credential,self.model

    def _scope(self,user,workspace):
        if (user,workspace)!=(self.user_id,self.workspace_id):
            raise ValueError("Review credential scope mismatch.")


class VoiceDecisionReview:
    def __init__(self,*,database_url,catalog,credentials,executor=None,diagnostics=None,source=None,
                 repository_type=DecisionReviewRepository):
        self.source = source if source is not None else VoiceReviewSource(database_url=database_url,catalog=catalog)
        self.repository = repository_type(database_url=database_url,source_current=self.source.current)
        self.credentials,self.executor = credentials,executor
        self.diagnostics = diagnostics or LiveDiagnostics()
        self.on_completed = None
        self.reconciler = None

    def _publication(self,principal,snapshot,review_id,review):
        if self.on_completed is None:
            return {}
        try:
            return {"learning":self.on_completed(principal=principal,snapshot=snapshot,review_id=review_id,review=review)}
        except Exception:
            return {"learning":{"state":"publication_pending"}}

    def ensure_schema(self):
        self.source.ensure_schema()
        self.repository.ensure_schema()

    def _event(self,event,principal,voice_id,*,review_id=None,count=0):
        try:
            self.diagnostics.review_event(event,principal,voice_id,review_id=review_id,assessment_count=count)
        except Exception:
            # Operational diagnostics must not interrupt capture or learning.
            pass

    def finalize(self,*,principal,voice_session_id):
        return self.finalize_source(principal=principal,session_id=voice_session_id)

    def finalize_source(self,*,principal,session_id,snapshot=None):
        """Shared execution; each channel supplies its canonical source adapter."""
        voice_session_id = session_id
        claim = None
        self._event("review_started",principal,voice_session_id)
        try:
            snapshot = self.source.load(principal,voice_session_id) if snapshot is None else snapshot
            if snapshot is None:
                self._event("review_skipped_empty",principal,voice_session_id)
                return {"state":"skipped_empty"}
            claim = self.repository.claim(principal,snapshot,lease_seconds=180)
            if claim is None:
                stored = self.repository.for_source(principal,snapshot)
                if stored is None or stored[1]!="completed":
                    self._event("review_pending",principal,voice_session_id)
                    return {"state":"pending"}
                self._event("review_completed",principal,voice_session_id,review_id=stored[0],count=len(stored[4].assessments))
                return {"state":"completed","reviewId":stored[0],"coverage":snapshot.coverage,
                        "assessmentCount":len(stored[4].assessments),"alreadyCompleted":True,
                        **self._publication(principal,snapshot,stored[0],
                            ProceduralReview(source_fingerprint(snapshot),stored[3],stored[4]))}
            with self.repository.keepalive(principal,claim,snapshot):
                # Resolve once AFTER source qualification/claim. The model runner and
                # durable result receive precisely the same bound provider/model.
                provider = self.credentials.selected_provider(user_id=principal.user_id,workspace_id=principal.workspace_id)
                credential,model = self.credentials.background_access(user_id=principal.user_id,
                    workspace_id=principal.workspace_id,provider_key=provider)
                access = BoundReviewAccess(principal.user_id,principal.workspace_id,provider,credential,model)
                options = {} if self.executor is None else {"executor":self.executor}
                model_runner = OpenAIMemoryReviewer(credentials=access,
                    user_id=principal.user_id,workspace_id=principal.workspace_id,**options)
                if callable(getattr(self.source,'review_parts',None)):
                    parts=self.source.review_parts(principal,snapshot)
                    if parts:
                        model_runner.with_input_parts(parts)
                saved = self.repository.stage(principal,claim,snapshot,name="analysis")
                if saved is not None:
                    if (saved["provider"],saved["model"])!=(provider,model):
                        raise ReviewConflictError("Analysis model binding changed.")
                    review = ProceduralReview(source_fingerprint(snapshot),model,ReviewOutput.model_validate(saved["output"]))
                else:
                    reviewer=DecisionReviewer(model_runner=model_runner)
                    plan=self.repository.stage(principal,claim,snapshot,name='analysis_plan')
                    plan_binding=dict(contract=WINDOW_CONTRACT,provider=provider,model=model,windowed=True)
                    if plan is not None and plan!=plan_binding:
                        raise ReviewConflictError('Analysis window plan binding changed.')
                    windowed=plan is not None or len(snapshot.observations)>16 or len(snapshot.model_dump_json())>100000
                    if not windowed:
                        try:
                            review=reviewer.review(snapshot)
                            windowed=len(review.output.proposals)==32
                        except DecisionReviewOverflow:
                            windowed=True
                    if windowed:
                        self.repository.stage(principal,claim,snapshot,name='analysis_plan',value=plan_binding)
                        review=review_windows(snapshot,reviewer=reviewer,model=model,provider=provider,
                            stage=lambda name,value=None:self.repository.stage(principal,claim,snapshot,name=name,value=value))
                    self.repository.stage(principal,claim,snapshot,name="analysis",value=dict(provider=provider,
                        model=model,output=review.output.model_dump(mode="json")))
                if self.reconciler:
                    review = self.reconciler.reconcile(principal=principal,claim=claim,snapshot=snapshot,
                        review=review,model_runner=model_runner,provider=provider)
            self.repository.complete(principal,claim,snapshot,review,provider=provider)
            self._event("review_completed",principal,voice_session_id,review_id=claim.review_id,count=len(review.output.assessments))
            return {"state":"completed","reviewId":claim.review_id,"coverage":snapshot.coverage,
                    "assessmentCount":len(review.output.assessments),"alreadyCompleted":False,
                    **self._publication(principal,snapshot,claim.review_id,review)}
        except Exception as error:
            import logging
            from .reviewer import DecisionReviewError
            # Validation messages are fixed code-authored strings (never session content), so they are
            # logged; provider exceptions log only their type chain, which may otherwise carry payloads.
            chain, cause = [], error.__cause__
            while cause is not None and len(chain) < 4:
                chain.append(type(cause).__name__)
                cause = cause.__cause__ or cause.__context__
            reason = str(error)[:200] if isinstance(error,(DecisionReviewError,ReviewConflictError)) else "-"
            logging.getLogger(__name__).warning("decision_review_failure type=%s reason=%s cause=%s",
                type(error).__name__, reason, ">".join(chain) or "none")
            if claim is not None:
                try:
                    self.repository.retryable(principal,claim)
                except Exception:
                    pass  # A reclaimed/revoked lease cannot be changed by this worker.
            self._event("review_failed",principal,voice_session_id,review_id=claim.review_id if claim else None)
            return {"state":"failed","errorCode":"decision_review_failed"}

    def status(self,*,principal,voice_session_id):
        with self.repository._connect() as connection, connection.cursor() as cursor:
            ConversationRepository._require_authority(cursor,principal)
            scope = (principal.user_id,principal.workspace_id,voice_session_id)
            cursor.execute("""SELECT transcript_capture_state FROM vault_private.vault_voice_sessions
              WHERE user_id=%s AND workspace_id=%s AND voice_session_id=%s FOR SHARE""",scope)
            session = cursor.fetchone()
            if session is None:
                raise ReviewConflictError("Owned Voice session required.")
            cursor.execute("""SELECT review_id,state,source_coverage_json,assessments_json,proposals_json,
                provider,model,error_code FROM vault_private.vault_decision_reviews
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s
              ORDER BY created_at DESC,review_id DESC LIMIT 1""",scope)
            row = cursor.fetchone()
            if row is None:
                return {"state":"blocked_incomplete_capture" if session[0]=="incomplete" else "not_reviewed",
                        "captureState":session[0],"assessments":[],"proposals":[]}
            return dict(reviewId=row[0],state=row[1],coverage=row[2].get("coverage","unknown"),
                assessments=row[3],proposals=row[4],provider=row[5],model=row[6],errorCode=row[7],captureState=session[0])
