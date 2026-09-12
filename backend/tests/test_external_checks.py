from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.database import Base, SessionLocal, engine
from backend.app.external_checks import enrich_originality_report, verify_cultural_references
from backend.app.main import app
from backend.app.models import Content, ContentVersion, ExternalCheckRun, ManualOriginalitySource
from backend.app.providers import ProviderError, SearchHit, SearchResponse, TavilySearchProvider
from backend.app.schemas import OriginalityReport


class FakeSearch:
    name = "fake-search"

    def __init__(self, fail_after: int | None = None) -> None:
        self.queries: list[str] = []
        self.fail_after = fail_after

    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        if self.fail_after is not None and len(self.queries) >= self.fail_after:
            raise ProviderError("模拟搜索服务失败")
        self.queries.append(query)
        if "活着" in query:
            hits = [SearchHit("《活着》余华作品介绍", "https://example.org/huozhe", "余华创作的长篇小说《活着》", 0.9)]
        else:
            hits = [SearchHit("城市比我更晚忘记", "https://example.org/note", "她从便利店门口经过，城市还记得分别。", 0.8)]
        return SearchResponse(query=query, results=hits[:max_results], request_id=f"req-{len(self.queries)}", usage_credits=1)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def base_report() -> OriginalityReport:
    return OriginalityReport(
        local_history_completed=True,
        public_web_completed=False,
        xiaohongshu_public_completed=False,
        uncovered_sources=[],
        title_risk="低",
        opening_risk="低",
        structure_risk="低",
        metaphor_risk="低",
        scene_risk="低",
        ending_risk="低",
        matches=[],
        suggestions=[],
        passes_gate=True,
    )


def make_article(db: Any) -> tuple[Content, ContentVersion]:
    content = Content(theme="旧街", emotion="想念", title="城市比我更晚忘记")
    db.add(content)
    db.flush()
    version = ContentVersion(
        content_id=content.id,
        version=1,
        kind="human_edit",
        title="城市比我更晚忘记",
        body_html="<p>她从便利店门口经过，城市还记得分别。</p>",
        body_text="她从便利店门口经过，城市还记得分别。",
        metadata_json={},
        content_hash="hash",
    )
    db.add(version)
    db.flush()
    return content, version


def test_manual_originality_source_api_requires_confirmation_and_validates_urls():
    with SessionLocal() as db:
        content, _ = make_article(db)
        db.commit()
        content_id = content.id

    client = TestClient(app)
    refused = client.post(
        f"/api/contents/{content_id}/originality-sources",
        json={"source_type": "body", "label": "参考正文", "source_value": "一段公开内容", "confirm": False},
    )
    assert refused.status_code == 400

    invalid_url = client.post(
        f"/api/contents/{content_id}/originality-sources",
        json={"source_type": "url", "label": "错误链接", "source_value": "javascript:alert(1)", "confirm": True},
    )
    assert invalid_url.status_code == 400

    saved = client.post(
        f"/api/contents/{content_id}/originality-sources",
        json={"source_type": "body", "label": "参考正文", "source_value": "一段公开内容", "confirm": True},
    )
    assert saved.status_code == 200
    assert saved.json()["label"] == "参考正文"
    listed = client.get(f"/api/contents/{content_id}/originality-sources")
    assert listed.status_code == 200
    assert [item["label"] for item in listed.json()] == ["参考正文"]


@pytest.mark.asyncio
async def test_originality_combines_public_and_manual_sources_with_honest_scope():
    with SessionLocal() as db:
        content, version = make_article(db)
        db.add(
            ManualOriginalitySource(
                content_id=content.id,
                source_type="body",
                label="用户粘贴的公开文章",
                source_value="她从便利店门口经过，城市还记得分别。",
                content_hash="manual-hash",
            )
        )
        search = FakeSearch()
        report = await enrich_originality_report(db, content, version, base_report(), search)
        db.commit()

        assert len(search.queries) == 3
        assert report.public_web_completed is True
        assert report.xiaohongshu_public_completed is True
        assert report.external_check_status == "completed"
        assert report.web_matches and report.manual_matches
        assert report.passes_gate is False
        assert "需要登录" in report.uncovered_sources[0]
        run = db.scalar(select(ExternalCheckRun).where(ExternalCheckRun.check_type == "originality"))
        assert run is not None and run.query_count == 3
        assert run.usage_credits == 3


@pytest.mark.asyncio
async def test_originality_stops_after_provider_error_without_retry():
    with SessionLocal() as db:
        content, version = make_article(db)
        search = FakeSearch(fail_after=1)
        report = await enrich_originality_report(db, content, version, base_report(), search)
        db.commit()

        assert len(search.queries) == 1
        assert report.external_check_status == "failed"
        assert "未自动重试" in str(report.coverage_details)
        run = db.scalar(select(ExternalCheckRun).where(ExternalCheckRun.check_type == "originality"))
        assert run is not None and run.status == "failed" and run.query_count == 1


@pytest.mark.asyncio
async def test_citation_verifier_returns_evidence_and_never_invents_source():
    with SessionLocal() as db:
        content, _ = make_article(db)
        report = await verify_cultural_references(
            db,
            content,
            [{"work": "活着", "author": "余华"}],
            FakeSearch(),
        )
        assert report.check_status == "completed"
        assert report.items[0].status == "verified"
        assert report.items[0].evidence[0]["url"] == "https://example.org/huozhe"

        unavailable = await verify_cultural_references(db, content, [{"quote": "无法确认的句子"}], None)
        assert unavailable.items[0].status == "unverified"
        assert unavailable.items[0].evidence == []
        assert "个人化转述" in unavailable.items[0].recommendation


@pytest.mark.asyncio
async def test_citation_verifier_marks_references_above_limit_as_unverified():
    with SessionLocal() as db:
        content, _ = make_article(db)
        references = [{"work": f"作品{i}"} for i in range(6)]
        search = FakeSearch()
        report = await verify_cultural_references(db, content, references, search)

        assert len(search.queries) == 5
        assert len(report.items) == 6
        assert report.items[-1].status == "unverified"
        assert "最多联网核验 5 条" in report.items[-1].recommendation
        assert "另有 1 条" in report.coverage_note


@pytest.mark.asyncio
async def test_tavily_provider_uses_basic_search_and_discards_raw_content(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "request_id": "request-1",
                "usage": {"credits": 1},
                "results": [{"title": "结果", "url": "https://example.org", "content": "摘要", "raw_content": "不应保留", "score": 0.75}],
            }

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
            captured.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("backend.app.providers.httpx.AsyncClient", FakeClient)
    response = await TavilySearchProvider("secret").search("测试", max_results=1)

    assert captured["json"]["search_depth"] == "basic"
    assert captured["json"]["include_answer"] is False
    assert captured["json"]["include_raw_content"] is False
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert response.results[0].content == "摘要"
    assert not hasattr(response.results[0], "raw_content")
