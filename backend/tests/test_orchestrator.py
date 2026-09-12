from typing import Any
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.database import Base, SessionLocal, engine
from backend.app.models import ApiUsage, Content, DiffMemoryCandidate, WorkflowStep
from backend.app.orchestrator import WorkflowError, WorkflowOrchestrator, friendly_workflow_validation_error
from backend.app.providers import ProviderResult
from backend.app.publishing import export_package
from backend.app.schemas import AIToneReview, EssayDraft, RiskReport, StyleReview


class FakeProvider:
    def __init__(self, cultural_references: list[dict[str, Any]] | None = None) -> None:
        self.cultural_references = cultural_references or []

    async def generate_json(self, *, system_prompt: str, user_prompt: str, task_type: str) -> ProviderResult:
        payloads: dict[str, dict[str, Any]] = {
            "plan_generation": {
                "plans": [
                    {
                        "plan_id": f"p{i}",
                        "title": f"方案{i}",
                        "angle": angle,
                        "opening_example": "她在便利店门口停了很久。",
                        "core_view": "关系结束后，城市仍替人保留记忆。",
                        "narrative_structure": ["场景", "回忆", "停顿"],
                        "scenes": ["便利店"],
                        "emotion_curve": ["迟钝", "刺痛", "未回答"],
                        "cultural_association": None,
                        "potential_risk": "避免重复雨夜意象",
                        "detail_question": "她当时手里拿着什么？",
                    }
                    for i, angle in enumerate(("私人关系", "女性经验", "城市联想"), start=1)
                ]
            },
            "detail_enrichment": {
                "question": "她当时手里拿着什么？",
                "virtual_details": ["一盒变凉的牛奶", "一张旧电影票", "没送出的钥匙"],
            },
            "draft_generation": {
                "title": "那家便利店还记得我们",
                "body": "原来，她在便利店门口停了很久。\n城市没有替谁保守秘密。" * 80,
                "alternate_titles": ["我绕开那条街", "城市比我更晚忘记"],
                "core_tags": ["情感随笔"],
                "trend_tags": [],
                "long_tail_tags": ["分开后的城市记忆"],
                "pinned_comment": "有些路不是不能走，只是走得慢了一点。",
                "cover_copy": "城市比我更晚忘记",
                "recommended_publish_time": "21:30",
                "recommendation_basis": "通用晚间阅读时段，尚无账号历史数据",
                "recommendation_confidence": "低",
                "cultural_references": self.cultural_references,
                "fictionality_notes": ["便利店场景为虚构"],
            },
            "style_review": {
                "dimensions": [{"name": "具体性", "rating": "高", "evidence": "便利店和牛奶构成具体场景"}],
                "issues": [],
                "strengths": ["场景明确"],
                "summary": "符合编辑宪法",
            },
            "ai_tone_review": {
                "issues": [],
                "revised_body": "保留原稿",
                "preserved_roughness": ["短句"],
                "summary": "模板化风险低",
            },
            "risk_review": {"risks": [], "blocks_submission": False, "summary": "无阻止提交项"},
        }
        return ProviderResult(payload=payloads[task_type], model="fake", input_tokens=10, output_tokens=20)


class StringSequenceProvider(FakeProvider):
    async def generate_json(
        self, *, system_prompt: str, user_prompt: str, task_type: str
    ) -> ProviderResult:
        result = await super().generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_type=task_type,
        )
        if task_type == "plan_generation":
            assert "必须是 JSON 字符串数组" in system_prompt
            for index, plan in enumerate(result.payload["plans"]):
                plan["narrative_structure"] = "单线递进" if index == 0 else "场景进入。回忆展开。动作留白。"
                plan["scenes"] = "公园长椅、末班公交"
                plan["emotion_curve"] = "克制" if index == 0 else "紧张→错愕→余波"
        return result


class FailOncePlanProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.plan_calls = 0

    async def generate_json(
        self, *, system_prompt: str, user_prompt: str, task_type: str
    ) -> ProviderResult:
        if task_type == "plan_generation":
            self.plan_calls += 1
            if self.plan_calls == 1:
                return ProviderResult(
                    payload={"plans": []},
                    model="fake-invalid",
                    input_tokens=11,
                    output_tokens=7,
                )
        return await super().generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_type=task_type,
        )


class LooseDraftProvider(FakeProvider):
    async def generate_json(
        self, *, system_prompt: str, user_prompt: str, task_type: str
    ) -> ProviderResult:
        result = await super().generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_type=task_type,
        )
        if task_type == "draft_generation":
            assert "fictionality_notes 必须是字符串数组" in system_prompt
            assert "cultural_references 必须是对象数组" in system_prompt
            result.payload["alternate_titles"] = "我绕开那条街、城市比我更晚忘记"
            result.payload["core_tags"] = "#情感随笔 #女性成长"
            result.payload["cultural_references"] = ["伍尔夫《一间自己的房间》"]
            result.payload["fictionality_notes"] = "便利店场景为虚构"
        return result


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.mark.asyncio
async def test_core_workflow_is_deterministic_and_versioned():
    with SessionLocal() as db:
        content = Content(theme="分开后不敢走的街", emotion="延迟性痛感")
        db.add(content)
        db.commit()
        orchestrator = WorkflowOrchestrator(db, llm=FakeProvider())
        plans = await orchestrator.generate_plans(content.id)
        orchestrator.select_plan(content.id, "p1")
        detail = await orchestrator.generate_detail_question(content.id)
        orchestrator.select_detail(content.id, "fictional", detail.payload["virtual_details"][0])
        draft = await orchestrator.generate_draft(content.id)
        assert len(plans.payload["plans"]) == 3
        assert draft.payload["cover_copy"] == "城市比我更晚忘记"
        assert content.current_step == "human_edit"
        assert len(content.versions) == 1
        memory_report = next(item for item in content.artifacts if item.artifact_type == "GenerationMemoryReport")
        assert "未注入历史正文" in memory_report.payload["retrieval_scope"]
        assert memory_report.payload["retrieval_engine"] == "sqlite-fts5-char-ngram-v1"
        assert "body" not in content.versions[0].metadata_json
        assert "memory_fingerprint" in content.versions[0].metadata_json
        edited_body = draft.payload["body"].replace("原来，", "")
        orchestrator.save_human_edit(
            content.id,
            draft.payload["title"],
            f"<p>{edited_body}</p>",
            edited_body,
        )
        reviews = await orchestrator.run_quality_reviews(content.id)
        assert len(reviews) == 5
        citation = next(item for item in reviews if item.artifact_type == "CitationVerificationReport")
        assert citation.payload["check_status"] == "not_needed"
        orchestrator.submit_review(content.id)
        assert content.status == "pending_review"
        assert db.scalar(select(DiffMemoryCandidate)) is not None
        exported = export_package(db, content)
        assert (Path(exported["folder"]) / "封面.png").is_file()


@pytest.mark.asyncio
async def test_plan_generation_accepts_model_sequences_returned_as_chinese_text():
    with SessionLocal() as db:
        content = Content(theme="主动提出新的关系边界", emotion="忐忑")
        db.add(content)
        db.commit()
        plans = await WorkflowOrchestrator(db, llm=StringSequenceProvider()).generate_plans(content.id)
        first = plans.payload["plans"][0]
        assert first["narrative_structure"] == ["单线递进"]
        assert first["scenes"] == ["公园长椅", "末班公交"]
        assert first["emotion_curve"] == ["克制"]


@pytest.mark.asyncio
async def test_draft_generation_normalizes_common_model_list_shapes():
    with SessionLocal() as db:
        content = Content(theme="主动提出新的关系边界", emotion="忐忑")
        db.add(content)
        db.commit()
        orchestrator = WorkflowOrchestrator(db, llm=LooseDraftProvider())
        await orchestrator.generate_plans(content.id)
        orchestrator.select_plan(content.id, "p1")
        detail = await orchestrator.generate_detail_question(content.id)
        orchestrator.select_detail(content.id, "fictional", detail.payload["virtual_details"][0])

        draft = await orchestrator.generate_draft(content.id)

        assert draft.prompt_version == "2.3.0"
        assert draft.payload["alternate_titles"] == ["我绕开那条街", "城市比我更晚忘记"]
        assert draft.payload["core_tags"] == ["情感随笔", "女性成长"]
        assert draft.payload["cultural_references"] == [{"text": "伍尔夫《一间自己的房间》"}]
        assert draft.payload["fictionality_notes"] == ["便利店场景为虚构"]
        assert content.current_step == "human_edit"


def test_validation_error_uses_parent_field_name_instead_of_list_index():
    invalid = {
        "title": "标题",
        "body": "正文",
        "alternate_titles": ["备选一", "备选二"],
        "core_tags": [],
        "trend_tags": [],
        "long_tail_tags": [],
        "pinned_comment": "评论",
        "cover_copy": "封面",
        "recommended_publish_time": "21:30",
        "recommendation_basis": "通用时段",
        "recommendation_confidence": "低",
        "cultural_references": [0],
        "fictionality_notes": [],
    }
    with pytest.raises(ValidationError) as caught:
        EssayDraft.model_validate(invalid)
    message = friendly_workflow_validation_error(caught.value)
    assert "文化引用" in message
    assert "“0”" not in message


def test_style_review_accepts_one_extra_model_wrapper():
    review = StyleReview.model_validate(
        {
            "style_review": {
                "dimensions": [{"name": "具体性", "rating": "高", "evidence": "有日记本细节"}],
                "issues": [],
                "strengths": "场景明确",
                "summary": "整体符合编辑宪法",
            }
        }
    )
    assert review.dimensions[0].name == "具体性"
    assert review.strengths == ["场景明确"]


def test_style_review_accepts_chinese_top_level_field_names():
    review = StyleReview.model_validate(
        {
            "评价维度": [{"name": "自我觉察", "rating": "中", "evidence": "有矛盾坦露"}],
            "问题列表": [],
            "优势": ["保留停顿"],
            "总结": "可以继续人工修改",
        }
    )
    assert review.summary == "可以继续人工修改"
    assert review.issues == []


def test_ai_tone_review_normalizes_preserved_roughness_text():
    review = AIToneReview.model_validate(
        {
            "ai_tone_review": {
                "issues": [],
                "revised_body": "保留原文，只调整一个机械转折。",
                "preserved_roughness": "保留口语停顿和不规整短句",
                "summary": "模板化风险较低",
            }
        }
    )
    assert review.preserved_roughness == ["保留口语停顿和不规整短句"]
    assert review.summary == "模板化风险较低"


def test_risk_report_accepts_one_extra_model_wrapper():
    report = RiskReport.model_validate(
        {
            "risk_review": {
                "risks": [],
                "blocks_submission": False,
                "summary": "没有需要阻止提交的明确高风险",
            }
        }
    )
    assert report.risks == []
    assert report.blocks_submission is False


@pytest.mark.asyncio
async def test_failed_workflow_step_keeps_history_and_allows_a_new_attempt():
    with SessionLocal() as db:
        content = Content(theme="失败后可以重试", emotion="克制")
        db.add(content)
        db.commit()
        provider = FailOncePlanProvider()
        orchestrator = WorkflowOrchestrator(db, llm=provider)

        with pytest.raises(WorkflowError, match="请重新点击当前步骤"):
            await orchestrator.generate_plans(content.id)
        plans = await orchestrator.generate_plans(content.id)

        steps = list(
            db.scalars(
                select(WorkflowStep)
                .where(WorkflowStep.content_id == content.id, WorkflowStep.step_id == "plan_generation")
                .order_by(WorkflowStep.attempt_no)
            )
        )
        assert len(plans.payload["plans"]) == 3
        assert [(step.attempt_no, step.status) for step in steps] == [(1, "failed"), (2, "success")]
        assert steps[0].input_hash == steps[1].input_hash
        assert steps[0].idempotency_key != steps[1].idempotency_key
        assert (steps[0].input_tokens, steps[0].output_tokens) == (11, 7)
        usage = list(
            db.scalars(
                select(ApiUsage).where(ApiUsage.content_id == content.id, ApiUsage.task_type == "plan_generation")
            )
        )
        assert len(usage) == 2


@pytest.mark.asyncio
async def test_unverified_active_citation_is_reflected_in_risk_gate():
    with SessionLocal() as db:
        content = Content(theme="读完一本书后的迟钝", emotion="克制")
        db.add(content)
        db.commit()
        orchestrator = WorkflowOrchestrator(
            db,
            llm=FakeProvider(cultural_references=[{"work": "活着", "author": "余华"}]),
            search_configured=False,
        )
        await orchestrator.generate_plans(content.id)
        orchestrator.select_plan(content.id, "p1")
        detail = await orchestrator.generate_detail_question(content.id)
        orchestrator.select_detail(content.id, "fictional", detail.payload["virtual_details"][0])
        draft = await orchestrator.generate_draft(content.id)
        edited_body = f"{draft.payload['body']}\n我读《活着》时，想起很多迟到的告别。"
        orchestrator.save_human_edit(content.id, draft.payload["title"], f"<p>{edited_body}</p>", edited_body)

        reviews = await orchestrator.run_quality_reviews(content.id)
        citation = next(item for item in reviews if item.artifact_type == "CitationVerificationReport")
        risk = next(item for item in reviews if item.artifact_type == "RiskReport")

        assert citation.payload["items"][0]["status"] == "unverified"
        assert risk.payload["blocks_submission"] is True
        assert any(item["category"] == "文化引用" for item in risk.payload["risks"])
        with pytest.raises(WorkflowError, match="高风险项"):
            orchestrator.submit_review(content.id)
