from typing import Any
import json

import pytest

from backend.app.database import Base, SessionLocal, engine
from backend.app.providers import ProviderResult
from backend.app.style_training import (
    StyleTrainingError,
    analyze_style,
    current_profile,
    decide_proposal,
    rollback_profile,
    update_profile,
)


class FakeStyleProvider:
    async def generate_json(
        self, *, system_prompt: str, user_prompt: str, task_type: str
    ) -> ProviderResult:
        assert task_type == "style_training"
        training_input = json.loads(user_prompt)
        assert training_input["editorial_constitution"]["version"] == 0
        assert training_input["reference_article"]
        assert training_input["output_language"] == "zh-CN"
        features: list[dict[str, Any]] = [
            {
                "dimension": f"风格维度{index}",
                "observation": f"第{index}项观察使用具体场景承载情绪。",
                "preference": f"第{index}项偏好保留自然、不规整的中文表达。",
                "imitation_risk": "低风险，仅提取抽象写法。",
            }
            for index in range(1, 6)
        ]
        return ProviderResult(
            payload={
                "features": features,
                "preferred_patterns": ["用具体生活场景承载抽象情绪"],
                "avoid_patterns": ["避免模板化总结和强行治愈"],
                "imagery_tendencies": ["夜晚城市中的微小日常物件"],
                "rhythm_summary": "长短句自然交替，并保留口语停顿。",
                "ending_summary": "以没有解决的动作或场景收尾。",
                "ai_tone_risks": ["排比过于整齐时容易出现模型腔"],
                "test_text": "这是一段完全原创的中文测试短文。窗外的灯灭了两盏，我还坐在桌边，没有急着替这个夜晚找答案。杯底剩下一点凉水，楼道里有人轻轻关门，声音很快又被安静吞回去。我把没有发出的消息留在输入框里，起身去关窗。风停了，窗帘还晃了几下，像一句没有说完的话。",
                "privacy_note": "只保留抽象风格特征，不保存参考文章原文。",
            },
            model="fake-style-model",
            input_tokens=30,
            output_tokens=40,
        )


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.mark.asyncio
async def test_style_training_keeps_only_abstract_features_and_versions_profile():
    sentinel = "SOURCE_ARTICLE_SENTINEL_THAT_MUST_NOT_BE_STORED"
    article = (sentinel + " personal prose content. ") * 8

    with SessionLocal() as db:
        proposal = await analyze_style(db, article, "user-pasted", llm=FakeStyleProvider())

        assert proposal.source_char_count == len(article)
        assert proposal.source_hash
        assert proposal.editorial_constitution_version == 0
        assert sentinel not in str(proposal.analysis)
        assert not hasattr(proposal, "article")

        decide_proposal(db, proposal.id, confirm=True)
        profile = current_profile(db)

        assert profile is not None
        assert profile.version == 1
        assert profile.change_type == "training"
        assert profile.rules["confirmed_training"][0]["proposal_id"] == proposal.id
        assert sentinel not in str(profile.rules)

        edited = update_profile(
            db,
            core_rules=["Use concrete scenes", "Keep emotional ambiguity"],
            manual_preferences=["Uneven sentence rhythm"],
            manual_avoid_patterns=["Forced healing"],
        )
        assert edited.version == 2
        assert edited.change_type == "manual_edit"
        assert edited.source_version == 1
        assert edited.rules["confirmed_training"] == profile.rules["confirmed_training"]

        restored = rollback_profile(db, 1)
        assert restored.version == 3
        assert restored.change_type == "rollback"
        assert restored.source_version == 1
        assert restored.rules == profile.rules


class EnglishStyleProvider(FakeStyleProvider):
    async def generate_json(
        self, *, system_prompt: str, user_prompt: str, task_type: str
    ) -> ProviderResult:
        result = await super().generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_type=task_type,
        )
        result.payload["features"][0]["observation"] = "This feedback was returned entirely in English."
        return result


@pytest.mark.asyncio
async def test_style_training_rejects_english_user_facing_feedback():
    article = "这是一篇用于测试风格训练语言边界的中文参考文章。" * 20
    with SessionLocal() as db:
        with pytest.raises(StyleTrainingError, match="简体中文"):
            await analyze_style(db, article, "用户粘贴", llm=EnglishStyleProvider())
