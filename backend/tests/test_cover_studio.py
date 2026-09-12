from io import BytesIO
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import select

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import Artifact, Content, ContentVersion
from backend.app.config import settings
from backend.app.orchestrator import WorkflowError
from backend.app.publishing import export_package


def cover_bytes(image_format: str = "PNG", size: tuple[int, int] = (1400, 1000)) -> bytes:
    image = Image.new("RGB", size, "#ddd7ca")
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 40):
        draw.rectangle((x, 0, x + 20, size[1]), fill="#5d6658")
    for y in range(0, size[1], 50):
        draw.line((0, y, size[0], y), fill="#a35d46", width=5)
    output = BytesIO()
    image.save(output, format=image_format, quality=92)
    return output.getvalue()


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def content_id() -> str:
    with SessionLocal() as db:
        content = Content(theme="城市里的迟到情绪", emotion="想念", title="下班以后")
        db.add(content)
        db.flush()
        db.add(
            Artifact(
                content_id=content.id,
                artifact_type="EssayDraft",
                step_id="draft_generation",
                version=1,
                payload={"cover_copy": "城市比我更晚忘记", "body": "测试正文"},
                source_artifact_ids=[],
                content_hash="draft",
                confirmed=True,
            )
        )
        db.commit()
        return content.id


def test_cover_upload_crop_three_templates_preview_and_confirmed_delete(content_id: str):
    client = TestClient(app)
    empty = client.get(f"/api/contents/{content_id}/cover").json()
    assert empty["upload"] is None and empty["rendered"] is None
    assert empty["defaults"] == {"width": 900, "height": 1200, "ratio": "3:4", "format": "PNG"}

    uploaded = client.post(
        f"/api/contents/{content_id}/cover/upload",
        files={"file": ("原图.png", cover_bytes(), "image/png")},
    )
    assert uploaded.status_code == 200
    upload_payload = uploaded.json()["payload"]
    assert upload_payload["original_retained"] is True
    assert upload_payload["width"] == 1400 and upload_payload["height"] == 1000
    original_path = Path(upload_payload["path"])
    assert original_path.is_file()
    assert client.get(f"/api/contents/{content_id}/cover/artifacts/{uploaded.json()['id']}/image").status_code == 200

    rendered_paths: list[Path] = []
    for template in ("whitespace", "magazine", "subtitle"):
        response = client.post(
            f"/api/contents/{content_id}/cover/render",
            json={
                "template": template,
                "copy": "下班以后才开始想念",
                "focus_x": 0.75,
                "focus_y": 0.35,
                "zoom": 1.4,
                "output_width": 800,
                "output_height": 1000,
            },
        )
        assert response.status_code == 200
        payload = response.json()["payload"]
        assert payload["format"] == "PNG" and payload["width"] == 800 and payload["height"] == 1000
        path = Path(payload["path"])
        rendered_paths.append(path)
        with Image.open(path) as image:
            assert image.format == "PNG" and image.size == (800, 1000)
    assert original_path.is_file(), "生成预览不能覆盖或删除原图"

    state = client.get(f"/api/contents/{content_id}/cover").json()
    assert state["upload"]["quality_status"] == "ready"
    assert state["rendered"]["template"] == "subtitle"
    assert "path" not in state["upload"] and state["rendered"]["preview_url"].startswith("/api/")
    refused = client.request("DELETE", f"/api/contents/{content_id}/cover", json={"confirm": False})
    assert refused.status_code == 400 and original_path.is_file()
    deleted = client.request("DELETE", f"/api/contents/{content_id}/cover", json={"confirm": True})
    assert deleted.status_code == 200 and not original_path.exists()
    assert all(not path.exists() for path in rendered_paths)
    with SessionLocal() as db:
        assert db.scalar(select(Artifact).where(Artifact.artifact_type.in_(["CoverUpload", "CoverPNG"]))) is None


def test_replacing_cover_keeps_only_one_original_and_validates_limits(content_id: str):
    client = TestClient(app)
    first = client.post(
        f"/api/contents/{content_id}/cover/upload",
        files={"file": ("first.png", cover_bytes("PNG"), "image/png")},
    ).json()
    first_path = Path(first["payload"]["path"])
    second_response = client.post(
        f"/api/contents/{content_id}/cover/upload",
        files={"file": ("second.jpg", cover_bytes("JPEG"), "image/jpeg")},
    )
    assert second_response.status_code == 200
    second_path = Path(second_response.json()["payload"]["path"])
    assert not first_path.exists() and second_path.is_file()
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Artifact).where(Artifact.artifact_type == "CoverUpload")))) == 1

    too_large = client.post(
        f"/api/contents/{content_id}/cover/upload",
        files={"file": ("huge.png", b"0" * (15 * 1024 * 1024 + 1), "image/png")},
    )
    assert too_large.status_code == 400 and "15 MB" in too_large.json()["detail"]
    long_copy = client.post(
        f"/api/contents/{content_id}/cover/render",
        json={"template": "whitespace", "copy": "这是一条明显超过十八个汉字限制的封面文案不能保存"},
    )
    assert long_copy.status_code == 422


def test_rendering_the_same_template_keeps_the_previous_image(content_id):
    client = TestClient(app)
    first = client.post(f"/api/contents/{content_id}/cover/render", json={"template": "whitespace", "copy": "第一张封面"}).json()
    original = Path(first["payload"]["path"]).read_bytes()
    second = client.post(f"/api/contents/{content_id}/cover/render", json={"template": "whitespace", "copy": "第二张封面"}).json()
    assert first["payload"]["path"] != second["payload"]["path"]
    assert Path(first["payload"]["path"]).read_bytes() == original
    with SessionLocal() as db:
        assert hashlib.sha256(original).hexdigest() == db.get(Artifact, first["id"]).content_hash
    assert client.get(f"/api/contents/{content_id}/cover/artifacts/{first['id']}/image").content == original


def test_exports_are_independent_and_failed_write_preserves_history(content_id, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "export_dir", tmp_path)
    with SessionLocal() as db:
        content = db.get(Content, content_id)
        version = ContentVersion(content_id=content_id, version=1, kind="manual", title="相同标题",
                                 body_html="<p>旧正文</p>", body_text="旧正文", content_hash="v1")
        db.add(version)
        db.commit()
        first = Path(export_package(db, content)["folder"])
        snapshot = {path.name: path.read_bytes() for path in first.iterdir()}
        version.body_text = "新正文"
        db.commit()
        second = Path(export_package(db, content)["folder"])
        assert first != second
        assert "旧正文" in (first / "发布内容.txt").read_text(encoding="utf-8-sig")
        assert "新正文" in (second / "发布内容.txt").read_text(encoding="utf-8-sig")
        original_write = Path.write_bytes

        def disk_full(path, data):
            if path.name == "发布内容.md":
                raise OSError("disk full")
            return original_write(path, data)

        monkeypatch.setattr(Path, "write_bytes", disk_full)
        before = set(tmp_path.iterdir())
        with pytest.raises(WorkflowError, match="写入失败"):
            export_package(db, content)
        assert set(tmp_path.iterdir()) == before
        assert {path.name: path.read_bytes() for path in first.iterdir()} == snapshot
