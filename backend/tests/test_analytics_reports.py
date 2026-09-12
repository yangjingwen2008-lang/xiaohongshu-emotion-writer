import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.analytics_reports import (
    AnalyticsReportError,
    confirm_report,
    dismiss_report,
    generate_report,
)
from backend.app.api import get_analytics_llm_provider
from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.memory_retrieval import confirmed_analytics_experiments
from backend.app.models import AnalyticsSnapshot, Content, Publication
from backend.app.providers import ProviderResult


client = TestClient(app)


class FakeAnalyticsProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_json(self, *, system_prompt: str, user_prompt: str, task_type: str) -> ProviderResult:
        self.calls += 1
        source = json.loads(user_prompt)
        snapshot_ids = [
            snapshot["snapshot_id"]
            for publication in source["publications"]
            for snapshot in publication["snapshots"]
        ]
        scope = task_type.removeprefix("analytics_")
        return ProviderResult(
            payload={
                "report_scope": scope,
                "sample_size": 999,
                "period_summary": "只分析已确认快照，当前样本仍然有限。",
                "observations": [
                    {
                        "label": "收藏相对稳定",
                        "finding": "收藏率在现有快照中保持稳定，但不能据此判断平台推荐原因。",
                        "snapshot_ids": snapshot_ids,
                        "confidence": "中",
                        "caveat": "样本少，只能视为相关性线索。",
                    }
                ],
                "correlations_not_causes": ["收藏率与具体场景同时出现，但不能证明因果。"],
                "suggestions": [
                    {
                        "suggestion_id": "scene_opening_test",
                        "applies_to": "开头",
                        "experiment": "下一篇只测试一次更快进入具体场景的开头。",
                        "rationale": "现有快照只能支持一次可逆的小实验。",
                        "evidence_snapshot_ids": snapshot_ids,
                        "confidence": "中",
                    }
                ],
                "preserve_identity": ["保留第一人称的不体面和具体生活触感。"],
                "limitations": ["没有平台算法数据，也没有未录入文章的数据。"],
                "conclusion": "可以谨慎试一次，但不能形成固定开头模板。",
            },
            model="fake-analytics",
            input_tokens=120,
            output_tokens=80,
        )


@pytest.fixture(autouse=True)
def clean_db_and_dependency():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    app.dependency_overrides.pop(get_analytics_llm_provider, None)


def create_publication_with_snapshots(db, *, title: str = "那条街还记得") -> Publication:
    now = datetime.now(timezone.utc)
    content = Content(theme="分别后的城市", emotion="迟来的想念", status="published")
    db.add(content)
    db.flush()
    publication = Publication(
        content_id=content.id,
        note_url="https://www.xiaohongshu.com/explore/report-test",
        published_at=now - timedelta(days=4),
        final_title=title,
        final_tags=["城市", "想念"],
        recommended_publish_time="21:30",
    )
    db.add(publication)
    db.flush()
    db.add_all(
        [
            AnalyticsSnapshot(
                publication_id=publication.id,
                day_offset=1,
                captured_at=now - timedelta(days=3),
                metrics={"views": 1000, "favorites": 80},
                calculated_rates={"favorite_rate": 0.08},
                source_type="manual",
            ),
            AnalyticsSnapshot(
                publication_id=publication.id,
                day_offset=3,
                captured_at=now - timedelta(days=1),
                metrics={"views": 1600, "favorites": 136},
                calculated_rates={"favorite_rate": 0.085},
                source_type="ocr_confirmed",
            ),
        ]
    )
    db.commit()
    db.refresh(publication)
    return publication


@pytest.mark.asyncio
async def test_single_report_is_snapshot_idempotent_and_only_confirmed_suggestions_enter_memory():
    provider = FakeAnalyticsProvider()
    with SessionLocal() as db:
        publication = create_publication_with_snapshots(db)
        first = await generate_report(db, provider, "single", publication.id)
        duplicate = await generate_report(db, provider, "single", publication.id)

        assert duplicate.id == first.id
        assert provider.calls == 1
        assert first.payload["sample_size"] == 1
        assert confirmed_analytics_experiments(db) == []

        with pytest.raises(AnalyticsReportError, match="存在的建议"):
            confirm_report(db, first.id, ["invented"], None, True)
        confirmed = confirm_report(db, first.id, ["scene_opening_test"], "只试一次", True)
        experiments = confirmed_analytics_experiments(db)
        assert confirmed.status == "confirmed"
        assert experiments[0]["suggestion_id"] == "scene_opening_test"
        assert "不覆盖风格档案" in experiments[0]["usage_boundary"]

        db.add(
            AnalyticsSnapshot(
                publication_id=publication.id,
                day_offset=7,
                captured_at=datetime.now(timezone.utc),
                metrics={"views": 2100, "favorites": 170},
                calculated_rates={"favorite_rate": 0.081},
            )
        )
        db.commit()
        updated = await generate_report(db, provider, "single", publication.id)
        assert updated.id != first.id
        assert provider.calls == 2
        assert first.payload["suggestions"][0]["experiment"].startswith("下一篇只测试一次")


@pytest.mark.asyncio
async def test_weekly_report_uses_only_snapshots_in_range_and_dismiss_preserves_history():
    provider = FakeAnalyticsProvider()
    with SessionLocal() as db:
        create_publication_with_snapshots(db, title="第一篇")
        create_publication_with_snapshots(db, title="第二篇")
        today = datetime.now(timezone.utc).date()
        report = await generate_report(
            db,
            provider,
            "weekly",
            period_start=today - timedelta(days=6),
            period_end=today,
        )
        assert report.payload["sample_size"] == 2
        assert len(report.input_snapshot_ids) == 4
        original_payload = json.loads(json.dumps(report.payload, ensure_ascii=False))
        dismissed = dismiss_report(db, report.id, "样本仍少，暂不采用", True)
        assert dismissed.status == "dismissed"
        assert dismissed.payload == original_payload
        assert confirmed_analytics_experiments(db) == []

        with pytest.raises(AnalyticsReportError, match="不能超过 7 天"):
            await generate_report(
                db,
                provider,
                "weekly",
                period_start=today - timedelta(days=7),
                period_end=today,
            )


def test_report_api_generates_lists_and_confirms_with_explicit_gate():
    provider = FakeAnalyticsProvider()
    app.dependency_overrides[get_analytics_llm_provider] = lambda: provider
    with SessionLocal() as db:
        publication = create_publication_with_snapshots(db)

    generated = client.post(
        "/api/analytics/reports/generate",
        json={"report_type": "single", "publication_id": publication.id},
    )
    assert generated.status_code == 200, generated.text
    report = generated.json()
    assert report["status"] == "generated"

    listed = client.get("/api/analytics/reports", params={"report_type": "single"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [report["id"]]

    rejected = client.post(
        f"/api/analytics/reports/{report['id']}/confirm",
        json={"selected_suggestion_ids": ["scene_opening_test"], "confirm": False},
    )
    assert rejected.status_code == 400

    confirmed = client.post(
        f"/api/analytics/reports/{report['id']}/confirm",
        json={"selected_suggestion_ids": ["scene_opening_test"], "note": "人工确认一次实验", "confirm": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed_suggestion_ids"] == ["scene_opening_test"]
