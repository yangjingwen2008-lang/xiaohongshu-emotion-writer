from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Content, ManualTrendSource, TrendCandidate, TrendRefreshRun
from ..schemas import ContentSummary, ConfirmationRequest, ManualTrendSourceCreate, ManualTrendSourceView, TrendCandidateView, TrendRunView
from ..trend_scheduler import TrendSchedulerError, install_schedule, schedule_status, uninstall_schedule
from ..trends import TrendError, TrendService, create_manual_trend_source, use_trend_candidate


router = APIRouter()


@router.get("/trends/candidates", response_model=list[TrendCandidateView])
def list_trend_candidates(db: Session = Depends(get_db)) -> list[TrendCandidate]:
    latest_run = db.scalar(
        select(TrendRefreshRun)
        .where(TrendRefreshRun.status == "completed")
        .order_by(TrendRefreshRun.started_at.desc())
        .limit(1)
    )
    if not latest_run:
        return []
    return list(
        db.scalars(
            select(TrendCandidate)
            .where(TrendCandidate.run_id == latest_run.id)
            .order_by(TrendCandidate.created_at.asc())
            .limit(8)
        )
    )


@router.get("/trends/runs", response_model=list[TrendRunView])
def list_trend_runs(limit: int = 10, db: Session = Depends(get_db)) -> list[TrendRefreshRun]:
    safe_limit = max(1, min(limit, 50))
    return list(
        db.scalars(select(TrendRefreshRun).order_by(TrendRefreshRun.started_at.desc()).limit(safe_limit))
    )


@router.post("/trends/refresh", response_model=TrendRunView)
async def refresh_trends(db: Session = Depends(get_db)) -> TrendRefreshRun:
    try:
        return await TrendService(db).refresh(trigger="manual")
    except TrendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/trends/manual-sources", response_model=list[ManualTrendSourceView])
def list_manual_trend_sources(db: Session = Depends(get_db)) -> list[ManualTrendSource]:
    return list(
        db.scalars(select(ManualTrendSource).order_by(ManualTrendSource.created_at.desc()).limit(100))
    )


@router.post("/trends/manual-sources", response_model=ManualTrendSourceView)
def add_manual_trend_source(
    payload: ManualTrendSourceCreate,
    db: Session = Depends(get_db),
) -> ManualTrendSource:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认后才能保存手工热点来源")
    value = payload.source_value.strip()
    if payload.source_type == "url":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="链接必须是有效的 http 或 https 地址")
    return create_manual_trend_source(
        db,
        source_type=payload.source_type,
        label=payload.label,
        source_value=value,
    )


@router.post("/trends/candidates/{candidate_id}/use", response_model=ContentSummary)
def create_content_from_trend(
    candidate_id: str,
    payload: ConfirmationRequest,
    db: Session = Depends(get_db),
) -> Content:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要确认后才能用热点候选创建文章")
    try:
        return use_trend_candidate(db, candidate_id)
    except TrendError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trends/schedule/status")
def get_trend_schedule_status() -> dict:
    return schedule_status()


@router.post("/trends/schedule/install")
def install_trend_schedule(payload: ConfirmationRequest) -> dict:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要确认后才能创建 Windows 计划任务")
    try:
        return install_schedule()
    except TrendSchedulerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/trends/schedule/uninstall")
def uninstall_trend_schedule(payload: ConfirmationRequest) -> dict:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要确认后才能删除 Windows 计划任务")
    try:
        return uninstall_schedule()
    except TrendSchedulerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
