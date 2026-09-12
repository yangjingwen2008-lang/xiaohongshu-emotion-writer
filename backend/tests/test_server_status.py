import json
from backend.app import server_status
from backend.app.config import instance_id


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps({"status": "ok", "instance_id": instance_id()}).encode()


def test_server_ready_requires_healthy_local_response(monkeypatch):
    monkeypatch.setattr(server_status, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    assert server_status.is_server_ready() is True


def test_wait_until_ready_retries_until_success(monkeypatch):
    results = iter((False, False, True))
    monkeypatch.setattr(server_status, "is_server_ready", lambda: next(results))
    monkeypatch.setattr(server_status.time, "sleep", lambda _seconds: None)
    assert server_status.wait_until_ready(wait_seconds=2, interval=0.01) is True


def test_another_checkouts_healthy_service_is_not_reused(monkeypatch):
    response = FakeResponse()
    response.read = lambda: b'{"status":"ok","instance_id":"other-checkout"}'
    monkeypatch.setattr(server_status, 'urlopen', lambda *_args, **_kwargs: response)
    assert server_status.is_server_ready() is False
