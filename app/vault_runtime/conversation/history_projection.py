"""Canonical history shape extracted unchanged from ConversationRuntimeStore."""
from hashlib import sha256
import json


def history_fingerprint(history):
    return sha256(json.dumps(history,sort_keys=True,ensure_ascii=False,
        separators=(",", ":"),allow_nan=False).encode()).hexdigest()


def assemble_history(rows,sources,results):
    history = {r[0]:dict(turnId=r[0],input=r[1],state=r[2],answer=r[3],originalSources=[],toolResults=[]) for r in rows}
    for turn_id,sequence,kind,payload in sources:
        history[turn_id]['originalSources'].append(dict(sequence=sequence,kind=kind,payload=payload))
    for turn_id,call_id,name,state,result in results:
        history[turn_id]['toolResults'].append(dict(callId=call_id,name=name,state=state,result=result))
    return tuple(history.values())
