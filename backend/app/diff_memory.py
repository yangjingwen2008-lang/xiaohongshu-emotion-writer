import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Content, ContentVersion, DiffMemoryCandidate, StyleProfileVersion
from .style_training import INITIAL_STYLE_PROFILE, current_profile


AI_TONE_PHRASES = (
    "原来",
    "后来才明白",
    "真正的",
    "我终于明白",
    "某种意义上",
    "归根结底",
)


class DiffMemoryError(RuntimeError):
    pass


def _excerpt(text: str, token: str | None = None, limit: int = 140) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return "（空）"
    if token and token in compact:
        center = compact.index(token)
        start = max(0, center - limit // 2)
        return compact[start:start + limit]
    return compact[:limit]


def _paragraph_lengths(text: str) -> list[int]:
    return [len(item.strip()) for item in re.split(r"\n+", text) if item.strip()]


def _ending_kind(text: str) -> str:
    tail = text.strip()[-120:]
    if tail.endswith(("？", "?")):
        return "未回答的问题"
    if any(word in tail for word in ("走", "停", "看", "关", "放", "回", "离开", "抱", "坐", "站")):
        return "动作或场景停顿"
    return "克制的开放式停顿"


def _reference_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if 2 <= len(value.strip()) <= 80 else []
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_reference_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_reference_strings(item))
        return result
    return []


def _observations(initial: ContentVersion, human: ContentVersion) -> list[dict[str, Any]]:
    before = initial.body_text
    after = human.body_text
    observations: list[dict[str, Any]] = []

    for phrase in AI_TONE_PHRASES:
        before_count = before.count(phrase)
        after_count = after.count(phrase)
        if before_count > after_count:
            observations.append(
                {
                    "pattern_type": "deleted_phrase",
                    "rule_text": f"减少使用“{phrase}”，优先保留具体经验",
                    "before_excerpt": _excerpt(before, phrase),
                    "after_excerpt": _excerpt(after),
                    "metrics": {"before_count": before_count, "after_count": after_count},
                }
            )

    before_lengths = _paragraph_lengths(before)
    after_lengths = _paragraph_lengths(after)
    before_average = sum(before_lengths) / len(before_lengths) if before_lengths else 0
    after_average = sum(after_lengths) / len(after_lengths) if after_lengths else 0
    if before_average >= 80 and after_average <= before_average * 0.8:
        observations.append(
            {
                "pattern_type": "shortened_paragraph",
                "rule_text": "缩短过长段落，保留更明显的停顿和呼吸",
                "before_excerpt": _excerpt(before),
                "after_excerpt": _excerpt(after),
                "metrics": {
                    "before_average_length": round(before_average, 1),
                    "after_average_length": round(after_average, 1),
                },
            }
        )

    opening_similarity = SequenceMatcher(None, before[:160], after[:160]).ratio()
    if opening_similarity >= 0.72 and len(after.strip()) >= 120:
        observations.append(
            {
                "pattern_type": "preserved_opening",
                "rule_text": "保留以具体场景或动作进入正文的开头",
                "before_excerpt": _excerpt(before[:180]),
                "after_excerpt": _excerpt(after[:180]),
                "metrics": {"opening_similarity": round(opening_similarity, 3)},
            }
        )

    ending_similarity = SequenceMatcher(None, before[-180:], after[-180:]).ratio()
    if ending_similarity < 0.55 and len(after.strip()) >= 120:
        kind = _ending_kind(after)
        observations.append(
            {
                "pattern_type": "ending_change",
                "rule_text": f"结尾更偏向{kind}，避免总结中心思想",
                "before_excerpt": _excerpt(before[-180:]),
                "after_excerpt": _excerpt(after[-180:]),
                "metrics": {"ending_similarity": round(ending_similarity, 3), "ending_kind": kind},
            }
        )

    references = list(
        dict.fromkeys(_reference_strings((initial.metadata_json or {}).get("cultural_references", [])))
    )
    removed_references = [item for item in references if item in before and item not in after]
    if removed_references:
        observations.append(
            {
                "pattern_type": "removed_citation",
                "rule_text": "删除与正文关系不够紧密的文化引用",
                "before_excerpt": _excerpt(before, removed_references[0]),
                "after_excerpt": _excerpt(after),
                "metrics": {"removed_references": removed_references[:5]},
            }
        )
    return observations


def analyze_human_revision(
    db: Session,
    content: Content,
    human_version: ContentVersion,
) -> list[DiffMemoryCandidate]:
    initial = db.scalar(
        select(ContentVersion)
        .where(
            ContentVersion.content_id == content.id,
            ContentVersion.kind == "initial_draft",
        )
        .order_by(ContentVersion.version.asc())
        .limit(1)
    )
    if not initial or initial.id == human_version.id:
        return []

    candidates: list[DiffMemoryCandidate] = []
    now = datetime.now(timezone.utc)
    for observation in _observations(initial, human_version):
        rule_hash = hashlib.sha256(observation["rule_text"].encode("utf-8")).hexdigest()
        candidate = db.scalar(
            select(DiffMemoryCandidate).where(DiffMemoryCandidate.rule_hash == rule_hash)
        )
        if not candidate:
            candidate = DiffMemoryCandidate(
                pattern_type=observation["pattern_type"],
                rule_text=observation["rule_text"],
                rule_hash=rule_hash,
                evidence=[],
            )
            db.add(candidate)
            db.flush()

        evidence = list(candidate.evidence or [])
        item = {
            "content_id": content.id,
            "content_title": human_version.title,
            "initial_version_id": initial.id,
            "human_version_id": human_version.id,
            "before_excerpt": observation["before_excerpt"],
            "after_excerpt": observation["after_excerpt"],
            "metrics": observation["metrics"],
            "observed_at": now.isoformat(),
        }
        existing_index = next(
            (index for index, current in enumerate(evidence) if current.get("content_id") == content.id),
            None,
        )
        if existing_index is None:
            evidence.append(item)
        else:
            evidence[existing_index] = item
        candidate.evidence = evidence
        candidate.occurrence_count = len(evidence)
        candidate.last_observed_at = now
        candidates.append(candidate)
    return candidates


def list_diff_candidates(db: Session) -> list[DiffMemoryCandidate]:
    return list(
        db.scalars(
            select(DiffMemoryCandidate)
            .order_by(
                case(
                    (DiffMemoryCandidate.status == "pending", 0),
                    (DiffMemoryCandidate.status == "confirmed", 1),
                    else_=2,
                ),
                DiffMemoryCandidate.last_observed_at.desc(),
            )
        )
    )


def decide_diff_candidate(
    db: Session,
    candidate_id: str,
    confirm: bool,
) -> DiffMemoryCandidate:
    candidate = db.get(DiffMemoryCandidate, candidate_id)
    if not candidate:
        raise DiffMemoryError("修改差异候选不存在")
    if candidate.status != "pending":
        raise DiffMemoryError("该候选已经处理过")
    candidate.status = "confirmed" if confirm else "rejected"
    candidate.decided_at = datetime.now(timezone.utc)

    if confirm:
        latest = current_profile(db)
        rules = deepcopy(latest.rules if latest else INITIAL_STYLE_PROFILE)
        confirmed = rules.setdefault("confirmed_diff_memory", [])
        confirmed.append(
            {
                "candidate_id": candidate.id,
                "pattern_type": candidate.pattern_type,
                "rule_text": candidate.rule_text,
                "occurrence_count_at_confirmation": candidate.occurrence_count,
            }
        )
        version = StyleProfileVersion(
            version=(db.scalar(select(func.max(StyleProfileVersion.version))) or 0) + 1,
            rules=rules,
            source_diff_candidate_id=candidate.id,
            change_type="diff_memory",
            source_version=latest.version if latest else 0,
        )
        db.add(version)
        db.flush()
        candidate.profile_version_id = version.id
    db.commit()
    db.refresh(candidate)
    return candidate
