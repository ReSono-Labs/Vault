import json

import pytest

from app.vault_runtime.voice.provider_evidence import project_provider_evidence


def call():
    return dict(type="response.function_call_arguments.done",response_id="response-1",item_id="item-1",
        call_id="call-1",name="contacts_search",arguments=json.dumps({"query":"Sarah","api_key":"secret"}),
        audio="NEVER STORE THIS",encrypted_content="OPAQUE")


def test_projects_only_bounded_original_browser_fields_and_redacts_secrets():
    value = project_provider_evidence("response.function_call_arguments.done",call())
    assert value["origin"]=="browser_provider" and value["response_id"]=="response-1"
    assert value["proposals"][0]["call_id"]=="call-1"
    assert "secret" not in json.dumps(value) and "NEVER STORE" not in json.dumps(value)
    assert "OPAQUE" not in json.dumps(value) and "reasoning" not in value


def test_completion_and_call_share_original_identity():
    event = call()
    item = dict(type="function_call",id=event["item_id"],call_id=event["call_id"],
        name=event["name"],arguments=event["arguments"])
    done = dict(type="response.done",response=dict(id="response-1",status="completed",output=[item]))
    assert project_provider_evidence("response.done",done)["proposals"] == project_provider_evidence(event["type"],event)["proposals"]
    assert project_provider_evidence("legacy.event",{})=={}


@pytest.mark.parametrize("changes",[{"type":"wrong"},{"arguments":"[]"},{"arguments":"{"},
    {"arguments":"x"*16385},{"arguments":'{"value":NaN}'},{"call_id":""},{"response_id":"x"*256}])
def test_malformed_or_overflow_capture_rejected(changes):
    with pytest.raises(ValueError):
        project_provider_evidence("response.function_call_arguments.done",dict(call(),**changes))


def test_response_output_count_bound():
    with pytest.raises(ValueError):
        project_provider_evidence("response.done",dict(type="response.done",
            response=dict(id="r",status="completed",output=[{}]*65)))
