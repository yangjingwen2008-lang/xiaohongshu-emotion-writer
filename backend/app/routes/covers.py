from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Artifact, Content
from ..orchestrator import WorkflowError
from ..schemas import ArtifactView, CoverRenderRequest, ConfirmationRequest
from ..publishing import export_package
from ..cover_studio import MAX_UPLOAD_BYTES as MAX_COVER_UPLOAD_BYTES, cover_image_path, cover_state, delete_cover_assets, render_cover, save_cover_upload
from .dependencies import _workflow_error
from ..image_provider import ImageGenerateRequest, ImageProviderError, build_image_provider
from ..image_generation import candidate_path, delete_candidate, generation_slot, get_candidate, list_candidates, save_candidate, use_candidate


router = APIRouter()


def _content(db: Session, content_id: str) -> Content:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    return content


@router.post("/contents/{content_id}/cover/generate")
async def generate_cover_image(content_id: str, payload: ImageGenerateRequest, db: Session = Depends(get_db)) -> dict:
    content = _content(db, content_id)
    try:
        with generation_slot(content_id):
            result = await build_image_provider(db).generate(prompt=payload.prompt, size=payload.size)
            return save_candidate(db, content, result, payload.prompt, payload.size)
    except ImageProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="图片已生成，但本地保存失败。请检查可用磁盘空间，可能已产生费用。") from exc


@router.get("/contents/{content_id}/cover/candidates")
def get_cover_candidates(content_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return list_candidates(db, _content(db, content_id))


@router.get("/contents/{content_id}/cover/candidates/{candidate_id}/image")
def get_candidate_image(content_id: str, candidate_id: str, download: bool = False, db: Session = Depends(get_db)) -> FileResponse:
    content = _content(db, content_id)
    try:
        item = get_candidate(db, content, candidate_id)
        path = candidate_path(content, item)
        return FileResponse(path, filename=f"AI封面-{candidate_id}{path.suffix}" if download else None)
    except ImageProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/contents/{content_id}/cover/candidates/{candidate_id}/use", response_model=ArtifactView)
def select_cover_candidate(content_id: str, candidate_id: str, db: Session = Depends(get_db)) -> Artifact:
    try:
        return use_candidate(db, _content(db, content_id), candidate_id)
    except ImageProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="封面文件读写失败，请检查磁盘空间和文件是否存在。") from exc


@router.delete("/contents/{content_id}/cover/candidates/{candidate_id}")
def remove_candidate(content_id: str, candidate_id: str, payload: ConfirmationRequest, db: Session = Depends(get_db)) -> dict:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="请确认删除这张候选图片。")
    try:
        delete_candidate(db, _content(db, content_id), candidate_id)
        return {"deleted": True}
    except ImageProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="候选图片删除失败，请检查文件权限后重试。") from exc


@router.post("/contents/{content_id}/cover/upload", response_model=ArtifactView)
async def upload_cover(content_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> Artifact:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    try:
        return save_cover_upload(db, content, file.filename or "cover.png", await file.read(MAX_COVER_UPLOAD_BYTES + 1))
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/cover/render", response_model=ArtifactView)
def create_cover(content_id: str, payload: CoverRenderRequest, db: Session = Depends(get_db)) -> Artifact:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    try:
        return render_cover(
            db,
            content,
            payload.template,
            payload.copy_text,
            focus_x=payload.focus_x,
            focus_y=payload.focus_y,
            zoom=payload.zoom,
            output_width=payload.output_width,
            output_height=payload.output_height,
        )
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.get("/contents/{content_id}/cover")
def get_cover_state(content_id: str, db: Session = Depends(get_db)) -> dict:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    return cover_state(db, content)


@router.get("/contents/{content_id}/cover/artifacts/{artifact_id}/image")
def get_cover_image(content_id: str, artifact_id: str, db: Session = Depends(get_db)) -> FileResponse:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    try:
        path, media_type = cover_image_path(db, content, artifact_id)
        return FileResponse(path, media_type=media_type, filename=path.name)
    except WorkflowError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/contents/{content_id}/cover")
def delete_cover(content_id: str, payload: ConfirmationRequest, db: Session = Depends(get_db)) -> dict:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="必须明确确认后才能删除封面原图和预览")
    try:
        delete_cover_assets(db, content)
        return {"deleted": True}
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc


@router.post("/contents/{content_id}/export")
def create_export(content_id: str, db: Session = Depends(get_db)) -> dict:
    content = db.get(Content, content_id)
    if not content:
        raise HTTPException(status_code=404, detail="文章不存在")
    try:
        return export_package(db, content)
    except WorkflowError as exc:
        raise _workflow_error(exc) from exc
