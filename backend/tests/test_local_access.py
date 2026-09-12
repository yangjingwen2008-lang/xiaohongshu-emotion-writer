import pytest
from urllib.parse import urlsplit
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.local_access import LocalAccessMiddleware
from backend.app.main import app


@pytest.mark.parametrize("headers,status", [
    ({}, 200),
    ({"Origin": "http://testserver"}, 200),
    ({"Origin": "http://localhost:5173"}, 200),
    ({"Origin": "https://untrusted.example"}, 403),
    ({"Origin": "null"}, 403),
    ({"Origin": "http://testserver:8080"}, 403),
    ({"Origin": "http://testserver/path"}, 403),
    ({"Sec-Fetch-Site": "cross-site"}, 403),
    ({"Host": "untrusted.example"}, 400),
    ({"Host": "127.0.0.1:bad-port"}, 400),
    ({"Host": "evil@127.0.0.1"}, 400),
])
def test_main_app_rejects_untrusted_browser_requests(headers, status):
    assert TestClient(app).get("/api/health", headers=headers).status_code == status


def test_foreign_simple_post_never_reaches_a_paid_endpoint():
    calls = []
    isolated = FastAPI()
    isolated.add_middleware(LocalAccessMiddleware)

    @isolated.post("/api/paid")
    def paid():
        calls.append(True)
        return {"called": True}

    client = TestClient(isolated)
    result = client.post("/api/paid", headers={"Origin": "https://untrusted.example"}, content="")
    assert result.status_code == 403 and calls == []
    assert client.post("/api/paid", headers={"Origin": "http://testserver"}).status_code == 200
    assert calls == [True]


@pytest.mark.parametrize("address", ["http://127.0.0.1:8765", "http://localhost:8765", "http://192.168.1.20:8765", "http://[::1]:8765"])
def test_same_origin_local_and_lan_clients_remain_available(address):
    # The current Starlette/httpx compatibility transport cannot parse an IPv6 base_url.
    client = TestClient(app)
    assert client.get("/api/health", headers={"Host": urlsplit(address).netloc, "Origin": address}).status_code == 200


def test_development_preflight_preserves_cors_headers():
    result = TestClient(app).options("/api/setup/image", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert result.status_code == 200
    assert result.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
