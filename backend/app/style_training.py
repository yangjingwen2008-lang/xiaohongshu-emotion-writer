import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .editorial_constitution import current_constitution_payload
from .models import ApiUsage, StyleProfileVersion, StyleTrainingProposal
from .prompt_registry import get_prompt
from .providers import LLMProvider, ProviderError, build_llm_provider
from .schemas import StyleTrainingAnalysis


INITIAL_STYLE_PROFILE = {
    "core_rules": [
        "用具体场景承载抽象情绪",
        "第一人称可以不体面，但必须有自我觉察",
        "女性经验是核心视角，同时避免简单性别对立",
        "不强行成长、释怀或给出标准答案",
        "结尾偏向动作、场景或未回答的问题",
    ],
    "confirmed_training": [],
}


class StyleTrainingError(RuntimeError):
    pass


async def analyze_style(
    db: Session,
    article: str,
    source_type: str,
    llm: LLMProvider | None = None,
) -> StyleTrainingProposal:
    prompt = get_prompt("style_trainer")
    provider = llm or build_llm_provider(db)
    constitution_version, constitution = current_constitution_payload(db)
    try:
        result = await provider.generate_json(
            system_prompt=prompt.system_prompt,
            user_prompt=json.dumps(
                {
                    "reference_article": article,
                    "output_language": "zh-CN",
                    "language_requirements": [
                        "所有面向用户的字符串必须使用简体中文",
                        "JSON 字段名保持约定的英文键名，但字段值不得返回整段英文",
                        "外语参考文章也必须用中文分析，必要的作品名可保留原文",
                    ],
                    "editorial_constitution": {
                        "version": constitution_version,
                        "sections": constitution,
                    },
                },
                ensure_ascii=False,
            ),
            task_type="style_training",
        )
        analysis = StyleTrainingAnalysis.model_validate(result.payload)
    except (ProviderError, ValueError) as exc:
        raise StyleTrainingError(f"风格分析失败：{exc}") from exc

    proposal = StyleTrainingProposal(
        status="pending",
        source_type=source_type,
        source_hash=hashlib.sha256(article.encode("utf-8")).hexdigest(),
        source_char_count=len(article),
        analysis=analysis.model_dump(mode="json"),
        prompt_version=prompt.version,
        editorial_constitution_version=constitution_version,
    )
    db.add(proposal)
    db.add(
        ApiUsage(
            content_id=None,
            provider="deepseek",
            task_type="style_training",
            model_name=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.input_tokens + result.output_tokens,
        )
    )
    db.commit()
    db.refresh(proposal)
    return proposal


def decide_proposal(db: Session, proposal_id: str, confirm: bool) -> StyleTrainingProposal:
    proposal = db.get(StyleTrainingProposal, proposal_id)
    if not proposal:
        raise StyleTrainingError("风格提案不存在")
    if proposal.status != "pending":
        raise StyleTrainingError("该提案已经处理过")
    proposal.status = "confirmed" if confirm else "rejected"
    proposal.decided_at = datetime.now(timezone.utc)
    if confirm:
        latest = db.scalar(select(StyleProfileVersion).order_by(StyleProfileVersion.version.desc()).limit(1))
        rules = deepcopy(latest.rules if latest else INITIAL_STYLE_PROFILE)
        rules.setdefault("confirmed_training", []).append(
            {
                "proposal_id": proposal.id,
                "source_type": proposal.source_type,
                "features": proposal.analysis["features"],
                "preferred_patterns": proposal.analysis["preferred_patterns"],
                "avoid_patterns": proposal.analysis["avoid_patterns"],
                "imagery_tendencies": proposal.analysis["imagery_tendencies"],
                "rhythm_summary": proposal.analysis["rhythm_summary"],
                "ending_summary": proposal.analysis["ending_summary"],
            }
        )
        next_version = (db.scalar(select(func.max(StyleProfileVersion.version))) or 0) + 1
        db.add(
            StyleProfileVersion(
                version=next_version,
                rules=rules,
                source_proposal_id=proposal.id,
                change_type="training",
            )
        )
    db.commit()
    db.refresh(proposal)
    return proposal


def current_profile(db: Session) -> StyleProfileVersion | None:
    return db.scalar(select(StyleProfileVersion).order_by(StyleProfileVersion.version.desc()).limit(1))


def list_profile_versions(db: Session) -> list[StyleProfileVersion]:
    return list(db.scalars(select(StyleProfileVersion).order_by(StyleProfileVersion.version.desc())))


def update_profile(
    db: Session,
    core_rules: list[str],
    manual_preferences: list[str],
    manual_avoid_patterns: list[str],
) -> StyleProfileVersion:
    latest = current_profile(db)
    rules = deepcopy(latest.rules if latest else INITIAL_STYLE_PROFILE)
    rules["core_rules"] = core_rules
    rules["manual_preferences"] = manual_preferences
    rules["manual_avoid_patterns"] = manual_avoid_patterns
    version = StyleProfileVersion(
        version=(db.scalar(select(func.max(StyleProfileVersion.version))) or 0) + 1,
        rules=rules,
        change_type="manual_edit",
        source_version=latest.version if latest else 0,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def rollback_profile(db: Session, target_version: int) -> StyleProfileVersion:
    target = db.scalar(select(StyleProfileVersion).where(StyleProfileVersion.version == target_version))
    if not target:
        raise StyleTrainingError("要回滚的风格档案版本不存在")
    latest = current_profile(db)
    if latest and latest.version == target.version:
        raise StyleTrainingError("当前已经是这个版本")
    restored = StyleProfileVersion(
        version=(db.scalar(select(func.max(StyleProfileVersion.version))) or 0) + 1,
        rules=deepcopy(target.rules),
        change_type="rollback",
        source_version=target.version,
    )
    db.add(restored)
    db.commit()
    db.refresh(restored)
    return restored
