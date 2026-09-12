import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..analytics import AnalyticsError, save_snapshot
from ..comments import CommentError, save_comments
from ..models import ManualTrendSource, OcrRun, Publication, new_id
from ..schemas import ConfirmationRequest, OcrConfirmRequest, OcrRunView, AnalyticsOcrConfirmRequest, CommentOcrConfirmRequest
from ..ocr import MAX_IMAGE_BYTES, OCRProvider, OcrError, parse_analytics_metrics, parse_comment_lines, validate_image
from .dependencies import get_ocr_provider, _delete_ocr_image


router = APIRouter()


@router.get("/ocr/status")
def get_ocr_status(provider: OCRProvider = Depends(get_ocr_provider)) -> dict:
    return {
        **provider.status(),
        "cloud_ocr": False,
        "accepted_types": ["image/png", "image/jpeg"],
        "max_image_bytes": MAX_IMAGE_BYTES,
        "retention": "热点截图仅保留到人工确认或放弃，随后永久删除",
        "retention_policies": {
            "trend": "确认或放弃后永久删除",
            "analytics": "确认后长期本地保留，用户可随时永久删除",
            "comments": "确认或放弃后永久删除；只保存人工核对后的评论文字",
        },
        "requires_human_confirmation": True,
    }


@router.get("/ocr/runs", response_model=list[OcrRunView])
def list_ocr_runs(
    purpose: Literal["trend", "analytics", "comments"] = "trend",
    db: Session = Depends(get_db),
) -> list[OcrRun]:
    return list(
        db.scalars(
            select(OcrRun)
            .where(OcrRun.purpose == purpose)
            .order_by(OcrRun.created_at.desc())
            .limit(50)
        )
    )


@router.post("/ocr/trends", response_model=OcrRunView)
async def recognize_trend_screenshot(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    provider: OCRProvider = Depends(get_ocr_provider),
) -> OcrRun:
    data = await file.read(MAX_IMAGE_BYTES + 1)
    try:
        image = validate_image(data)
    except OcrError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    duplicate = db.scalar(
        select(OcrRun)
        .where(
            OcrRun.purpose == "trend",
            OcrRun.image_hash == image.content_hash,
            OcrRun.status == "pending_confirmation",
        )
        .order_by(OcrRun.created_at.desc())
        .limit(1)
    )
    if duplicate:
        return duplicate
    run = OcrRun(
        id=new_id(),
        purpose="trend",
        status="pending_confirmation",
        provider=provider.name,
        original_filename=Path(file.filename or "screenshot.png").name[:500],
        media_type=image.media_type,
        image_hash=image.content_hash,
        image_size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        retention_policy="delete_after_confirmation",
        lines=[],
        engine_metadata={"local_only": True},
    )
    folder = settings.upload_dir / "ocr" / "pending"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{run.id}{image.suffix}"
    target.write_bytes(data)
    run.image_path = str(target)
    try:
        result = provider.recognize(target)
        run.provider = result.provider
        run.recognized_text = result.text
        run.corrected_text = result.text
        run.lines = result.lines
        run.engine_metadata = result.metadata
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except OcrError as exc:
        _delete_ocr_image(str(target))
        run.status = "failed"
        run.image_path = None
        run.error_summary = str(exc)
        run.recognized_text = None
        run.corrected_text = None
        run.lines = []
        db.add(run)
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=f"截图识别失败：{exc}。原截图已永久删除，未保存为热点来源，也不会自动重试。",
        ) from exc


@router.get("/ocr/runs/{run_id}/image")
def get_ocr_image(run_id: str, db: Session = Depends(get_db)) -> FileResponse:
    run = db.get(OcrRun, run_id)
    allowed = bool(
        run
        and run.image_path
        and (
            (run.purpose == "trend" and run.status == "pending_confirmation")
            or (run.purpose == "analytics" and run.status in {"pending_confirmation", "confirmed"})
            or (run.purpose == "comments" and run.status == "pending_confirmation")
        )
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="待确认截图不存在或已永久删除")
    target = Path(run.image_path)
    root = (settings.upload_dir / "ocr" / "pending").resolve()
    if target.resolve().parent != root:
        raise HTTPException(status_code=404, detail="截图路径无效")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="截图文件已删除")
    return FileResponse(target, media_type=run.media_type, filename=run.original_filename)


@router.post("/ocr/analytics", response_model=OcrRunView)
async def recognize_analytics_screenshot(
    publication_id: str = Form(...),
    day_offset: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    provider: OCRProvider = Depends(get_ocr_provider),
) -> OcrRun:
    if not db.get(Publication, publication_id):
        raise HTTPException(status_code=404, detail="发布记录不存在")
    if day_offset not in {1, 3, 7}:
        raise HTTPException(status_code=400, detail="数据快照只支持发布后第 1、3、7 天")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    try:
        image = validate_image(data)
    except OcrError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    duplicate_candidates = list(db.scalars(
        select(OcrRun)
        .where(
            OcrRun.purpose == "analytics",
            OcrRun.image_hash == image.content_hash,
            OcrRun.status == "pending_confirmation",
        )
        .order_by(OcrRun.created_at.desc())
        .limit(20)
    ))
    duplicate = next(
        (
            item for item in duplicate_candidates
            if item.engine_metadata.get("publication_id") == publication_id
            and item.engine_metadata.get("day_offset") == day_offset
        ),
        None,
    )
    if duplicate:
        return duplicate
    run = OcrRun(
        id=new_id(),
        purpose="analytics",
        status="pending_confirmation",
        provider=provider.name,
        original_filename=Path(file.filename or "analytics.png").name[:500],
        media_type=image.media_type,
        image_hash=image.content_hash,
        image_size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        retention_policy="retain_until_manual_delete",
        lines=[],
        engine_metadata={"local_only": True, "publication_id": publication_id, "day_offset": day_offset},
    )
    folder = settings.upload_dir / "ocr" / "pending"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{run.id}{image.suffix}"
    target.write_bytes(data)
    run.image_path = str(target)
    try:
        result = provider.recognize(target)
        run.provider = result.provider
        run.recognized_text = result.text
        run.corrected_text = result.text
        run.lines = result.lines
        run.engine_metadata = {
            **result.metadata,
            "publication_id": publication_id,
            "day_offset": day_offset,
            "parsed_metrics": parse_analytics_metrics(result.text),
        }
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except OcrError as exc:
        _delete_ocr_image(str(target))
        run.status = "failed"
        run.image_path = None
        run.error_summary = str(exc)
        run.recognized_text = run.corrected_text = None
        run.lines = []
        db.add(run)
        db.commit()
        raise HTTPException(status_code=422, detail=f"数据截图识别失败：{exc}。原截图已永久删除，未写入数据快照，也不会自动重试。") from exc


@router.post("/ocr/runs/{run_id}/confirm-analytics", response_model=OcrRunView)
def confirm_analytics_ocr_run(
    run_id: str,
    payload: AnalyticsOcrConfirmRequest,
    db: Session = Depends(get_db),
) -> OcrRun:
    run = db.get(OcrRun, run_id)
    if not run or run.purpose != "analytics":
        raise HTTPException(status_code=404, detail="数据截图 OCR 记录不存在")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="必须核对文字和指标后才能保存数据快照")
    if run.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="这条数据截图已经处理")
    publication_id = str(run.engine_metadata.get("publication_id", ""))
    day_offset = int(run.engine_metadata.get("day_offset", 0))
    try:
        snapshot = save_snapshot(
            db,
            publication_id,
            day_offset,
            payload.metrics.model_dump(),
            payload.note,
            source_type="ocr_confirmed",
            commit=False,
        )
    except AnalyticsError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run.status = "confirmed"
    run.corrected_text = payload.corrected_text.strip()
    run.linked_analytics_snapshot_id = snapshot.id
    run.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


@router.post("/ocr/comments", response_model=OcrRunView)
async def recognize_comment_screenshot(
    publication_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    provider: OCRProvider = Depends(get_ocr_provider),
) -> OcrRun:
    if not db.get(Publication, publication_id):
        raise HTTPException(status_code=404, detail="发布记录不存在")
    data = await file.read(MAX_IMAGE_BYTES + 1)
    try:
        image = validate_image(data)
    except OcrError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    duplicate_candidates = list(
        db.scalars(
            select(OcrRun)
            .where(
                OcrRun.purpose == "comments",
                OcrRun.image_hash == image.content_hash,
                OcrRun.status == "pending_confirmation",
            )
            .order_by(OcrRun.created_at.desc())
            .limit(20)
        )
    )
    duplicate = next(
        (
            item
            for item in duplicate_candidates
            if item.engine_metadata.get("publication_id") == publication_id
        ),
        None,
    )
    if duplicate:
        return duplicate
    run = OcrRun(
        id=new_id(),
        purpose="comments",
        status="pending_confirmation",
        provider=provider.name,
        original_filename=Path(file.filename or "comments.png").name[:500],
        media_type=image.media_type,
        image_hash=image.content_hash,
        image_size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        retention_policy="delete_after_confirmation",
        lines=[],
        engine_metadata={"local_only": True, "publication_id": publication_id},
    )
    folder = settings.upload_dir / "ocr" / "pending"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{run.id}{image.suffix}"
    target.write_bytes(data)
    run.image_path = str(target)
    try:
        result = provider.recognize(target)
        run.recognized_text = result.text
        run.corrected_text = result.text
        run.lines = result.lines
        run.engine_metadata = {
            **result.metadata,
            "publication_id": publication_id,
            # Windows OCR usually preserves comment boundaries in ``lines`` even
            # when its aggregate text is flattened into one long sentence.
            "suggested_comments": parse_comment_lines("\n".join(result.lines) or result.text),
        }
        db.add(run)
        db.commit()
        db.refresh(run)
        return run
    except OcrError as exc:
        _delete_ocr_image(str(target))
        run.status = "failed"
        run.image_path = None
        run.error_summary = str(exc)[:1000]
        run.deleted_at = datetime.now(timezone.utc)
        db.add(run)
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=f"评论截图识别失败：{exc}。原截图已永久删除，不会自动重试。",
        ) from exc


@router.post("/ocr/runs/{run_id}/confirm-comments", response_model=OcrRunView)
def confirm_comment_ocr_run(
    run_id: str,
    payload: CommentOcrConfirmRequest,
    db: Session = Depends(get_db),
) -> OcrRun:
    run = db.get(OcrRun, run_id)
    if not run or run.purpose != "comments":
        raise HTTPException(status_code=404, detail="评论截图 OCR 记录不存在")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="必须核对评论文字后才能保存")
    if run.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="这张评论截图已经处理")
    publication_id = str(run.engine_metadata.get("publication_id", ""))
    try:
        save_comments(
            db,
            publication_id,
            payload.comments,
            source_type="screenshot",
            source_ocr_run_id=run.id,
            confirm=True,
            commit=False,
        )
        _delete_ocr_image(run.image_path)
    except (OcrError, CommentError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run.status = "confirmed"
    run.image_path = None
    run.recognized_text = None
    run.corrected_text = None
    run.lines = []
    run.confirmed_at = run.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


@router.delete("/ocr/runs/{run_id}/image", response_model=OcrRunView)
def delete_retained_ocr_image(
    run_id: str,
    payload: ConfirmationRequest,
    db: Session = Depends(get_db),
) -> OcrRun:
    run = db.get(OcrRun, run_id)
    if not run or run.purpose != "analytics":
        raise HTTPException(status_code=404, detail="数据截图 OCR 记录不存在")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="必须明确确认后才能永久删除数据截图")
    if not run.image_path:
        raise HTTPException(status_code=409, detail="数据截图已经删除")
    try:
        _delete_ocr_image(run.image_path)
    except OcrError as exc:
        raise HTTPException(status_code=500, detail=f"数据截图永久删除失败：{exc}") from exc
    run.image_path = None
    run.deleted_at = datetime.now(timezone.utc)
    if run.status == "pending_confirmation":
        run.status = "discarded"
        run.recognized_text = run.corrected_text = None
        run.lines = []
    db.commit()
    db.refresh(run)
    return run


@router.post("/ocr/runs/{run_id}/confirm", response_model=OcrRunView)
def confirm_ocr_run(
    run_id: str,
    payload: OcrConfirmRequest,
    db: Session = Depends(get_db),
) -> OcrRun:
    run = db.get(OcrRun, run_id)
    if not run or run.purpose != "trend":
        raise HTTPException(status_code=404, detail="OCR 记录不存在")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="必须明确确认后才能保存 OCR 结果")
    if run.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="这条 OCR 记录已经处理，不能重复确认")
    corrected = payload.corrected_text.strip()
    try:
        _delete_ocr_image(run.image_path)
    except OcrError as exc:
        raise HTTPException(status_code=500, detail=f"截图永久删除失败，未保存来源：{exc}") from exc
    source = ManualTrendSource(
        source_type="screenshot",
        label=payload.label.strip(),
        source_value=corrected,
        content_hash=hashlib.sha256(corrected.encode("utf-8")).hexdigest(),
    )
    db.add(source)
    db.flush()
    run.status = "confirmed"
    run.corrected_text = corrected
    run.image_path = None
    run.linked_manual_trend_source_id = source.id
    run.confirmed_at = run.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


@router.post("/ocr/runs/{run_id}/discard", response_model=OcrRunView)
def discard_ocr_run(run_id: str, payload: ConfirmationRequest, db: Session = Depends(get_db)) -> OcrRun:
    run = db.get(OcrRun, run_id)
    if not run or run.purpose not in {"trend", "comments"}:
        raise HTTPException(status_code=404, detail="OCR 记录不存在")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="必须明确确认后才能永久删除截图")
    if run.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="这条 OCR 记录已经处理")
    try:
        _delete_ocr_image(run.image_path)
    except OcrError as exc:
        raise HTTPException(status_code=500, detail=f"截图永久删除失败：{exc}") from exc
    run.status = "discarded"
    run.image_path = None
    run.recognized_text = None
    run.corrected_text = None
    run.lines = []
    run.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run
