from types import SimpleNamespace as NS

import pytest

from app.vault_runtime.conversation.contracts import InputError
from app.vault_runtime.conversation.model_capture import capture_model_response


def test_original_readable_summary_not_clipped_or_reconstructed():
    payload,calls = capture_model_response(NS(response_id='r',output=[
        NS(type='reasoning',id='i',summary=[NS(text='x'*20000)],encrypted_content='secret')]))
    assert payload['output'][0]['summary']==['x'*20000] and calls=={}
    assert 'secret' not in str(payload)
    payload,_ = capture_model_response(NS(output=[]))
    assert payload['reasoningAvailability']=='not_returned'


@pytest.mark.parametrize('raw',['{"a":1,"a":2}','{"a":NaN}','[]'])
def test_malformed_original_arguments_rejected(raw):
    with pytest.raises(ValueError):
        capture_model_response(NS(output=[NS(type='function_call',id='i',name='tool',call_id='c',arguments=raw)]))


def test_ambiguous_or_unsupported_original_source_rejected():
    call = NS(type='function_call',name='tool',call_id='c',arguments='{}')
    with pytest.raises(InputError):
        capture_model_response(NS(output=[call,call]))
    with pytest.raises(InputError):
        capture_model_response(NS(output=[NS(type='unhandled-provider-source')]))


def test_attachment_format_limits_and_actual_text_extraction():
    from app.vault_runtime.conversation.attachments import inspect_input
    from app.vault_runtime.conversation.contracts import InputError
    from PIL import Image
    from io import BytesIO
    import pytest
    assert inspect_input('note.txt',b'Actual text')==('text/plain','Actual text','complete_text')
    image=BytesIO()
    Image.new('RGB',(2,2)).save(image,format='PNG')
    assert inspect_input('picture.png',image.getvalue())==('image/png',None,'image')
    for name,data in [('bad.png',b'fake'),('script.html',b'<script>'),('note.txt',b'\xff'),('note.txt',b'x'*60001)]:
        with pytest.raises(InputError):
            inspect_input(name,data)
