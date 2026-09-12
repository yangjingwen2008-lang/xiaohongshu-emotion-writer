from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import AnalyticsSnapshot, Artifact, Content, ContentVersion, Publication


class AnalyticsError(RuntimeError):
    pass


ALLOWED_NOTE_HOSTS = ("xiaohongshu.com", "xhslink.com", "xhsurl.com")


def _validated_note_url(value: str) -> str:
    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise AnalyticsError("请输入完整的小红书笔记链接")
    if not any(hostname == host or hostname.endswith(f".{host}") for host in ALLOWED_NOTE_HOSTS):
        raise AnalyticsError("链接域名不是可识别的小红书公开链接")
    return value.strip()


def _latest_version(db: Session, content_id: str) -> ContentVersion:
    version = db.scalar(
        select(ContentVersion)
        .where(ContentVersion.content_id == content_id)
        .order_by(ContentVersion.version.desc())
        .limit(1)
    )
    if not version:
        raise AnalyticsError("没有可记录为已发布的正文版本")
    return version


def _latest_artifact(db: Session, content_id: str, artifact_type: str) -> Artifact | None:
    return db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content_id, Artifact.artifact_type == artifact_type)
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )


def record_publication(
    db: Session,
    content_id: str,
    note_url: str,
    published_at: datetime | None,
) -> Publication:
    content = db.get(Content, content_id)
    if not content:
        raise AnalyticsError("文章不存在")
    if content.status != "pending_review":
        raise AnalyticsError("只有已经人工提交待审核的文章才能记录发布")
    if db.scalar(select(Publication).where(Publication.content_id == content_id)):
        raise AnalyticsError("这篇文章已经记录过发布链接")

    version = _latest_version(db, content_id)
    draft = _latest_artifact(db, content_id, "EssayDraft")
    cover = _latest_artifact(db, content_id, "CoverPNG")
    draft_payload = draft.payload if draft else {}
    tags = [
        tag.lstrip("#")
        for group in ("core_tags", "trend_tags", "long_tail_tags")
        for tag in draft_payload.get(group, [])
    ]
    publication = Publication(
        content_id=content.id,
        note_url=_validated_note_url(note_url),
        published_at=published_at or datetime.now(timezone.utc),
        final_title=version.title,
        final_version_id=version.id,
        final_tags=tags,
        final_cover_path=(cover.payload.get("path") if cover else None),
        recommended_publish_time=draft_payload.get("recommended_publish_time"),
    )
    content.status = "published"
    content.current_step = "publication_record"
    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication


def _calculate_rates(metrics: dict) -> dict:
    views = metrics.get("views")
    impressions = metrics.get("impressions")
    engagement_denominator = impressions if isinstance(impressions, (int, float)) and impressions > 0 else views
    rates: dict[str, float | str] = {}
    if isinstance(engagement_denominator, (int, float)) and engagement_denominator > 0:
        rates["engagement_denominator"] = "impressions" if engagement_denominator == impressions else "views"
        for metric, rate_name in (
            ("likes", "like_rate"),
            ("favorites", "favorite_rate"),
            ("comments", "comment_rate"),
            ("shares", "share_rate"),
        ):
            value = metrics.get(metric)
            if isinstance(value, (int, float)):
                rates[rate_name] = round(value / engagement_denominator, 6)
    if isinstance(views, (int, float)) and views > 0:
        for metric, rate_name in (
            ("profile_visits", "profile_visit_rate"),
            ("new_followers", "follower_conversion_rate"),
        ):
            value = metrics.get(metric)
            if isinstance(value, (int, float)):
                rates[rate_name] = round(value / views, 6)
    return rates


def save_snapshot(
    db: Session,
    publication_id: str,
    day_offset: int,
    metrics: dict,
    note: str | None,
    source_type: str = "manual",
    *,
    commit: bool = True,
) -> AnalyticsSnapshot:
    publication = db.get(Publication, publication_id)
    if not publication:
        raise AnalyticsError("发布记录不存在")
    cleaned = {key: value for key, value in metrics.items() if value is not None and key != "extra_metrics"}
    cleaned.update(metrics.get("extra_metrics") or {})
    if not cleaned:
        raise AnalyticsError("至少填写一项真实数据")
    snapshot = db.scalar(
        select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.publication_id == publication_id,
            AnalyticsSnapshot.day_offset == day_offset,
        )
    )
    if snapshot:
        snapshot.metrics = cleaned
        snapshot.calculated_rates = _calculate_rates(cleaned)
        snapshot.note = note
        snapshot.source_type = source_type
        snapshot.captured_at = datetime.now(timezone.utc)
    else:
        snapshot = AnalyticsSnapshot(
            publication_id=publication_id,
            day_offset=day_offset,
            metrics=cleaned,
            calculated_rates=_calculate_rates(cleaned),
            source_type=source_type,
            note=note,
        )
        db.add(snapshot)
    if commit:
        db.commit()
        db.refresh(snapshot)
    else:
        db.flush()
    return snapshot


def list_publications(db: Session) -> list[Publication]:
    return list(
        db.scalars(
            select(Publication)
            .options(selectinload(Publication.snapshots))
            .order_by(Publication.published_at.desc())
        )
    )


def get_publication(db: Session, publication_id: str) -> Publication:
    publication = db.scalar(
        select(Publication)
        .options(selectinload(Publication.snapshots))
        .where(Publication.id == publication_id)
    )
    if not publication:
        raise AnalyticsError("发布记录不存在")
    return publication


def due_snapshots(db: Session, now: datetime | None = None) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    due: list[dict] = []
    for publication in list_publications(db):
        published_at = publication.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        recorded = {snapshot.day_offset for snapshot in publication.snapshots}
        for day_offset in (1, 3, 7):
            due_at = published_at + timedelta(days=day_offset)
            if day_offset not in recorded and current >= due_at:
                due.append(
                    {
                        "publication_id": publication.id,
                        "content_id": publication.content_id,
                        "final_title": publication.final_title,
                        "day_offset": day_offset,
                        "due_at": due_at,
                        "overdue_days": max(0, (current.date() - due_at.date()).days),
                    }
                )
    return sorted(due, key=lambda item: (item["due_at"], item["final_title"]))
