from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from backend.app.api import get_ocr_provider
from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import AnalyticsSnapshot, CommentRecord, Content, ManualTrendSource, OcrRun, Publication
from backend.app.ocr import OcrError, OcrResult, parse_analytics_metrics, parse_comment_lines, validate_image


class FakeOCRProvider:
    name = "fake-local-ocr"

    def status(self) -> dict:
        return {"available": True, "provider": self.name, "local_only": True, "languages": ["zh-Hans-CN"]}

    def recognize(self, image_path: Path) -> OcrResult:
        assert image_path.is_file()
        return OcrResult(
            text="下班以后，我才开始想念。",
            lines=["下班以后，我才开始想念。"],
            provider=self.name,
            metadata={"language": "zh-Hans-CN", "local_only": True},
        )


def image_bytes(image_format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (320, 180), "white").save(output, format=image_format)
    return output.getvalue()


@pytest.fixture(autouse=True)
def clean_db_and_provider():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_ocr_provider] = lambda: FakeOCRProvider()
    yield
    app.dependency_overrides.pop(get_ocr_provider, None)


def test_validate_image_rejects_non_image_and_oversized_dimensions():
    with pytest.raises(OcrError, match="有效"):
        validate_image(b"not-an-image")
    output = BytesIO()
    Image.new("1", (6000, 5000)).save(output, format="PNG")
    with pytest.raises(OcrError, match="2500 万"):
        validate_image(output.getvalue())


def test_local_ocr_requires_correction_confirmation_then_deletes_screenshot():
    client = TestClient(app)
    status = client.get("/api/ocr/status").json()
    assert status["available"] is True and status["cloud_ocr"] is False
    created = client.post(
        "/api/ocr/trends",
        files={"file": ("讨论截图.png", image_bytes(), "image/png")},
    )
    assert created.status_code == 200
    run = created.json()
    assert run["status"] == "pending_confirmation"
    assert run["recognized_text"] == "下班以后，我才开始想念。"
    assert client.get(f"/api/ocr/runs/{run['id']}/image").status_code == 200
    with SessionLocal() as db:
        stored = db.get(OcrRun, run["id"])
        image_path = Path(stored.image_path)
        assert image_path.is_file()

    refused = client.post(
        f"/api/ocr/runs/{run['id']}/confirm",
        json={"label": "下班后的讨论", "corrected_text": "下班以后，我才真正开始想念。", "confirm": False},
    )
    assert refused.status_code == 400 and image_path.is_file()
    confirmed = client.post(
        f"/api/ocr/runs/{run['id']}/confirm",
        json={"label": "下班后的讨论", "corrected_text": "下班以后，我才真正开始想念。", "confirm": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert not image_path.exists()
    assert client.get(f"/api/ocr/runs/{run['id']}/image").status_code == 404
    with SessionLocal() as db:
        source = db.scalar(select(ManualTrendSource))
        assert source.source_type == "screenshot"
        assert source.source_value == "下班以后，我才真正开始想念。"


def test_duplicate_pending_upload_is_idempotent_and_discard_clears_private_text():
    client = TestClient(app)
    payload = image_bytes("JPEG")
    first = client.post("/api/ocr/trends", files={"file": ("a.jpg", payload, "image/jpeg")}).json()
    second = client.post("/api/ocr/trends", files={"file": ("b.jpg", payload, "image/jpeg")}).json()
    assert first["id"] == second["id"]
    refused = client.post(f"/api/ocr/runs/{first['id']}/discard", json={"confirm": False})
    assert refused.status_code == 400
    discarded = client.post(f"/api/ocr/runs/{first['id']}/discard", json={"confirm": True})
    assert discarded.status_code == 200
    assert discarded.json()["status"] == "discarded"
    assert discarded.json()["recognized_text"] is None
    with SessionLocal() as db:
        stored = db.get(OcrRun, first["id"])
        assert stored.image_path is None and stored.lines == []


@pytest.mark.parametrize("purpose", ["trends", "analytics", "comments"])
def test_pending_screenshots_have_independent_files_and_deletion(purpose):
    with SessionLocal() as db:
        content = Content(theme="独立截图测试", emotion="平静")
        db.add(content)
        db.flush()
        publication = Publication(content_id=content.id, note_url="https://www.xiaohongshu.com/explore/test",
                                  published_at=content.created_at, final_title="测试", final_tags=[])
        db.add(publication)
        db.commit()
        publication_id = publication.id
    data = {"publication_id": publication_id, "day_offset": "1"} if purpose != "trends" else {}
    client = TestClient(app)
    images, runs = [], []
    for color in ("white", "black"):
        output = BytesIO()
        Image.new("RGB", (320, 180), color).save(output, "PNG")
        images.append(output.getvalue())
        response = client.post(f"/api/ocr/{purpose}", data=data, files={"file": ("screenshot.png", images[-1], "image/png")})
        assert response.status_code == 200
        runs.append(response.json())
    assert runs[0]["id"] != runs[1]["id"]
    for run, image in zip(runs, images):
        assert client.get(f"/api/ocr/runs/{run['id']}/image").content == image
        with SessionLocal() as db:
            assert Path(db.get(OcrRun, run["id"]).image_path).stem == run["id"]
    if purpose == "analytics":
        deleted = client.request("DELETE", f"/api/ocr/runs/{runs[0]['id']}/image", json={"confirm": True})
    else:
        deleted = client.post(f"/api/ocr/runs/{runs[0]['id']}/discard", json={"confirm": True})
    assert deleted.status_code == 200
    assert client.get(f"/api/ocr/runs/{runs[0]['id']}/image").status_code == 404
    assert client.get(f"/api/ocr/runs/{runs[1]['id']}/image").content == images[1]


def test_ocr_failure_deletes_image_and_records_clear_partial_state():
    class FailingProvider(FakeOCRProvider):
        name = "failing-local-ocr"

        def recognize(self, image_path: Path) -> OcrResult:
            raise OcrError("模拟识别失败")

    app.dependency_overrides[get_ocr_provider] = lambda: FailingProvider()
    client = TestClient(app)
    response = client.post("/api/ocr/trends", files={"file": ("bad.png", image_bytes(), "image/png")})
    assert response.status_code == 422
    assert "原截图已永久删除" in response.json()["detail"]
    with SessionLocal() as db:
        run = db.scalar(select(OcrRun))
        assert run.status == "failed" and run.image_path is None
        assert run.recognized_text is None and run.error_summary == "模拟识别失败"


def test_parse_analytics_metrics_supports_counts_ratios_and_ten_thousands():
    parsed = parse_analytics_metrics(
        "曝光量 1.2万\n浏览量：8600\n点赞 320\n收藏 180\n评论 26\n分享 12\n"
        "新增关注 9\n主页访问 45\n完读率 63 · 5％\n平均阅读时长 18.2秒\n粉丝占比 41%\n非粉丝占比 59%"
    )
    assert parsed == {
        "impressions": 12000,
        "views": 8600,
        "likes": 320,
        "favorites": 180,
        "comments": 26,
        "shares": 12,
        "new_followers": 9,
        "profile_visits": 45,
        "completion_rate": 0.635,
        "average_read_seconds": 18.2,
        "follower_view_ratio": 0.41,
        "non_follower_view_ratio": 0.59,
    }


def test_analytics_ocr_requires_confirmation_retains_image_then_allows_permanent_delete():
    class MetricsProvider(FakeOCRProvider):
        def recognize(self, image_path: Path) -> OcrResult:
            return OcrResult(
                text="浏览量 8600\n点赞 320\n收藏 180\n评论 26\n完读率 63.5%",
                lines=["浏览量 8600", "点赞 320", "收藏 180", "评论 26", "完读率 63.5%"],
                provider=self.name,
                metadata={"language": "zh-Hans-CN", "local_only": True},
            )

    app.dependency_overrides[get_ocr_provider] = lambda: MetricsProvider()
    with SessionLocal() as db:
        content = Content(theme="数据截图", emotion="平静", status="published", current_step="publication_record")
        db.add(content)
        db.flush()
        publication = Publication(
            content_id=content.id,
            note_url="https://www.xiaohongshu.com/explore/test",
            published_at=content.created_at,
            final_title="数据截图测试",
            final_tags=[],
        )
        db.add(publication)
        db.commit()
        publication_id = publication.id

    client = TestClient(app)
    created = client.post(
        "/api/ocr/analytics",
        data={"publication_id": publication_id, "day_offset": "3"},
        files={"file": ("创作后台.png", image_bytes(), "image/png")},
    )
    assert created.status_code == 200
    run = created.json()
    assert run["retention_policy"] == "retain_until_manual_delete"
    assert run["engine_metadata"]["parsed_metrics"]["views"] == 8600
    with SessionLocal() as db:
        image_path = Path(db.get(OcrRun, run["id"]).image_path)
        assert image_path.is_file()

    refused = client.post(
        f"/api/ocr/runs/{run['id']}/confirm-analytics",
        json={"corrected_text": run["recognized_text"], "metrics": {"views": 8600, "likes": 321}, "confirm": False},
    )
    assert refused.status_code == 400 and image_path.is_file()
    confirmed = client.post(
        f"/api/ocr/runs/{run['id']}/confirm-analytics",
        json={
            "corrected_text": "浏览量 8600\n点赞 321（人工修正）",
            "metrics": {"views": 8600, "likes": 321, "favorites": 180, "comments": 26, "completion_rate": 0.635},
            "note": "第 3 天后台截图",
            "confirm": True,
        },
    )
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    assert image_path.is_file(), "数据后台截图确认后应按文档长期本地保留"
    with SessionLocal() as db:
        snapshot = db.scalar(select(AnalyticsSnapshot))
        assert snapshot.day_offset == 3 and snapshot.source_type == "ocr_confirmed"
        assert snapshot.metrics["likes"] == 321
        assert confirmed.json()["linked_analytics_snapshot_id"] == snapshot.id

    delete_refused = client.request("DELETE", f"/api/ocr/runs/{run['id']}/image", json={"confirm": False})
    assert delete_refused.status_code == 400 and image_path.is_file()
    deleted = client.request("DELETE", f"/api/ocr/runs/{run['id']}/image", json={"confirm": True})
    assert deleted.status_code == 200 and not image_path.exists()
    assert deleted.json()["corrected_text"] == "浏览量 8600\n点赞 321（人工修正）"
    with SessionLocal() as db:
        assert db.scalar(select(AnalyticsSnapshot)) is not None


def test_parse_comment_lines_suggests_authors_but_ignores_time_metadata():
    assert parse_comment_lines("• 小雨：看到这里很想哭\n3 小时前\n谢谢你写出来") == [
        {"author_label": "小雨", "text": "看到这里很想哭"},
        {"author_label": None, "text": "谢谢你写出来"},
    ]


def test_comment_ocr_requires_correction_then_deletes_screenshot_and_saves_multiple_comments():
    class CommentProvider(FakeOCRProvider):
        def recognize(self, image_path: Path) -> OcrResult:
            return OcrResult(
                text="小雨：看到这里很想哭\n3小时前\n谢谢你写出来",
                lines=["评论区", "小雨：看到这里很想哭", "3小时前", "谢谢你写出来"],
                provider=self.name,
                metadata={"language": "zh-Hans-CN", "local_only": True},
            )

    app.dependency_overrides[get_ocr_provider] = lambda: CommentProvider()
    with SessionLocal() as db:
        content = Content(theme="评论截图", emotion="被理解", status="published")
        db.add(content)
        db.flush()
        publication = Publication(
            content_id=content.id,
            note_url="https://www.xiaohongshu.com/explore/comment-ocr-test",
            published_at=content.created_at,
            final_title="评论截图测试",
            final_tags=[],
        )
        db.add(publication)
        db.commit()
        publication_id = publication.id

    client = TestClient(app)
    created = client.post(
        "/api/ocr/comments",
        data={"publication_id": publication_id},
        files={"file": ("评论区.png", image_bytes(), "image/png")},
    )
    assert created.status_code == 200, created.text
    run = created.json()
    assert run["retention_policy"] == "delete_after_confirmation"
    assert len(run["engine_metadata"]["suggested_comments"]) == 2
    with SessionLocal() as db:
        image_path = Path(db.get(OcrRun, run["id"]).image_path)
        assert image_path.is_file()

    refused = client.post(
        f"/api/ocr/runs/{run['id']}/confirm-comments",
        json={"corrected_text": run["recognized_text"], "comments": [{"text": "看到这里很想哭"}], "confirm": False},
    )
    assert refused.status_code == 400 and image_path.is_file()
    confirmed = client.post(
        f"/api/ocr/runs/{run['id']}/confirm-comments",
        json={
            "corrected_text": "小雨：看到这里很想哭\n晚风：谢谢你写出来",
            "comments": [
                {"author_label": "小雨", "text": "看到这里很想哭"},
                {"author_label": "晚风", "text": "谢谢你写出来"},
            ],
            "confirm": True,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["recognized_text"] is None
    assert confirmed.json()["corrected_text"] is None
    assert not image_path.exists()
    with SessionLocal() as db:
        comments = list(db.scalars(select(CommentRecord).order_by(CommentRecord.author_label)))
        assert len(comments) == 2
        assert all(item.source_type == "screenshot" and item.source_ocr_run_id == run["id"] for item in comments)
