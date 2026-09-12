import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import AnalyticsReport, Artifact, Content, ContentVersion, StyleProfileVersion


FTS_ENGINE_NAME = "sqlite-fts5-char-ngram-v1"
FTS_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS content_search_fts USING fts5(
    version_id UNINDEXED,
    content_id UNINDEXED,
    title_tokens,
    body_tokens,
    metadata_tokens,
    tokenize='unicode61 remove_diacritics 2'
)
"""


def _segments(value: str) -> list[str]:
    return re.findall(r"[\u3400-\u9fff]+|[a-z0-9]+", value.lower())


def ordered_ngrams(value: str, limit: int = 6000) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for segment in _segments(value):
        candidates: Iterable[str]
        if re.fullmatch(r"[a-z0-9]+", segment):
            candidates = (segment,)
        else:
            candidates = (
                segment[index:index + size]
                for size in (3, 2)
                for index in range(max(0, len(segment) - size + 1))
            )
        for token in candidates:
            if token and token not in seen:
                seen.add(token)
                output.append(token)
                if len(output) >= limit:
                    return output
    return output


def ngram_similarity(left: str, right: str) -> float:
    left_tokens = set(ordered_ngrams(left))
    right_tokens = set(ordered_ngrams(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def ensure_fts_table(db: Session) -> None:
    db.execute(text(FTS_TABLE_SQL))


def _metadata_text(content: Content, version: ContentVersion) -> str:
    fingerprint = (version.metadata_json or {}).get("memory_fingerprint", {})
    values = [
        content.theme,
        content.emotion,
        *(fingerprint.get("scenes") or []),
        *(fingerprint.get("structure_tags") or []),
        *(fingerprint.get("imagery") or []),
        fingerprint.get("ending_type") or "",
    ]
    return " ".join(str(value) for value in values if value)


def index_version(db: Session, content: Content, version: ContentVersion) -> None:
    ensure_fts_table(db)
    db.execute(text("DELETE FROM content_search_fts WHERE version_id = :version_id"), {"version_id": version.id})
    db.execute(
        text(
            """
            INSERT INTO content_search_fts(version_id, content_id, title_tokens, body_tokens, metadata_tokens)
            VALUES (:version_id, :content_id, :title_tokens, :body_tokens, :metadata_tokens)
            """
        ),
        {
            "version_id": version.id,
            "content_id": content.id,
            "title_tokens": " ".join(ordered_ngrams(version.title)),
            "body_tokens": " ".join(ordered_ngrams(version.body_text)),
            "metadata_tokens": " ".join(ordered_ngrams(_metadata_text(content, version))),
        },
    )


def rebuild_search_index(db: Session) -> int:
    ensure_fts_table(db)
    db.execute(text("DELETE FROM content_search_fts"))
    versions = list(db.scalars(select(ContentVersion).order_by(ContentVersion.created_at)))
    for version in versions:
        content = db.get(Content, version.content_id)
        if content:
            index_version(db, content, version)
    db.commit()
    return len(versions)


def ensure_search_index_current(db: Session) -> None:
    ensure_fts_table(db)
    indexed_ids = set(db.scalars(text("SELECT version_id FROM content_search_fts")))
    version_ids = set(db.scalars(select(ContentVersion.id)))
    if indexed_ids != version_ids:
        rebuild_search_index(db)
    else:
        db.commit()


def search_versions(
    db: Session,
    query: str,
    exclude_content_id: str | None = None,
    limit: int = 20,
) -> list[ContentVersion]:
    ensure_fts_table(db)
    tokens = ordered_ngrams(query, limit=80)
    if not tokens:
        return []
    match_query = " OR ".join(f'"{token}"' for token in tokens)
    sql = """
        SELECT version_id
        FROM content_search_fts
        WHERE content_search_fts MATCH :match_query
    """
    params: dict[str, Any] = {"match_query": match_query, "limit": limit}
    if exclude_content_id:
        sql += " AND content_id != :exclude_content_id"
        params["exclude_content_id"] = exclude_content_id
    sql += " ORDER BY bm25(content_search_fts) LIMIT :limit"
    version_ids = list(db.scalars(text(sql), params))
    versions = {version.id: version for version in db.scalars(select(ContentVersion).where(ContentVersion.id.in_(version_ids)))}
    return [versions[version_id] for version_id in version_ids if version_id in versions]


def build_memory_fingerprint(db: Session, content: Content, body_text: str) -> dict:
    plans = db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content.id, Artifact.artifact_type == "NarrativePlanSet")
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    selected: dict[str, Any] = {}
    if plans:
        selected = next(
            (plan for plan in plans.payload.get("plans", []) if plan.get("plan_id") == content.selected_plan_id),
            {},
        )
    imagery_candidates = (
        "雨", "海", "路灯", "街道", "书店", "出租屋", "车站", "窗", "夜", "气味", "拥抱", "聊天框", "电影", "异乡"
    )
    tail = body_text.strip()[-120:]
    ending_type = "未回答的问题" if tail.endswith(("？", "?")) else "动作或场景停顿"
    return {
        "scenes": list(dict.fromkeys(selected.get("scenes") or []))[:5],
        "structure_tags": list(dict.fromkeys(selected.get("narrative_structure") or []))[:5],
        "emotion_curve": list(dict.fromkeys(selected.get("emotion_curve") or []))[:5],
        "imagery": [item for item in imagery_candidates if item in body_text][:5],
        "ending_type": ending_type,
    }


def _style_rules(profile: StyleProfileVersion | None) -> list[str]:
    if not profile:
        return []
    rules = profile.rules or {}
    selected = [
        *(
            item.get("rule_text")
            for item in reversed(rules.get("confirmed_diff_memory") or [])
            if item.get("rule_text")
        ),
        *(rules.get("manual_preferences") or []),
        *(f"避免：{item}" for item in (rules.get("manual_avoid_patterns") or [])),
        *(rules.get("core_rules") or []),
    ]
    for training in reversed(rules.get("confirmed_training") or []):
        selected.extend(training.get("preferred_patterns") or [])
        selected.extend(f"避免：{item}" for item in (training.get("avoid_patterns") or []))
    return list(dict.fromkeys(selected))[:8]


def confirmed_analytics_experiments(db: Session, limit: int = 3) -> list[dict[str, Any]]:
    reports = list(
        db.scalars(
            select(AnalyticsReport)
            .where(AnalyticsReport.status == "confirmed")
            .order_by(AnalyticsReport.decided_at.desc(), AnalyticsReport.created_at.desc())
            .limit(20)
        )
    )
    experiments: list[dict[str, Any]] = []
    for report in reports:
        selected = set(report.confirmed_suggestion_ids or [])
        for suggestion in report.payload.get("suggestions", []):
            suggestion_id = suggestion.get("suggestion_id")
            if suggestion_id not in selected:
                continue
            experiments.append(
                {
                    "report_id": report.id,
                    "report_type": report.report_type,
                    "suggestion_id": suggestion_id,
                    "applies_to": suggestion.get("applies_to"),
                    "experiment": suggestion.get("experiment"),
                    "rationale": suggestion.get("rationale"),
                    "confidence": suggestion.get("confidence"),
                    "evidence_snapshot_ids": suggestion.get("evidence_snapshot_ids") or [],
                    "usage_boundary": "可选且可逆的小实验；每篇最多采用一条，不覆盖风格档案",
                }
            )
            if len(experiments) >= limit:
                return experiments
    return experiments


def generation_memory_report(db: Session, content: Content, profile: StyleProfileVersion | None) -> dict:
    plans = db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content.id, Artifact.artifact_type == "NarrativePlanSet")
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    selected: dict[str, Any] = {}
    if plans:
        selected = next(
            (plan for plan in plans.payload.get("plans", []) if plan.get("plan_id") == content.selected_plan_id),
            {},
        )
    query = " ".join(
        str(value)
        for value in (
            content.theme,
            content.emotion,
            selected.get("title"),
            selected.get("core_view"),
            *(selected.get("scenes") or []),
            *(selected.get("narrative_structure") or []),
        )
        if value
    )
    matches = search_versions(db, query, exclude_content_id=content.id, limit=5)
    avoid_history = []
    for version in matches[:5]:
        fingerprint = (version.metadata_json or {}).get("memory_fingerprint", {})
        avoid_history.append(
            {
                "content_id": version.content_id,
                "version_id": version.id,
                "historical_title": version.title,
                "scenes": (fingerprint.get("scenes") or [])[:3],
                "structure_tags": (fingerprint.get("structure_tags") or [])[:3],
                "imagery": (fingerprint.get("imagery") or [])[:3],
                "ending_type": fingerprint.get("ending_type"),
            }
        )
    return {
        "retrieval_engine": FTS_ENGINE_NAME,
        "retrieval_scope": "仅检索本地历史版本的中文字符 n-gram、主题标签和结构指纹；未注入历史正文。复盘记忆只加载用户明确确认的最近 3 条可逆实验，不自动改风格档案",
        "style_rules_used": _style_rules(profile),
        "avoid_history": avoid_history,
        "source_version_ids": [item["version_id"] for item in avoid_history],
        "confirmed_analytics_experiments": confirmed_analytics_experiments(db),
    }
