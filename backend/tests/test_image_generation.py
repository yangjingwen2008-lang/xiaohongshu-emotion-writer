import asyncio
import base64
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
from threading import Event

import httpx
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException

from backend.app import image_provider as provider
from backend.app.config import settings
from backend.app.database import Base, SessionLocal, engine
from backend.app.image_generation import generation_busy
from backend.app.main import app
from backend.app.models import AppSetting, Artifact, Content, ContentVersion
from backend.app.routes import covers, system
from backend.app.security import SecretStoreError, secret_store


def png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (900, 1200), "#bfc6b7").save(output, "PNG")
    return output.getvalue()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "export_dir", tmp_path / "exports")
    monkeypatch.setattr(settings, "image_generation_enabled", False)
    monkeypatch.setattr(settings, "image_base_url", "")
    monkeypatch.setattr(settings, "image_model", "")
    keys = {"image": "example-image-key"}
    monkeypatch.setattr(secret_store, "get", lambda name: keys.get(name))
    monkeypatch.setattr(secret_store, "set", lambda name, value: keys.update({name: value}))
    return keys


@pytest.fixture
def content_id():
    with SessionLocal() as db:
        item = Content(theme="雨后窗边", emotion="平静", title="雨后窗边")
        db.add(item)
        db.flush()
        db.add(Artifact(content_id=item.id, artifact_type="EssayDraft", step_id="draft_generation",
                        payload={"cover_copy": "雨后窗边"}, content_hash="draft", source_artifact_ids=[]))
        db.add(ContentVersion(content_id=item.id, version=1, kind="human_edit", title="雨后窗边",
                              body_html="<p>虚构验收正文</p>", body_text="虚构验收正文", content_hash="test"))
        db.commit()
        return item.id


def use_transport(monkeypatch, handler):
    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    async def public(_host, _port):
        return "8.8.8.8"
    monkeypatch.setattr(provider, "public_address", public)


def adapter():
    return provider.OpenAICompatibleImageProvider(provider.ImageConfiguration(
        enabled=True, base_url="https://image.example/v1", model="example-model"), "private-test-key")


def test_settings_save_retains_key_and_never_calls_provider(isolated, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: pytest.fail("saving settings must not call a provider"))
    client = TestClient(app)
    config = {"enabled": True, "base_url": "https://image.example/v1/", "model": "example-model", "timeout_seconds": 180, "api_key": "private-test-key"}
    saved = client.post("/api/setup/image", json=config)
    assert saved.status_code == 200 and saved.json()["available"]
    assert "private-test-key" not in saved.text and "api_key" not in saved.json()
    config["api_key"] = None
    assert client.post("/api/setup/image", json=config).status_code == 200
    assert isolated["image"] == "private-test-key"
    with SessionLocal() as db:
        assert "private-test-key" not in json.dumps(db.get(AppSetting, "image_generation").value)
    config["base_url"] = "https://different.example/v1"
    assert client.post("/api/setup/image", json=config).status_code == 400
    config["api_key"] = "new-private-key"
    assert client.post("/api/setup/image", json=config).status_code == 200
    manifest = next(row["manifest"] for row in client.get("/api/plugins/manifests").json()
                    if row["manifest"]["provider_type"] == "ImageGenerationProvider")
    assert manifest["enabled"] and manifest["allowed_domains"] == ["different.example"]


@pytest.mark.parametrize("source", ["database", "environment"])
def test_invalid_configuration_keeps_cover_page_usable_and_can_be_repaired(source, content_id, monkeypatch):
    if source == "database":
        with SessionLocal() as db:
            db.add(AppSetting(key="image_generation", value={"enabled": True, "base_url": "broken-private-input"}))
            db.commit()
    else:
        monkeypatch.setattr(settings, "image_generation_enabled", True)
        monkeypatch.setattr(settings, "image_base_url", "broken-private-input")
    client = TestClient(app)
    status = client.get("/api/setup/image")
    assert status.status_code == 200 and not status.json()["available"]
    assert status.json()["configuration_error"] and "broken-private-input" not in status.text
    assert client.get(f"/api/contents/{content_id}/cover").status_code == 200
    with SessionLocal() as db, pytest.raises(provider.ImageProviderError, match="配置无效"):
        provider.build_image_provider(db)
    config = {"enabled": True, "base_url": "https://repaired.example/v1", "model": "model"}
    assert client.post("/api/setup/image", json=config).status_code == 400
    assert client.post("/api/setup/image", json={**config, "api_key": "new-key"}).json()["available"]


@pytest.mark.parametrize("legacy", [True, False])
def test_failed_config_commit_never_sends_new_key_to_old_service(legacy, isolated, monkeypatch):
    old = provider.ImageConfiguration(enabled=True, base_url="https://old.example/v1", model="old")
    with SessionLocal() as db:
        db.add(AppSetting(key="image_generation", value=old.model_dump()))
        if not legacy:
            db.add(AppSetting(key="image_credential_binding", value=provider.image_key_binding(old.base_url, isolated["image"])))
        db.commit()
        real_commit = db.commit
        commits = 0

        def fail_final_commit():
            nonlocal commits
            commits += 1
            if commits == (2 if legacy else 1):
                raise OperationalError("commit", {}, Exception("disk full"))
            real_commit()

        with monkeypatch.context() as patch:
            patch.setattr(db, "commit", fail_final_commit)
            with pytest.raises(HTTPException) as error:
                system.save_image_setup(provider.ImageSetupRequest(enabled=True, base_url="https://new.example/v1", model="new", api_key="new-key"), db)
            assert error.value.status_code == 503
        assert isolated["image"] == "new-key"
        assert provider.image_configuration(db).base_url == old.base_url
        assert not provider.image_status(db)["available"]
        with pytest.raises(provider.ImageProviderError, match="不一致"):
            provider.build_image_provider(db)
        repaired = system.save_image_setup(provider.ImageSetupRequest(enabled=True, base_url="https://new.example/v1", model="new", api_key="new-key"), db)
        assert repaired["available"]
        assert provider.build_image_provider(db).config.base_url == "https://new.example/v1"


def test_credential_store_failure_preserves_existing_image_configuration(isolated, monkeypatch):
    client = TestClient(app)
    config = {"enabled": True, "base_url": "https://image.example/v1", "model": "model", "api_key": "old-key"}
    assert client.post("/api/setup/image", json=config).status_code == 200

    def fail(*args):
        raise SecretStoreError("凭据保存失败")

    monkeypatch.setattr(secret_store, "set", fail)
    assert client.post("/api/setup/image", json={**config, "base_url": "https://new.example/v1", "api_key": "new-key"}).status_code == 503
    status = client.get("/api/setup/image").json()
    assert status["available"] and status["base_url"] == config["base_url"]
    assert isolated["image"] == "old-key"


@pytest.mark.parametrize("base", ["http://image.example/v1", "https://localhost/v1", "https://127.0.0.1/v1", "https://image.example/v1?key=private", "https://image.example/v1/images/generations"])
def test_config_validation_does_not_echo_secrets(base):
    response = TestClient(app).post("/api/setup/image", json={"enabled": True, "base_url": base, "model": "sample", "api_key": "private-test-key"})
    assert response.status_code == 422
    assert "private-test-key" not in response.text and "input" not in response.json()["detail"][0]


async def test_base64_request_is_minimal_and_pins_validated_address(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})
    use_transport(monkeypatch, handler)
    result = await adapter().generate(prompt="雨后窗边")
    assert result.data == png()
    assert json.loads(requests[0].content) == {"model": "example-model", "prompt": "雨后窗边", "n": 1}
    assert requests[0].url.host == "8.8.8.8"
    assert requests[0].headers["host"] == "image.example"
    assert requests[0].extensions["sni_hostname"] == "image.example"
    await adapter().generate(prompt="雨后窗边", size="1024x1536")
    assert json.loads(requests[1].content)["size"] == "1024x1536"


async def test_url_download_redirect_never_forwards_authorization(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": "https://cdn.example/picture?signature=private"}]}, headers={"set-cookie": "session=private; Path=/; Secure"})
        if len(requests) == 2:
            return httpx.Response(302, headers={"location": "https://second.example/picture.png"})
        return httpx.Response(200, content=png())
    use_transport(monkeypatch, handler)
    result = await adapter().generate(prompt="雨后窗边")
    assert result.data == png() and len(requests) == 3
    assert requests[0].headers["authorization"] == "Bearer private-test-key"
    assert all("authorization" not in request.headers for request in requests[1:])
    assert all("cookie" not in request.headers for request in requests[1:])
    assert requests[2].headers["host"] == "second.example"


async def test_redirect_to_private_address_is_rejected(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"url": "https://cdn.example/image"}]}) if request.method == "POST" else httpx.Response(302, headers={"location": "https://169.254.169.254/private"})
    use_transport(monkeypatch, handler)
    with pytest.raises(provider.ImageProviderError, match="下载地址"):
        await adapter().generate(prompt="test")
    assert len(requests) == 2


async def test_dns_rejects_mixed_public_and_private_answers(monkeypatch):
    async def addresses(*args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 443)), (None, None, None, None, ("10.0.0.1", 443))]
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    with pytest.raises(provider.ImageProviderError, match="非公网"):
        await provider.public_address("cdn.example", 443)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 307])
async def test_upstream_errors_never_retry_or_echo_payload(monkeypatch, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "private-test-key"}, headers={"location": "https://other.example/v1"})
    use_transport(monkeypatch, handler)
    with pytest.raises(provider.ImageProviderError) as error:
        await adapter().generate(prompt="test")
    assert "private-test-key" not in str(error.value)
    assert len(calls) == 1


async def test_timeout_does_not_retry(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-test-key")
    use_transport(monkeypatch, handler)
    with pytest.raises(provider.ImageProviderError, match="可能已计费") as error:
        await adapter().generate(prompt="test")
    assert error.value.status_code == 504 and len(calls) == 1


@pytest.mark.parametrize("result", [{}, {"data": []}, {"data": ["invalid"]}, {"data": [{"b64_json": "invalid!"}]}])
async def test_missing_or_invalid_image(monkeypatch, result):
    use_transport(monkeypatch, lambda request: httpx.Response(200, json=result))
    with pytest.raises(provider.ImageProviderError):
        await adapter().generate(prompt="test")


async def test_response_size_limit(monkeypatch):
    monkeypatch.setattr(provider, "MAX_RESPONSE_BYTES", 32)
    use_transport(monkeypatch, lambda request: httpx.Response(200, content=b"x" * 33))
    with pytest.raises(provider.ImageProviderError, match="过大"):
        await adapter().generate(prompt="test")


def test_candidate_round_trip_selection_export_and_delete(monkeypatch, content_id):
    class Fake:
        async def generate(self, **kwargs):
            return provider.ImageResult(png(), "example-model")
    monkeypatch.setattr(covers, "build_image_provider", lambda db: Fake())
    client = TestClient(app)
    root = f"/api/contents/{content_id}/cover"
    original = client.post(root + "/upload", files={"file": ("old.png", png(), "image/png")}).json()
    rendered = client.post(root + "/render", json={"template": "whitespace", "copy": "旧封面"}).json()
    generated = client.post(root + "/generate", json={"prompt": "雨后窗边"})
    assert generated.status_code == 200
    candidate = generated.json()
    assert "path" not in candidate and "filename" not in candidate
    state = client.get(root).json()
    assert state["upload"]["id"] == original["id"] and state["rendered"]["id"] == rendered["id"]
    assert state["candidates"][0]["id"] == candidate["id"]
    assert datetime.fromisoformat(state["candidates"][0]["created_at"]).utcoffset() == timedelta(0)
    assert client.get(candidate["download_url"]).headers["content-disposition"].startswith("attachment")
    assert client.get(candidate["preview_url"]).content == png()
    assert client.get(root.replace(content_id, "missing") + f"/candidates/{candidate['id']}/image").status_code == 404
    selected = client.post(root + f"/candidates/{candidate['id']}/use")
    assert selected.status_code == 200
    state = client.get(root).json()
    assert state["rendered"] is None and state["upload"]["id"] != original["id"]
    assert not Path(rendered["payload"]["path"]).exists()
    assert client.post(root + "/render", json={"template": "magazine", "copy": "雨后窗边"}).status_code == 200
    exported = client.post(f"/api/contents/{content_id}/export")
    assert exported.status_code == 200 and (Path(exported.json()["folder"]) / "封面.png").is_file()
    assert client.request("DELETE", root + f"/candidates/{candidate['id']}", json={"confirm": False}).status_code == 400
    assert client.request("DELETE", root + f"/candidates/{candidate['id']}", json={"confirm": True}).status_code == 200
    assert client.get(root + "/candidates").json() == []
    assert client.get(candidate["preview_url"]).status_code == 404
    assert client.get(client.get(root).json()["upload"]["preview_url"]).content == png()


@pytest.mark.parametrize("kind", ["corrupt", "bytes", "pixels"])
def test_invalid_images_preserve_current_cover(monkeypatch, content_id, kind):
    from backend.app import cover_studio
    data = b"invalid" if kind == "corrupt" else png()
    client = TestClient(app)
    root = f"/api/contents/{content_id}/cover"
    original = client.post(root + "/upload", files={"file": ("old.png", png(), "image/png")}).json()
    if kind == "bytes":
        monkeypatch.setattr(cover_studio, "MAX_UPLOAD_BYTES", 10)
    if kind == "pixels":
        monkeypatch.setattr(cover_studio, "MAX_SOURCE_PIXELS", 100)
    class Fake:
        async def generate(self, **kwargs):
            return provider.ImageResult(data, "example-model")
    monkeypatch.setattr(covers, "build_image_provider", lambda db: Fake())
    assert client.post(root + "/generate", json={"prompt": "test"}).status_code == 502
    state = client.get(root).json()
    assert state["upload"]["id"] == original["id"] and not state["candidates"]
    assert not generation_busy(content_id)


def test_concurrent_requests_only_call_provider_once(monkeypatch, content_id):
    started, finish = Event(), Event()
    calls = []
    class Fake:
        async def generate(self, **kwargs):
            calls.append(kwargs)
            started.set()
            await asyncio.to_thread(finish.wait, 5)
            return provider.ImageResult(png(), "example-model")
    monkeypatch.setattr(covers, "build_image_provider", lambda db: Fake())
    root = f"/api/contents/{content_id}/cover"
    with TestClient(app) as client, ThreadPoolExecutor() as pool:
        future = pool.submit(client.post, root + "/generate", json={"prompt": "test"})
        assert started.wait(3)
        try:
            assert client.get(root).json()["image_generation_busy"]
            assert client.post(root + "/generate", json={"prompt": "test"}).status_code == 409
        finally:
            finish.set()
        assert future.result(timeout=5).status_code == 200
    assert len(calls) == 1 and not generation_busy(content_id)


def test_unconfigured_and_empty_prompt_do_not_generate(content_id):
    client = TestClient(app)
    root = f"/api/contents/{content_id}/cover/generate"
    assert client.post(root, json={"prompt": "test"}).status_code == 400
    assert client.post(root, json={"prompt": "   "}).status_code == 422
    assert client.post(root, json={"prompt": "test", "size": "auto"}).status_code == 422


def test_failed_local_save_preserves_current_cover(monkeypatch, content_id):
    client = TestClient(app)
    root = f"/api/contents/{content_id}/cover"
    original = client.post(root + "/upload", files={"file": ("old.png", png(), "image/png")}).json()
    class Fake:
        async def generate(self, **kwargs):
            return provider.ImageResult(png(), "example-model")
    monkeypatch.setattr(covers, "build_image_provider", lambda db: Fake())
    def fail_write(*args):
        raise OSError("no space")
    monkeypatch.setattr(Path, "write_bytes", fail_write)
    response = client.post(root + "/generate", json={"prompt": "test"})
    assert response.status_code == 500 and "可能已计费" in response.json()["detail"]
    state = client.get(root).json()
    assert state["upload"]["id"] == original["id"] and state["candidates"] == []


async def test_download_size_limit(monkeypatch):
    monkeypatch.setattr(provider, "MAX_IMAGE_BYTES", 32)
    def handler(request):
        return httpx.Response(200, json={"data": [{"url": "https://cdn.example/image"}]}) if request.method == "POST" else httpx.Response(200, content=b"x" * 33)
    use_transport(monkeypatch, handler)
    with pytest.raises(provider.ImageProviderError, match="过大"):
        await adapter().generate(prompt="test")


def test_multicast_download_addresses_are_not_public():
    assert not provider.is_public_address("224.0.0.1")
    assert not provider.is_public_address("ff02::1")


def test_missing_candidate_file_can_be_removed(content_id):
    with SessionLocal() as db:
        item = Artifact(content_id=content_id, artifact_type="GeneratedCoverImage", step_id="cover_and_export",
                        payload={"filename": "missing.png"}, source_artifact_ids=[], content_hash="test")
        db.add(item)
        db.commit()
        candidate_id = item.id
    response = TestClient(app).request("DELETE", f"/api/contents/{content_id}/cover/candidates/{candidate_id}", json={"confirm": True})
    assert response.status_code == 200
