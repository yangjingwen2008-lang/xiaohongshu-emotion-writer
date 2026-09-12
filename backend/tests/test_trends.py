import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import Content, ManualTrendSource, TrendCandidate, TrendRefreshRun, TrendSourceRecord
from backend.app.providers import (
    ProviderError,
    ProviderResult,
    SearchHit,
    SearchResponse,
    TavilyTrendSourceProvider,
    TrendCollectionResult,
    TrendEvidence,
    TrendSourceError,
)
from backend.app.trend_scheduler import TASKS, install_schedule
from backend.app.trends import TrendError, TrendService, cleanup_expired_trend_data, use_trend_candidate


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_json(self, *, system_prompt: str, user_prompt: str, task_type: str) -> ProviderResult:
        self.calls.append(task_type)
        payload = json.loads(user_prompt)
        if task_type == "trend_scout":
            source_ids = [item["source_id"] for item in payload["sources"]]
            result = {
                "candidates": [
                    {
                        "title": f"公开讨论线索 {index + 1}",
                        "source_ids": [source_ids[index % len(source_ids)]],
                        "trend_signal": "正在讨论",
                        "trend_basis": "公开页面摘要出现了可核查的关系与城市生活讨论。",
                        "confidence": "中",
                        "data_limitations": "只覆盖搜索服务可访问的公开网页，不代表平台完整热度。",
                    }
                    for index in range(3)
                ],
                "data_status": "sufficient",
                "summary": "形成三条有来源线索",
            }
        else:
            result = {
                "candidates": [
                    {
                        "scout_candidate_index": index,
                        "title": f"把迟到的情绪放回日常 {index + 1}",
                        "emotion": "延迟性痛感",
                        "female_emotional_angle": "从年轻女性在工作和关系之间的身体疲惫进入私人经验。",
                        "account_fit": "高",
                        "homogeneity_risk": "中",
                        "cultural_association": "可轻度联想到城市电影，但不列作品清单。",
                        "rewrite_logic": "只保留情绪内核，重新设计人物、场景和叙事结构。",
                    }
                    for index in range(3)
                ],
                "data_status": "sufficient",
            }
        return ProviderResult(payload=result, model="fake", input_tokens=10, output_tokens=20)


class FakeTrendProvider:
    name = "fake-trend"

    async def collect(self) -> TrendCollectionResult:
        return TrendCollectionResult(
            evidence=[
                TrendEvidence("小红书", "旧街与关系讨论", "https://www.xiaohongshu.com/explore/1", "公开摘要一", 0.8),
                TrendEvidence("豆瓣", "二十岁与现实", "https://www.douban.com/group/topic/2", "公开摘要二", 0.7),
                TrendEvidence("知乎", "工作中的情绪后劲", "https://www.zhihu.com/question/3", "公开摘要三", 0.6),
            ],
            query_count=3,
            request_ids=["req-1", "req-2", "req-3"],
            usage_credits=3,
        )


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.mark.asyncio
async def test_tavily_trend_provider_uses_three_queries_and_deduplicates_urls():
    class FakeSearch:
        name = "fake-search"

        def __init__(self) -> None:
            self.queries: list[str] = []

        async def search(self, query: str, max_results: int = 5) -> SearchResponse:
            self.queries.append(query)
            return SearchResponse(
                query=query,
                results=[SearchHit("讨论", "https://www.zhihu.com/question/1", "公开摘要", 0.9)],
                request_id=f"req-{len(self.queries)}",
                usage_credits=1,
            )

    search = FakeSearch()
    result = await TavilyTrendSourceProvider(search).collect()

    assert len(search.queries) == 3
    assert result.query_count == 3 and result.usage_credits == 3
    assert len(result.evidence) == 1
    assert result.evidence[0].platform == "知乎"


@pytest.mark.asyncio
async def test_tavily_trend_provider_stops_on_first_error_without_retry():
    class FailingSearch:
        name = "failing-search"

        def __init__(self) -> None:
            self.calls = 0

        async def search(self, query: str, max_results: int = 5) -> SearchResponse:
            self.calls += 1
            raise ProviderError("模拟公网失败")

    search = FailingSearch()
    with pytest.raises(TrendSourceError, match="模拟公网失败") as error:
        await TavilyTrendSourceProvider(search).collect()
    assert search.calls == 1
    assert error.value.partial_result.query_count == 0


@pytest.mark.asyncio
async def test_tavily_trend_provider_preserves_completed_queries_before_failure():
    class PartiallyFailingSearch:
        name = "partial-search"

        def __init__(self) -> None:
            self.calls = 0

        async def search(self, query: str, max_results: int = 5) -> SearchResponse:
            self.calls += 1
            if self.calls == 2:
                raise ProviderError("第二条失败")
            return SearchResponse(
                query=query,
                results=[SearchHit("已完成公开来源", "https://www.douban.com/topic/1", "有限摘要", 0.8)],
                request_id="req-first",
                usage_credits=1,
            )

    search = PartiallyFailingSearch()
    with pytest.raises(TrendSourceError) as error:
        await TavilyTrendSourceProvider(search).collect()

    assert search.calls == 2
    assert error.value.partial_result.query_count == 1
    assert error.value.partial_result.request_ids == ["req-first"]
    assert error.value.partial_result.usage_credits == 1
    assert len(error.value.partial_result.evidence) == 1


@pytest.mark.asyncio
async def test_trend_service_persists_sources_candidates_and_selected_lineage():
    with SessionLocal() as db:
        llm = FakeLLM()
        run = await TrendService(db, llm=llm, source_provider=FakeTrendProvider()).refresh()

        assert run.status == "completed" and run.data_status == "sufficient"
        assert run.source_count == 3 and run.candidate_count == 3
        assert llm.calls == ["trend_scout", "topic_strategist"]
        candidates = list(db.scalars(select(TrendCandidate).where(TrendCandidate.run_id == run.id)))
        assert len(candidates) == 3
        assert candidates[0].confidence == "中"
        assert "不代表平台完整热度" in candidates[0].data_limitations

        content = use_trend_candidate(db, candidates[0].id)
        assert content.current_step == "idea_intake"
        assert "不复刻原热点标题" in content.extra_requirements
        assert use_trend_candidate(db, candidates[0].id).id == content.id


@pytest.mark.asyncio
async def test_trend_service_derives_status_when_model_returns_partial_or_explanation():
    class WrongStatusLLM(FakeLLM):
        async def generate_json(
            self, *, system_prompt: str, user_prompt: str, task_type: str
        ) -> ProviderResult:
            result = await super().generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                task_type=task_type,
            )
            result.payload["data_status"] = (
                "partial" if task_type == "trend_scout" else "基于三条候选，未硬凑数量。"
            )
            return result

    with SessionLocal() as db:
        llm = WrongStatusLLM()
        run = await TrendService(db, llm=llm, source_provider=FakeTrendProvider()).refresh()
        assert run.status == "completed"
        assert run.data_status == "sufficient"
        assert run.candidate_count == 3
        assert llm.calls == ["trend_scout", "topic_strategist"]


@pytest.mark.asyncio
async def test_trend_validation_error_is_saved_as_concise_chinese_message():
    class InvalidCandidateLLM(FakeLLM):
        async def generate_json(
            self, *, system_prompt: str, user_prompt: str, task_type: str
        ) -> ProviderResult:
            result = await super().generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                task_type=task_type,
            )
            if task_type == "topic_strategist":
                result.payload["candidates"][0]["account_fit"] = "极高"
            return result

    with SessionLocal() as db:
        with pytest.raises(TrendError, match="账号匹配度") as error:
            await TrendService(db, llm=InvalidCandidateLLM(), source_provider=FakeTrendProvider()).refresh()
        assert "pydantic.dev" not in str(error.value)
        run = db.scalar(select(TrendRefreshRun))
        assert run is not None and run.status == "failed"
        assert "账号匹配度" in run.error_summary
        assert "已保留 3 条有限来源摘要" in run.error_summary
        assert "pydantic.dev" not in run.error_summary


@pytest.mark.asyncio
async def test_scheduled_refresh_is_idempotent_and_empty_sources_are_honest():
    now = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        service = TrendService(db, llm=FakeLLM(), source_configured=False)
        first = await service.refresh(trigger="scheduled", now=now)
        second = await service.refresh(trigger="scheduled", now=now)
        assert first.id == second.id
        assert first.status == "completed"
        assert first.data_status == "data_insufficient"
        assert first.candidate_count == 0
        assert "没有手工补充" in first.error_summary


@pytest.mark.asyncio
async def test_provider_failure_is_recorded_and_does_not_fabricate_candidates():
    class FailingProvider:
        name = "failing"

        async def collect(self) -> TrendCollectionResult:
            raise ProviderError("上游不可用")

    with SessionLocal() as db:
        with pytest.raises(TrendError, match="未自动重试"):
            await TrendService(db, llm=FakeLLM(), source_provider=FailingProvider()).refresh()
        run = db.scalar(select(TrendRefreshRun))
        assert run is not None and run.status == "failed"
        assert db.scalar(select(TrendCandidate)) is None


@pytest.mark.asyncio
async def test_service_saves_partial_public_evidence_but_never_builds_candidates_after_failure():
    class PartialProvider:
        name = "partial"

        async def collect(self) -> TrendCollectionResult:
            partial = TrendCollectionResult(
                evidence=[TrendEvidence("豆瓣", "前序结果", "https://www.douban.com/topic/1", "有限摘要", 0.8)],
                query_count=1,
                request_ids=["req-first"],
                usage_credits=1,
            )
            raise TrendSourceError("第二条公开查询失败", partial)

    with SessionLocal() as db:
        llm = FakeLLM()
        with pytest.raises(TrendError, match="已保存前序有限摘要"):
            await TrendService(db, llm=llm, source_provider=PartialProvider()).refresh()

        run = db.scalar(select(TrendRefreshRun))
        assert run is not None and run.status == "failed"
        assert run.query_count == 1 and run.source_count == 1
        assert run.request_ids == ["req-first"] and run.usage_credits == 1
        assert db.scalar(select(TrendSourceRecord)).source_type == "public_search_partial"
        assert db.scalar(select(TrendCandidate)) is None
        assert llm.calls == []


def test_manual_source_api_requires_confirmation_and_candidate_use_requires_confirmation():
    client = TestClient(app)
    refused = client.post(
        "/api/trends/manual-sources",
        json={"source_type": "topic", "label": "手工话题", "source_value": "城市关系讨论", "confirm": False},
    )
    assert refused.status_code == 400
    bad_url = client.post(
        "/api/trends/manual-sources",
        json={"source_type": "url", "label": "错误链接", "source_value": "javascript:alert(1)", "confirm": True},
    )
    assert bad_url.status_code == 400
    saved = client.post(
        "/api/trends/manual-sources",
        json={"source_type": "topic", "label": "手工话题", "source_value": "城市关系讨论", "confirm": True},
    )
    assert saved.status_code == 200
    assert client.get("/api/trends/manual-sources").json()[0]["label"] == "手工话题"

    with SessionLocal() as db:
        run = TrendRefreshRun(trigger="manual", status="completed", idempotency_key="fixture", provider="manual")
        db.add(run); db.flush()
        candidate = TrendCandidate(
            run_id=run.id,
            title="私人情绪切口",
            emotion="想念",
            source_ids=[],
            source_platforms=["用户手工补充"],
            source_links=[],
            trend_signal="数据不足",
            trend_basis="用户手工补充",
            female_emotional_angle="从私人生活进入",
            account_fit="高",
            homogeneity_risk="低",
            confidence="低",
            data_limitations="只有手工来源",
            rewrite_logic="不复制标题",
        )
        db.add(candidate); db.commit(); candidate_id = candidate.id
    refused_use = client.post(f"/api/trends/candidates/{candidate_id}/use", json={"confirm": False})
    assert refused_use.status_code == 400
    accepted = client.post(f"/api/trends/candidates/{candidate_id}/use", json={"confirm": True})
    assert accepted.status_code == 200


def test_cleanup_removes_only_expired_unselected_raw_runs():
    old = datetime.now(timezone.utc) - timedelta(days=31)
    with SessionLocal() as db:
        removable = TrendRefreshRun(trigger="manual", status="completed", idempotency_key="old-remove", provider="manual", started_at=old)
        retained = TrendRefreshRun(trigger="manual", status="completed", idempotency_key="old-keep", provider="manual", started_at=old)
        content = Content(theme="保留来源", emotion="克制")
        db.add_all([removable, retained, content]); db.flush()
        source = ManualTrendSource(source_type="topic", label="旧来源", source_value="旧讨论", content_hash="hash", created_at=old)
        db.add(source); db.flush()
        db.add(TrendSourceRecord(run_id=retained.id, manual_source_id=source.id, source_type="manual_input", platform="手工", title="旧来源", snippet="旧讨论", collected_at=old))
        db.add(TrendCandidate(run_id=retained.id, title="已选", emotion="克制", source_ids=[], source_platforms=[], source_links=[], trend_signal="数据不足", trend_basis="手工", female_emotional_angle="私人经验", account_fit="高", homogeneity_risk="低", confidence="低", data_limitations="手工", rewrite_logic="重写", used_content_id=content.id))
        db.commit()

        result = cleanup_expired_trend_data(db)
        assert result["runs"] == 1
        assert db.get(TrendRefreshRun, removable.id) is None
        assert db.get(TrendRefreshRun, retained.id) is not None
        assert db.get(ManualTrendSource, source.id) is not None


def test_scheduler_creates_two_daily_limited_tasks(monkeypatch: pytest.MonkeyPatch):
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args: list[str]) -> Any:
        calls.append(args)
        return Result()

    monkeypatch.setattr("backend.app.trend_scheduler._supported", lambda: True)
    monkeypatch.setattr("backend.app.trend_scheduler._run", fake_run)
    result = install_schedule()

    creates = [call for call in calls if "/Create" in call]
    assert len(creates) == 2
    assert {call[call.index("/ST") + 1] for call in creates} == set(TASKS)
    assert all(call[call.index("/SC") + 1] == "DAILY" for call in creates)
    assert result["installed"] is True
