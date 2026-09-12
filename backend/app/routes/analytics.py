from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..analytics import AnalyticsError, due_snapshots, get_publication, list_publications, record_publication, save_snapshot
from ..analytics_reports import AnalyticsReportError, confirm_report, dismiss_report, generate_report, list_reports
from ..models import AnalyticsSnapshot, Publication
from ..providers import LLMProvider
from ..schemas import DueSnapshotView, AnalyticsSnapshotCreateRequest, AnalyticsSnapshotView, AnalyticsReportDecisionRequest, AnalyticsReportDismissRequest, AnalyticsReportGenerateRequest, AnalyticsReportView, PublicationCreateRequest, PublicationView
from .dependencies import get_analytics_llm_provider


router = APIRouter()


@router.post("/contents/{content_id}/publish", response_model=PublicationView)
def publish_content(
    content_id: str, payload: PublicationCreateRequest, db: Session = Depends(get_db)
) -> Publication:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认文章已经手动发布")
    try:
        return record_publication(db, content_id, payload.note_url, payload.published_at)
    except AnalyticsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/publications", response_model=list[PublicationView])
def publications(db: Session = Depends(get_db)) -> list[Publication]:
    return list_publications(db)


@router.get("/publications/due", response_model=list[DueSnapshotView])
def publication_due_snapshots(db: Session = Depends(get_db)) -> list[dict]:
    return due_snapshots(db)


@router.get("/publications/{publication_id}", response_model=PublicationView)
def publication_detail(publication_id: str, db: Session = Depends(get_db)) -> Publication:
    try:
        return get_publication(db, publication_id)
    except AnalyticsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/publications/{publication_id}/snapshots", response_model=AnalyticsSnapshotView)
def create_analytics_snapshot(
    publication_id: str,
    payload: AnalyticsSnapshotCreateRequest,
    db: Session = Depends(get_db),
) -> AnalyticsSnapshot:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认本次数据录入")
    try:
        return save_snapshot(
            db,
            publication_id,
            payload.day_offset,
            payload.metrics.model_dump(mode="json"),
            payload.note,
        )
    except AnalyticsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analytics/reports", response_model=list[AnalyticsReportView])
def analytics_reports(
    report_type: Literal["single", "weekly", "monthly"] | None = None,
    publication_id: str | None = None,
    db: Session = Depends(get_db),
):
    return list_reports(db, report_type, publication_id)


@router.post("/analytics/reports/generate", response_model=AnalyticsReportView)
async def create_analytics_report(
    payload: AnalyticsReportGenerateRequest,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_analytics_llm_provider),
):
    try:
        return await generate_report(
            db,
            provider,
            payload.report_type,
            payload.publication_id,
            payload.period_start,
            payload.period_end,
        )
    except AnalyticsReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analytics/reports/{report_id}/confirm", response_model=AnalyticsReportView)
def confirm_analytics_report(
    report_id: str,
    payload: AnalyticsReportDecisionRequest,
    db: Session = Depends(get_db),
):
    try:
        return confirm_report(
            db,
            report_id,
            payload.selected_suggestion_ids,
            payload.note,
            payload.confirm,
        )
    except AnalyticsReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analytics/reports/{report_id}/dismiss", response_model=AnalyticsReportView)
def dismiss_analytics_report(
    report_id: str,
    payload: AnalyticsReportDismissRequest,
    db: Session = Depends(get_db),
):
    try:
        return dismiss_report(db, report_id, payload.note, payload.confirm)
    except AnalyticsReportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
