import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import AnalyticsReport, Publication
from .prompt_registry import get_prompt
from .providers import LLMProvider, ProviderError, record_usage
from .schemas import RetrospectiveReport


class AnalyticsReportError(RuntimeError):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _date_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=timezone.utc),
        datetime.combine(end, time.max, tzinfo=timezone.utc),
    )


def _snapshot_payload(snapshot: Any) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.id,
        "day_offset": snapshot.day_offset,
        "captured_at": _aware(snapshot.captured_at).isoformat(),
        "source_type": snapshot.source_type,
        "metrics": snapshot.metrics,
        "calculated_rates": snapshot.calculated_rates,
        "note": snapshot.note,
    }


def _publication_payload(publication: Publication, snapshots: list[Any]) -> dict[str, Any]:
    return {
        "publication_id": publication.id,
        "published_at": _aware(publication.published_at).isoformat(),
        "final_title": publication.final_title,
        "final_tags": publication.final_tags,
        "recommended_publish_time": publication.recommended_publish_time,
        "snapshots": [_snapshot_payload(item) for item in snapshots],
    }


def _report_input(
    db: Session,
    report_type: str,
    publication_id: str | None,
    period_start: date | None,
    period_end: date | None,
) -> tuple[dict[str, Any], list[str], datetime, datetime, str | None]:
    if report_type == "single":
        if not publication_id:
            raise AnalyticsReportError("单篇复盘必须选择一篇已发布文章")
        publication = db.scalar(
            select(Publication)
            .options(selectinload(Publication.snapshots))
            .where(Publication.id == publication_id)
            .execution_options(populate_existing=True)
        )
        if not publication:
            raise AnalyticsReportError("发布记录不存在")
        snapshots = list(publication.snapshots)
        if not snapshots:
            raise AnalyticsReportError("至少录入一个已确认数据快照后才能生成单篇复盘")
        start = _aware(publication.published_at)
        end = max(_aware(item.captured_at) for item in snapshots)
        snapshot_ids = [item.id for item in snapshots]
        return (
            {
                "report_type": report_type,
                "sample_definition": "一篇文章的已确认第 1/3/7 天数据快照",
                "publications": [_publication_payload(publication, snapshots)],
                "analysis_rules": [
                    "区分相关与因果，不把单篇结果推广为账号规律",
                    "只给可逆的小实验，不自动修改风格档案",
                    "明确保留账号的私人感、具体场景和非模板化表达",
                ],
            },
            snapshot_ids,
            start,
            end,
            publication.id,
        )

    today = datetime.now(timezone.utc).date()
    if period_start is None and period_end is None:
        period_end = today
        period_start = today - timedelta(days=6 if report_type == "weekly" else 29)
    if period_start is None or period_end is None:
        raise AnalyticsReportError("周报或月报必须同时提供开始和结束日期")
    if period_start > period_end:
        raise AnalyticsReportError("复盘开始日期不能晚于结束日期")
    span = (period_end - period_start).days + 1
    limit = 7 if report_type == "weekly" else 31
    if span > limit:
        raise AnalyticsReportError(f"{('周报' if report_type == 'weekly' else '月报')}范围不能超过 {limit} 天")
    start, end = _date_bounds(period_start, period_end)
    publications = list(
        db.scalars(
            select(Publication)
            .options(selectinload(Publication.snapshots))
            .order_by(Publication.published_at)
            .execution_options(populate_existing=True)
        )
    )
    selected: list[tuple[Publication, list[Any]]] = []
    for publication in publications:
        snapshots = [
            item
            for item in publication.snapshots
            if start <= _aware(item.captured_at) <= end
        ]
        if snapshots:
            selected.append((publication, snapshots))
    if not selected:
        raise AnalyticsReportError("这个时间范围内没有已确认数据快照")
    snapshot_ids = [item.id for _, snapshots in selected for item in snapshots]
    return (
        {
            "report_type": report_type,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "sample_definition": "时间范围内实际确认的数据快照；未录入文章不计入样本",
            "publications": [_publication_payload(publication, snapshots) for publication, snapshots in selected],
            "analysis_rules": [
                "先标注文章数和快照数，再判断样本是否足够",
                "只陈述数据支持的相关性，不虚构平台流量原因",
                "建议必须是可逆小实验，不自动修改风格档案或形成流量模板",
                "明确列出应保留的账号审美与私人表达",
            ],
        },
        snapshot_ids,
        start,
        end,
        None,
    )


def _hash_input(prompt_version: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"prompt_version": prompt_version, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def generate_report(
    db: Session,
    provider: LLMProvider,
    report_type: str,
    publication_id: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> AnalyticsReport:
    if report_type not in {"single", "weekly", "monthly"}:
        raise AnalyticsReportError("不支持的复盘类型")
    prompt = get_prompt("analytics_reviewer")
    report_input, snapshot_ids, start, end, linked_publication_id = _report_input(
        db, report_type, publication_id, period_start, period_end
    )
    input_hash = _hash_input(prompt.version, report_input)
    existing = db.scalar(
        select(AnalyticsReport)
        .where(
            AnalyticsReport.input_hash == input_hash,
            AnalyticsReport.status.in_(["generated", "confirmed"]),
        )
        .order_by(AnalyticsReport.created_at.desc())
        .limit(1)
    )
    if existing:
        return existing

    row = AnalyticsReport(
        report_type=report_type,
        publication_id=linked_publication_id,
        period_start=start,
        period_end=end,
        status="running",
        input_snapshot_ids=snapshot_ids,
        input_hash=input_hash,
        prompt_version=prompt.version,
        payload={},
    )
    db.add(row)
    db.flush()
    try:
        result = await provider.generate_json(
            system_prompt=prompt.system_prompt,
            user_prompt=json.dumps(report_input, ensure_ascii=False, separators=(",", ":")),
            task_type=f"analytics_{report_type}",
        )
        validated = RetrospectiveReport.model_validate(result.payload)
        if validated.report_scope != report_type:
            raise AnalyticsReportError("模型返回的复盘范围与请求不一致")
        allowed_snapshot_ids = set(snapshot_ids)
        referenced = {
            snapshot_id
            for item in validated.observations
            for snapshot_id in item.snapshot_ids
        } | {
            snapshot_id
            for item in validated.suggestions
            for snapshot_id in item.evidence_snapshot_ids
        }
        if not referenced.issubset(allowed_snapshot_ids):
            raise AnalyticsReportError("复盘引用了输入范围外的数据快照")
        payload = validated.model_dump(mode="json")
        payload["sample_size"] = len(report_input["publications"])
        row.status = "generated"
        row.model_name = result.model
        row.payload = payload
        row.completed_at = datetime.now(timezone.utc)
        content_id = None
        if linked_publication_id:
            publication = db.get(Publication, linked_publication_id)
            content_id = publication.content_id if publication else None
        record_usage(db, content_id, f"analytics_{report_type}", result)
        db.commit()
        db.refresh(row)
        return row
    except (ProviderError, ValidationError, AnalyticsReportError, ValueError) as exc:
        row.status = "failed"
        row.error_summary = str(exc)[:1000]
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise AnalyticsReportError(str(exc)) from exc


def list_reports(
    db: Session,
    report_type: str | None = None,
    publication_id: str | None = None,
) -> list[AnalyticsReport]:
    statement = select(AnalyticsReport)
    if report_type:
        statement = statement.where(AnalyticsReport.report_type == report_type)
    if publication_id:
        statement = statement.where(AnalyticsReport.publication_id == publication_id)
    return list(db.scalars(statement.order_by(AnalyticsReport.created_at.desc()).limit(100)))


def confirm_report(
    db: Session,
    report_id: str,
    selected_suggestion_ids: list[str],
    note: str | None,
    confirm: bool,
) -> AnalyticsReport:
    if not confirm:
        raise AnalyticsReportError("必须明确确认选中的复盘建议")
    row = db.get(AnalyticsReport, report_id)
    if not row:
        raise AnalyticsReportError("复盘报告不存在")
    if row.status != "generated":
        raise AnalyticsReportError("这份复盘已经处理或尚未生成成功")
    available = {item["suggestion_id"] for item in row.payload.get("suggestions", [])}
    selected = list(dict.fromkeys(selected_suggestion_ids))
    if not selected or not set(selected).issubset(available):
        raise AnalyticsReportError("只能确认报告中存在的建议")
    row.status = "confirmed"
    row.confirmed_suggestion_ids = selected
    row.decision_note = note.strip() if note else None
    row.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def dismiss_report(db: Session, report_id: str, note: str | None, confirm: bool) -> AnalyticsReport:
    if not confirm:
        raise AnalyticsReportError("必须明确确认忽略这份复盘")
    row = db.get(AnalyticsReport, report_id)
    if not row:
        raise AnalyticsReportError("复盘报告不存在")
    if row.status != "generated":
        raise AnalyticsReportError("这份复盘已经处理或尚未生成成功")
    row.status = "dismissed"
    row.confirmed_suggestion_ids = []
    row.decision_note = note.strip() if note else None
    row.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
