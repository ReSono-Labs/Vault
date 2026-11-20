"""Shared test helpers moved out of test modules (TST-01)."""

from threading import Event
from time import monotonic


def create(m):
    m.app._conversation_runtime.memories._embedder_factory = None
    response = m.post('/conversations', {'createKey':'chat-test'}, m.headers)
    assert response.status_code == 201, response.payload
    return response.payload['conversationId']


def submit(m, conversation, key='send-one', version=0):
    response = m.post(f'/conversations/{conversation}/turns',
        {'submissionKey':key,'input':'Find my contacts','expectedHistoryVersion':version},m.headers)
    assert response.status_code == 202, response.payload
    return response.payload['turnId']


def wait(m, conversation, turn):
    deadline = monotonic()+10
    while monotonic()<deadline:
        response = m.app.handle(method='GET',target=f'/conversations/{conversation}/turns/{turn}',headers=m.headers)
        assert response.status_code == 200, response.payload
        if response.payload['state'] not in {'submitted','running'}:
            return response.payload
        Event().wait(.02)
    raise AssertionError('Bounded test turn did not finish')
