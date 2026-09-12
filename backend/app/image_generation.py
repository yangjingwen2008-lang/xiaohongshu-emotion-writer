"""Generated cover candidates, isolated from the currently selected cover."""
import hashlib
import logging
from contextlib import contextmanager
from datetime import timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from .cover_studio import FORMATS, save_cover_upload, validate_cover_image
from .image_provider import ImageProviderError, ImageResult
from .models import ApiUsage, Artifact, Content
from .orchestrator import WorkflowError


CANDIDATE_TYPE = "GeneratedCoverImage"
_active: set[str] = set()
_mutex = Lock()


def generation_busy(content_id: str) -> bool:
    with _mutex:
        return content_id in _active


@contextmanager
def generation_slot(content_id: str):
    # The local application runs one uvicorn worker; the guard also covers reloads
    # of the browser, concurrent tabs, and independently issued API requests.
    with _mutex:
        if content_id in _active:
            raise ImageProviderError("这篇文章正在生成图片，请等待完成，未重复调用服务。", 409)
        _active.add(content_id)
    try:
        yield
    finally:
        with _mutex:
            _active.discard(content_id)


def candidate_view(item: Artifact) -> dict:
    prefix = f"/api/contents/{item.content_id}/cover/candidates/{item.id}/image"
    created_at = item.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {"id": item.id, **{k: v for k, v in item.payload.items() if k != "filename"},
            "created_at": created_at, "preview_url": prefix, "download_url": f"{prefix}?download=true"}


def list_candidates(db: Session, content: Content) -> list[dict]:
    return [candidate_view(item) for item in db.scalars(select(Artifact).where(
        Artifact.content_id == content.id, Artifact.artifact_type == CANDIDATE_TYPE
    ).order_by(Artifact.created_at.desc()))]


def get_candidate(db: Session, content: Content, candidate_id: str) -> Artifact:
    item = db.get(Artifact, candidate_id)
    if not item or item.content_id != content.id or item.artifact_type != CANDIDATE_TYPE:
        raise ImageProviderError("候选图片不存在。", 404)
    return item


def candidate_path(content: Content, item: Artifact, *, must_exist: bool = True) -> Path:
    root = (settings.upload_dir / content.id / "generated").resolve()
    target = (root / item.payload.get("filename", "")).resolve()
    if target.parent != root or (must_exist and not target.is_file()):
        raise ImageProviderError("候选图片文件不存在或路径无效。", 404)
    return target


def save_candidate(db: Session, content: Content, result: ImageResult, prompt: str, size: str | None) -> dict:
    try:
        metadata = validate_cover_image(result.data)
    except WorkflowError as exc:
        raise ImageProviderError(f"生成图片未通过校验：{exc}") from exc
    root = (settings.upload_dir / content.id / "generated").resolve()
    filename = f"{uuid4().hex}{FORMATS[metadata['format']]}"
    target = root / filename
    try:
        root.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.data)
        item = Artifact(content_id=content.id, artifact_type=CANDIDATE_TYPE, step_id="cover_and_export",
                        payload={**metadata, "filename": filename, "prompt": prompt, "model": result.model,
                                 "requested_size": size, "size_bytes": len(result.data)},
                        source_artifact_ids=[], content_hash=hashlib.sha256(result.data).hexdigest(), confirmed=False)
        db.add(item)
        usage = result.usage or {}
        counts = {key: usage.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")}
        counts = {key: value if type(value) is int and 0 <= value <= 2_147_483_647 else 0 for key, value in counts.items()}
        db.add(ApiUsage(content_id=content.id, provider="image", task_type="image_generation",
                        model_name=result.model, **counts, estimated_cost_usd=None))
        db.commit()
    except (OSError, SQLAlchemyError) as exc:
        db.rollback()
        try:
            target.unlink(missing_ok=True)
        except OSError:
            logging.getLogger(__name__).warning("未能清理保存失败的候选图片文件。")
        raise ImageProviderError("图片已生成，但本地保存失败；请检查磁盘和数据库，上游可能已计费。", 500) from exc
    return candidate_view(item)


def use_candidate(db: Session, content: Content, candidate_id: str) -> Artifact:
    item = get_candidate(db, content, candidate_id)
    path = candidate_path(content, item)
    return save_cover_upload(db, content, f"AI生成{path.suffix}", path.read_bytes(), source_artifact_id=item.id)


def delete_candidate(db: Session, content: Content, candidate_id: str) -> None:
    item = get_candidate(db, content, candidate_id)
    # A selected cover is a separate validated copy, so deleting a candidate is safe.
    path = candidate_path(content, item, must_exist=False)
    path.unlink(missing_ok=True)
    db.delete(item)
    db.commit()
