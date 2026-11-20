"""Readable original SDK observations; encrypted/hidden reasoning is excluded."""
from app.vault_runtime.memory.evidence import redact_evidence
from app.vault_runtime.tools.strict_json import parse_json_object_bytes
from app.vault_runtime.voice.tools import canonical_arguments_sha256
from .contracts import InputError


def capture_model_response(response):
    output,calls = [],{}
    response_id = getattr(response,"response_id",None)
    if response_id is not None and (not isinstance(response_id,str) or len(response_id)>256):
        raise InputError("Invalid original response identity.")
    items = tuple(getattr(response,"output",()))
    if len(items)>128:
        raise InputError("Original model response exceeds capture bound.")
    for item in items:
        kind = getattr(item,"type",None)
        identity = getattr(item,"id",None)
        if identity is not None and (not isinstance(identity,str) or len(identity)>256):
            raise InputError("Invalid original item identity.")
        if kind=="reasoning":
            summaries = []
            for summary in getattr(item,"summary",()):
                text = getattr(summary,"text",None)
                if not isinstance(text,str):
                    raise InputError("Malformed original readable summary.")
                summaries.append(text)  # Complete or rejected by store bound; never clipped.
            output.append(dict(type=kind,id=identity,summary=summaries))
        elif kind=="function_call":
            name,call_id,raw = getattr(item,"name",None),getattr(item,"call_id",None),getattr(item,"arguments",None)
            if not all(isinstance(v,str) and v and len(v)<=256 for v in (name,call_id)) or not isinstance(raw,str):
                raise InputError("Original tool call has no valid identity.")
            args = parse_json_object_bytes(raw.encode())
            fingerprint = canonical_arguments_sha256(args)
            value = (name,fingerprint)
            if call_id in calls:
                raise InputError("Ambiguous original tool call identity.")
            calls[call_id] = value
            output.append(dict(type=kind,id=identity,call_id=call_id,name=name,
                arguments=redact_evidence(args),arguments_sha256=fingerprint))
        elif kind=="message":
            content = []
            for part in getattr(item,"content",()):
                part_type = getattr(part,"type",None)
                if part_type=="output_text":
                    content.append(dict(type=part_type,text=part.text))
                elif part_type=="refusal":
                    content.append(dict(type=part_type,refusal=part.refusal))
                else:
                    raise InputError("Unsupported original message content; capture incomplete.")
            output.append(dict(type=kind,id=identity,role=getattr(item,"role","assistant"),content=content))
        else:
            raise InputError("Unsupported original model output; capture incomplete.")
    return dict(origin="server_sdk",response_id=response_id,output=output,
        reasoningAvailability="available" if any(i["type"]=="reasoning" and i["summary"] for i in output) else "not_returned"),calls
