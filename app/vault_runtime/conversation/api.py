"""Owned conversation route delegation; local host retains authentication and CSRF."""
from urllib.parse import parse_qs

from .contracts import InputError,identifier
from .streaming import event_stream


def handle_conversation_api(runtime,principal,*,method,path,query,headers,payload):
    from app.vault_runtime.local_api.app import LocalApiResponse
    no_store = (("Cache-Control","no-store"),)
    def response(status,value,**extra):
        return LocalApiResponse(status,value,no_store,**extra)
    def envelope(keys):
        if set(payload)!=set(keys):
            raise InputError("Unexpected conversation request fields.")
    parts = path.strip("/").split("/")
    if parts==['conversations','decisions','qualification'] and method=='GET':
        values=parse_qs(query,keep_blank_values=True)
        if set(values)-{'after','limit'} or any(len(v)!=1 for v in values.values()):
            raise InputError('Invalid historical qualification cursor.')
        reviewer=runtime.decision_review
        if reviewer is None:
            return response(503,{'error':{'code':'decision_review_disabled'}})
        return response(200,reviewer.source.qualification_report(principal,
            after=values.get('after',[None])[0],limit=int(values.get('limit',['10'])[0])))
    if parts==['conversations','decisions','rebuild'] and method=='POST':
        envelope(('expectedEpoch','requestKey'))
        reviewer=runtime.decision_review
        publisher=reviewer.on_completed if reviewer is not None else None
        if not callable(getattr(publisher,'rebuild',None)):
            return response(503,{'error':{'code':'decision_rebuild_unavailable'}})
        from app.vault_runtime.decision_learning.repository import ReviewConflictError
        from .contracts import ConflictError
        try:
            result=publisher.rebuild(principal=principal,source=reviewer.source,
                expected_epoch=payload['expectedEpoch'],request_key=payload['requestKey'])
        except ReviewConflictError as exc:
            raise ConflictError(str(exc)) from exc
        return response(200,result)
    if parts==["conversations"]:
        if method=="GET":
            return response(200,{"items":runtime.store.recent(principal)})
        if method=="POST":
            envelope(("createKey",))
            key = identifier(payload["createKey"])
            if key.startswith("voice-review:"):
                raise InputError("Reserved conversation identity prefix.")
            conversation = runtime.store.create(principal,key)
            return response(201,dict(conversationId=conversation.conversation_id,
                historyVersion=conversation.history_version,state=conversation.state))
    if len(parts)>=2 and parts[0]=="conversations":
        conversation_id = identifier(parts[1])
        if parts[2:]==["attachments"] and method=="POST":
            envelope(("uploadKey","name","dataBase64"))
            if runtime.attachments is None:
                raise InputError("Attachment storage is unavailable.")
            staged=runtime.attachments.stage(principal,conversation_id,
                upload_key=payload['uploadKey'],name=payload['name'],data=payload['dataBase64'])
            if runtime.preparation is not None:
                runtime.preparation.discard(principal,conversation_id)
            return response(201,staged)
        if len(parts)==4 and parts[2]=="attachments" and method=="DELETE":
            envelope(())
            if runtime.attachments is None:
                raise InputError("Attachment storage is unavailable.")
            runtime.attachments.remove(principal,conversation_id,identifier(parts[3]))
            if runtime.preparation is not None:
                runtime.preparation.discard(principal,conversation_id)
            return response(200,{"removed":True})
        if parts[2:]==["review-status"] and method=="GET":
            return response(200,{"segments":runtime.store.review_progress(principal,conversation_id),
                "idleSeconds":runtime.review_idle_seconds})
        if parts[2:]==["activity"] and method=="POST":
            envelope(())
            runtime.store.activity(principal,conversation_id)
            return response(200,{"state":"recorded"})
        if parts[2:]==["end-session"] and method=="POST":
            envelope(("expectedHistoryVersion",))
            return response(202,runtime.end_session(principal,conversation_id,payload["expectedHistoryVersion"]))
        if parts[2:]==["preparation"]:
            if runtime.preparation is None:
                return response(503,{"error":{"code":"preparation_unavailable"}})
            if method=="POST":
                return response(202,runtime.preparation.update(principal,conversation_id,payload))
            if method=="DELETE":
                envelope(("utteranceId",))
                return response(200,runtime.preparation.discard(principal,conversation_id,payload["utteranceId"]))
            if method=="GET":
                values = parse_qs(query,keep_blank_values=True)
                if set(values)!={"utteranceId","revision"} or any(len(v)!=1 for v in values.values()):
                    raise InputError("Invalid preparation cursor.")
                revision = int(values["revision"][0])
                if not 0<=revision<=2**31-1:
                    raise InputError("Invalid preparation revision.")
                return response(200,runtime.preparation.status(principal,conversation_id,
                    identifier(values["utteranceId"][0]),revision))
        if len(parts)==2 and method=="GET":
            values = parse_qs(query,keep_blank_values=True)
            if set(values)-{"before"} or any(len(v)!=1 for v in values.values()):
                raise InputError("Invalid history cursor.")
            try:
                before = int(values["before"][0]) if "before" in values else None
            except ValueError:
                raise InputError("Invalid history cursor.") from None
            conversation = runtime.store.load(principal,conversation_id)
            page = runtime.store.display_history(principal,conversation_id,before=before)
            if runtime.attachments is not None:
                attached=runtime.attachments.metadata(principal,conversation_id,[t['turnId'] for t in page['turns']])
                for turn in page['turns']:
                    turn['attachments']=attached.get(turn['turnId'],[])
            return response(200,dict(conversationId=conversation_id,historyVersion=conversation.history_version,
                title=conversation.title,state=conversation.state,**page))
        if parts[2:]==["turns"] and method=="POST":
            if set(payload) not in ({"submissionKey","input","expectedHistoryVersion"},
                                    {"submissionKey","input","expectedHistoryVersion","attachmentIds"}):
                raise InputError("Unexpected conversation request fields.")
            return response(202,runtime.submit(principal,conversation_id,submission_key=payload["submissionKey"],
                input_text=payload["input"],expected_history_version=payload["expectedHistoryVersion"],
                attachment_ids=payload.get('attachmentIds')))
        if len(parts)>=4 and parts[2]=="turns":
            turn_id = identifier(parts[3])
            if len(parts)==4 and method=="GET":
                return response(200,runtime.store.status(principal,conversation_id,turn_id))
            if len(parts)==5 and parts[4]=="stop" and method=="POST":
                envelope(())
                return response(200,runtime.stop(principal,conversation_id,turn_id))
            if len(parts)==5 and parts[4]=="events" and method=="GET":
                values = parse_qs(query,keep_blank_values=True)
                if set(values)-{"after"} or len(values.get("after",["0"]))!=1:
                    raise InputError("Invalid conversation event cursor.")
                try:
                    event_id = next((v for k,v in headers.items() if k.lower()=="last-event-id"),"0")
                    cursors = (int(values.get("after",["0"])[0]),int(event_id))
                    if any(not 0<=v<=2**63-1 for v in cursors):
                        raise ValueError("Invalid cursor")
                    after = max(cursors)
                except (ValueError,TypeError):
                    raise InputError("Invalid conversation event cursor.") from None
                if not 0<=after<=2**63-1:
                    raise InputError("Invalid conversation event cursor.")
                runtime.store.status(principal,conversation_id,turn_id)  # Before committing HTTP headers.
                return response(200,{},content_type="text/event-stream; charset=utf-8",
                    stream=event_stream(runtime.store,principal,conversation_id,turn_id,after=after,slots=runtime.view_slots))
    return response(404,{"error":{"code":"not_found"}})
