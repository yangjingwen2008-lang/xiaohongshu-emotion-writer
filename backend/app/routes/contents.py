import hashlib
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Artifact, Content, ContentVersion, ExternalCheckRun, ManualOriginalitySource
from ..orchestrator import WorkflowError, WorkflowOrchestrator
from ..schemas import ArtifactView, ContentCreate, ContentDetail, ContentSummary, DetailSelection, DraftUpdate, ManualOriginalitySourceCreate, ManualOriginalitySourceView, PlanSelection, SubmitReviewRequest
from .dependencies import _workflow_error


router = APIRouter()


@router.post("/contents", response_model=ContentSummary)
def create_content(payload: ContentCreate, db: Session = Depends(get_db)) -> Content:
    content = Content(**payload.model_dump())
    db.add(content)
    db.commit()
    db.refresh(content)
    return content


@router.get("/contents", response_model=list[ContentSummary])
def list_contents(db: Session = Depends(get_db)) -> list[Content]:
    return list(db.scalars(select(Content).order_by(Content.updated_at.desc())))


@router.get("/contents/{content_id}", response_model=ContentDetail)
def get_content(content_id: str, db: Session = Depends(get_db)) -> ContentDetail:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    artifacts = list(
        db.scalars(select(Artifact).where(Artifact.content_id == content_id).order_by(Artifact.created_at.asc()))
    )
    return ContentDetail(
        **ContentSummary.model_validate(content).model_dump(),
        extra_requirements=content.extra_requirements,
        selected_plan_id=content.selected_plan_id,
        selected_detail=content.selected_detail,
        artifacts=[ArtifactView.model_validate(item) for item in artifacts],
    )


@router.get("/contents/{content_id}/versions")
def list_versions(content_id: str, db: Session = Depends(get_db)) -> list[dict]:
    versions = list(
        db.scalars(
            select(ContentVersion)
            .where(ContentVersion.content_id == content_id)
            .order_by(ContentVersion.version.desc())
        )
    )
    return [
        {
            "id": item.id,
            "version": item.version,
            "kind": item.kind,
            "title": item.title,
            "body_html": item.body_html,
            "body_text": item.body_text,
            "created_at": item.created_at,
        }
        for item in versions
    ]


@router.get(
    "/contents/{content_id}/originality-sources",
    response_model=list[ManualOriginalitySourceView],
)
def list_originality_sources(content_id: str, db: Session = Depends(get_db)) -> list[ManualOriginalitySource]:
    if not db.get(Content, content_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    return list(
        db.scalars(
            select(ManualOriginalitySource)
            .where(ManualOriginalitySource.content_id == content_id)
            .order_by(ManualOriginalitySource.created_at.desc())
        )
    )


@router.post(
    "/contents/{content_id}/originality-sources",
    response_model=ManualOriginalitySourceView,
)
def add_originality_source(
    content_id: str,
    payload: ManualOriginalitySourceCreate,
    db: Session = Depends(get_db),
) -> ManualOriginalitySource:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要确认后才能保存手工补充来源")
    if not db.get(Content, content_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    value = payload.source_value.strip()
    if payload.source_type == "url":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="链接必须是有效的 http 或 https 地址")
    record = ManualOriginalitySource(
        content_id=content_id,
        source_type=payload.source_type,
        label=payload.label.strip(),
        source_value=value,
        content_hash=hashlib.sha256(value.encode("utf-8")).hexdigest(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/contents/{content_id}/external-checks")
def list_external_checks(content_id: str, db: Session = Depends(get_db)) -> list[dict]:
    if not db.get(Content, content_id):
        raise HTTPException(status_code=404, detail="文章不存在")
    records = list(
        db.scalars(
            select(ExternalCheckRun)
            .where(ExternalCheckRun.content_id == content_id)
            .order_by(ExternalCheckRun.started_at.desc())
            .limit(50)
        )
    )
    return [
        {
            "id": item.id,
            "check_type": item.check_type,
            "provider": item.provider,
            "status": item.status,
            "query_count": item.query_count,
            "usage_credits": item.usage_credits,
            "covered_sources": item.covered_sources,
            "unavailable_sources": item.unavailable_sources,
            "result_summary": item.result_summary,
            "request_ids": item.request_ids,
            "error_summary": item.error_summary,
            "started_at": item.started_at,
            "ended_at": item.ended_at,
        }
        for item in records
    ]


@router.post("/contents/{content_id}/workflow/plans", response_model=ArtifactView)
async def generate_plans(content_id: str, db: Session = Depends(get_db)) -> Artifact:
    try:
        return await WorkflowOrchestrator(db).generate_plans(content_id)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/workflow/select-plan", response_model=ArtifactView)
def select_plan(content_id: str, payload: PlanSelection, db: Session = Depends(get_db)) -> Artifact:
    try:
        return WorkflowOrchestrator(db).select_plan(content_id, payload.plan_id)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/workflow/detail-question", response_model=ArtifactView)
async def detail_question(content_id: str, db: Session = Depends(get_db)) -> Artifact:
    try:
        return await WorkflowOrchestrator(db).generate_detail_question(content_id)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/workflow/select-detail", response_model=ArtifactView)
def select_detail(content_id: str, payload: DetailSelection, db: Session = Depends(get_db)) -> Artifact:
    try:
        return WorkflowOrchestrator(db).select_detail(content_id, payload.mode, payload.detail)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/workflow/draft", response_model=ArtifactView)
async def generate_draft(content_id: str, db: Session = Depends(get_db)) -> Artifact:
    try:
        return await WorkflowOrchestrator(db).generate_draft(content_id)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.patch("/contents/{content_id}/draft")
def save_draft(content_id: str, payload: DraftUpdate, db: Session = Depends(get_db)) -> dict:
    try:
        version = WorkflowOrchestrator(db).save_human_edit(
            content_id, payload.title, payload.body_html, payload.body_text
        )
        return {"saved": True, "version": version.version, "version_id": version.id}
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/quality", response_model=list[ArtifactView])
async def run_quality(content_id: str, db: Session = Depends(get_db)) -> list[Artifact]:
    try:
        return await WorkflowOrchestrator(db).run_quality_reviews(content_id)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/submit-review", response_model=ContentSummary)
def submit_review(content_id: str, payload: SubmitReviewRequest, db: Session = Depends(get_db)) -> Content:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认提交")
    try:
        return WorkflowOrchestrator(db).submit_review(content_id)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc
