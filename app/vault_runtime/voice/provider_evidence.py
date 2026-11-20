"""Bounded browser-origin provider links, never hidden reasoning or trusted causality."""
import json

from app.vault_runtime.memory.evidence import redact_evidence


def project_provider_evidence(event_type: str, payload: object) -> dict:
    if event_type not in {"response.done","response.function_call_arguments.done"}:
        return {}
    if not isinstance(payload,dict) or payload.get("type")!=event_type:
        raise ValueError("Provider evidence type mismatch.")

    def identity(value):
        if not isinstance(value,str) or not value.strip() or len(value)>255 or "\x00" in value:
            raise ValueError("Provider evidence identity must be bounded text.")
        return value

    def proposal(item):
        arguments = item.get("arguments")
        if not isinstance(arguments,str) or len(arguments.encode())>16384:
            raise ValueError("Provider proposal arguments must be bounded JSON text.")
        try:
            def reject_constant(_):
                raise ValueError("Non-finite JSON value.")
            parsed = json.loads(arguments,parse_constant=reject_constant)
        except (ValueError,RecursionError) as exc:
            raise ValueError("Provider proposal arguments must be JSON.") from exc
        if not isinstance(parsed,dict):
            raise ValueError("Provider proposal arguments must be an object.")
        try:
            redacted = redact_evidence(parsed)
        except RecursionError as exc:
            raise ValueError("Provider proposal nesting exceeds capture bound.") from exc
        return dict(item_id=identity(item.get("id",item.get("item_id"))),
            call_id=identity(item.get("call_id")),name=identity(item.get("name")),arguments=redacted)

    if event_type=="response.function_call_arguments.done":
        result = dict(origin="browser_provider",response_id=identity(payload.get("response_id")),
            proposals=[proposal(payload)])
    else:
        response = payload.get("response")
        if not isinstance(response,dict) or not isinstance(response.get("output"),list):
            raise ValueError("Provider completion requires response output.")
        if len(response["output"])>64:
            raise ValueError("Provider completion output exceeds capture bound.")
        result = dict(origin="browser_provider",response_id=identity(response.get("id")),
            status=identity(response.get("status")),proposals=[])
        for item in response["output"]:
            if not isinstance(item,dict):
                raise ValueError("Provider output item must be an object.")
            if item.get("type")=="function_call":
                result["proposals"].append(proposal(item))
    if len(json.dumps(result,ensure_ascii=False).encode())>65536:
        raise ValueError("Provider evidence exceeds capture bound.")
    return result
