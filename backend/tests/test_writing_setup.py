import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.database import get_db
from backend.app.models import AppSetting
from backend.app.providers import WRITING_PRESETS
from backend.app.routes.system import router
from backend.app.security import secret_store


def test_writing_setup_switches_only_to_the_selected_service(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    AppSetting.__table__.create(engine)
    keys = {"deepseek": "existing-deepseek-key"}
    monkeypatch.setattr(secret_store, "get", keys.get)
    monkeypatch.setattr(secret_store, "set", keys.__setitem__)
    calls = []

    def completion(request):
        calls.append((str(request.url), request.headers["Authorization"], json.loads(request.content)))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(completion), **kwargs))

    def session():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = session
    with TestClient(app) as client:
        assert client.get("/setup/status").json()["writing_provider"] == "deepseek"
        assert client.post("/setup/writing", json={"provider": "openai"}).status_code == 400
        for provider in ("openai", "qwen", "deepseek"):
            new_key = f"fixture-{provider}-key"
            assert client.post("/setup/writing", json={"provider": provider, "api_key": new_key}).status_code == 200
            status = client.get("/setup/status")
            assert status.json()["writing_provider"] == provider
            assert status.json()["writing_configured"] is True
            assert new_key not in status.text
            preset = WRITING_PRESETS[provider]
            assert client.post("/setup/test/writing").json() == {"ok": True, "model": preset.model}
            url, authorization, body = calls[-1]
            assert url == f"{preset.base_url}/chat/completions"
            assert authorization == f"Bearer {new_key}"
            assert body["model"] == preset.model
            assert body["response_format"] == {"type": "json_object"}
            assert ("thinking" in body) == (provider == "deepseek")
            assert ("enable_thinking" in body) == (provider == "qwen")
        assert client.post("/setup/writing", json={"provider": "openai"}).status_code == 200
        assert client.post("/setup/test/writing").json()["ok"] is True
        assert calls[-1][1] == "Bearer fixture-openai-key"
