from app.brokers.etoro.http_response_payload import response_payload


class FakeResponse:
    def __init__(self, *, content: bytes, payload: dict):
        self.content = content
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_response_payload_returns_empty_dict_when_response_has_no_content():
    response = FakeResponse(content=b'', payload={'ignored': True})

    assert response_payload(response) == {}


def test_response_payload_returns_json_when_response_has_content():
    response = FakeResponse(content=b'{}', payload={'ok': True})

    assert response_payload(response) == {'ok': True}
