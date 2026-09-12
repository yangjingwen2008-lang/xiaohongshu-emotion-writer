import hashlib
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import logging

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ROOT_DIR, settings
from .models import Artifact, Content
from .orchestrator import WorkflowError


MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
MAX_OUTPUT_PIXELS = 6_220_800
FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        ROOT_DIR / "fonts" / "SourceHanSerifSC-Regular.otf",
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _latest_draft(db: Session, content_id: str) -> dict:
    artifact = db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content_id, Artifact.artifact_type == "EssayDraft")
        .order_by(Artifact.version.desc())
        .limit(1)
    )
    if not artifact:
        raise WorkflowError("没有可用于封面的正文草稿")
    return artifact.payload


def _safe_remove(path_value: str | None, roots: set[Path]) -> None:
    if not path_value:
        return
    target = Path(path_value).resolve()
    if target.parent not in roots:
        raise WorkflowError("封面文件路径越界，已停止删除")
    target.unlink(missing_ok=True)


def validate_cover_image(data: bytes) -> dict:
    if not data:
        raise WorkflowError("封面图片为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise WorkflowError("封面原图不能超过 15 MB")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image_format = image.format or ""
            width, height = image.size
            if width * height > MAX_SOURCE_PIXELS:
                raise WorkflowError("封面原图不能超过 4000 万像素")
            preview = image.convert("L")
            preview.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
            sharpness = round(ImageStat.Stat(preview.filter(ImageFilter.FIND_EDGES)).var[0], 2)
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError("上传文件不是有效图片") from exc
    if image_format not in FORMATS:
        raise WorkflowError("只允许 PNG、JPG 或 WebP 图片")
    return {"format": image_format, "width": width, "height": height, "sharpness_score": sharpness}


def save_cover_upload(db: Session, content: Content, filename: str, data: bytes, *, source_artifact_id: str | None = None) -> Artifact:
    metadata = validate_cover_image(data)
    image_format, width, height, sharpness = (metadata[key] for key in ("format", "width", "height", "sharpness_score"))

    target_dir = (settings.upload_dir / content.id).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    existing = list(
        db.scalars(select(Artifact).where(Artifact.content_id == content.id, Artifact.artifact_type == "CoverUpload"))
    )
    next_version = max((item.version for item in existing), default=0) + 1
    rendered = list(db.scalars(select(Artifact).where(Artifact.content_id == content.id, Artifact.artifact_type == "CoverPNG")))
    # Write the new file first. A failed write must leave the current cover intact.
    target = target_dir / f"original-{uuid4().hex}{FORMATS[image_format]}"
    target.write_bytes(data)
    for item in existing + rendered:
        db.delete(item)
    quality_status = "ready" if min(width, height) >= 600 and max(width, height) >= 800 and sharpness >= 20 else "warning"
    artifact = Artifact(
        content_id=content.id,
        artifact_type="CoverUpload",
        step_id="cover_and_export",
        version=next_version,
        payload={
            "path": str(target),
            "original_name": Path(filename).name,
            "format": image_format,
            "width": width,
            "height": height,
            "size_bytes": len(data),
            "sharpness_score": sharpness,
            "quality_status": quality_status,
            "quality_note": "清晰度和分辨率可用" if quality_status == "ready" else "建议使用更清晰或更高分辨率的图片",
            "original_retained": True,
        },
        source_artifact_ids=[source_artifact_id] if source_artifact_id else [],
        content_hash=hashlib.sha256(data).hexdigest(),
        confirmed=True,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    for item in existing + rendered:
        try:
            _safe_remove(item.payload.get("path"), {target_dir, (settings.export_dir / "covers").resolve()})
        except (OSError, WorkflowError):
            logging.getLogger(__name__).warning("新封面已保存，旧封面文件清理未完成。")
    return artifact


def _crop_to_output(source: Image.Image, size: tuple[int, int], focus_x: float, focus_y: float, zoom: float) -> Image.Image:
    output_width, output_height = size
    source_width, source_height = source.size
    target_ratio = output_width / output_height
    if source_width / source_height >= target_ratio:
        crop_height = source_height / zoom
        crop_width = crop_height * target_ratio
    else:
        crop_width = source_width / zoom
        crop_height = crop_width / target_ratio
    center_x, center_y = focus_x * source_width, focus_y * source_height
    left = max(0.0, min(source_width - crop_width, center_x - crop_width / 2))
    top = max(0.0, min(source_height - crop_height, center_y - crop_height / 2))
    box = (round(left), round(top), round(left + crop_width), round(top + crop_height))
    return source.crop(box).resize(size, Image.Resampling.LANCZOS)


def render_cover(
    db: Session,
    content: Content,
    template: str,
    copy: str | None,
    *,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
    zoom: float = 1.0,
    output_width: int = 900,
    output_height: int = 1200,
) -> Artifact:
    if output_width * output_height > MAX_OUTPUT_PIXELS:
        raise WorkflowError("封面输出像素过大，请缩小自定义尺寸")
    draft = _latest_draft(db, content.id)
    text = (copy or draft.get("cover_copy") or content.title or content.theme).strip()[:18]
    upload = db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content.id, Artifact.artifact_type == "CoverUpload")
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    if upload and Path(upload.payload["path"]).is_file():
        with Image.open(upload.payload["path"]) as source:
            canvas = _crop_to_output(source.convert("RGB"), (output_width, output_height), focus_x, focus_y, zoom)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.68 if template != "subtitle" else 0.58)
    else:
        colors = {"whitespace": "#F0EEE7", "magazine": "#D8D2C5", "subtitle": "#30332F"}
        canvas = Image.new("RGB", (output_width, output_height), colors[template])

    draw = ImageDraw.Draw(canvas)
    scale_x, scale_y = output_width / 900, output_height / 1200
    scale = min(scale_x, scale_y)
    point = lambda x, y: (round(x * scale_x), round(y * scale_y))
    font = lambda size: _font(max(12, round(size * scale)))
    ink = "#F7F4EC" if template == "subtitle" or upload else "#282723"
    accent = "#C88870" if template == "subtitle" or upload else "#A45D43"
    if template == "magazine":
        draw.rectangle((*point(65, 70), *point(835, 104)), fill=accent)
        title_font, y = font(72), round(185 * scale_y)
        for part in (text[:9], text[9:]):
            if part:
                draw.text((round(72 * scale_x), y), part, font=title_font, fill=ink)
                y += round(105 * scale_y)
        draw.text(point(72, 1060), "潮湿雨季 / 私人随笔", font=font(25), fill=ink)
    elif template == "subtitle":
        draw.rectangle((*point(0, 860), *point(900, 1200)), fill="#141614")
        subtitle_font = font(52)
        bbox = draw.textbbox((0, 0), text, font=subtitle_font)
        draw.text(((output_width - (bbox[2] - bbox[0])) / 2, round(930 * scale_y)), text, font=subtitle_font, fill=ink)
        draw.text(point(340, 1040), "潮湿雨季", font=font(22), fill=accent)
    else:
        draw.line((*point(70, 110), *point(200, 110)), fill=accent, width=max(2, round(4 * scale)))
        title_font, y = font(64), round(250 * scale_y)
        for part in (text[:8], text[8:]):
            if part:
                draw.text((round(70 * scale_x), y), part, font=title_font, fill=ink)
                y += round(95 * scale_y)
        draw.text(point(70, 1080), "潮湿雨季 · 女性情感随笔", font=font(24), fill=accent)

    target_dir = (settings.export_dir / "covers").resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{content.id}_{template}_{uuid4().hex}.png"
    canvas.save(target, format="PNG", optimize=True)
    last_version = db.scalar(
        select(Artifact.version)
        .where(Artifact.content_id == content.id, Artifact.artifact_type == "CoverPNG")
        .order_by(Artifact.version.desc())
        .limit(1)
    ) or 0
    artifact = Artifact(
        content_id=content.id,
        artifact_type="CoverPNG",
        step_id="cover_and_export",
        version=last_version + 1,
        payload={
            "path": str(target), "template": template, "copy": text,
            "width": output_width, "height": output_height,
            "focus_x": focus_x, "focus_y": focus_y, "zoom": zoom,
            "format": "PNG", "optimized": True,
        },
        source_artifact_ids=[upload.id] if upload else [],
        content_hash=hashlib.sha256(target.read_bytes()).hexdigest(),
        confirmed=True,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def delete_cover_assets(db: Session, content: Content) -> None:
    artifacts = list(
        db.scalars(
            select(Artifact).where(
                Artifact.content_id == content.id,
                Artifact.artifact_type.in_(["CoverUpload", "CoverPNG"]),
            )
        )
    )
    roots = {(settings.upload_dir / content.id).resolve(), (settings.export_dir / "covers").resolve()}
    for artifact in artifacts:
        _safe_remove(artifact.payload.get("path"), roots)
        db.delete(artifact)
    db.commit()


def cover_state(db: Session, content: Content) -> dict:
    from .image_generation import generation_busy, list_candidates
    from .image_provider import image_status
    upload = db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content.id, Artifact.artifact_type == "CoverUpload")
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    rendered = db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content.id, Artifact.artifact_type == "CoverPNG")
        .order_by(Artifact.created_at.desc())
        .limit(1)
    )
    return {
        "upload": {
            "id": upload.id,
            **{key: value for key, value in upload.payload.items() if key != "path"},
            "preview_url": f"/api/contents/{content.id}/cover/artifacts/{upload.id}/image",
        } if upload else None,
        "rendered": {
            "id": rendered.id,
            **{key: value for key, value in rendered.payload.items() if key != "path"},
            "preview_url": f"/api/contents/{content.id}/cover/artifacts/{rendered.id}/image",
        } if rendered else None,
        "defaults": {"width": 900, "height": 1200, "ratio": "3:4", "format": "PNG"},
        "auto_image_generation": image_status(db)["available"],
        "image_generation_busy": generation_busy(content.id),
        "candidates": list_candidates(db, content),
    }


def cover_image_path(db: Session, content: Content, artifact_id: str) -> tuple[Path, str]:
    artifact = db.get(Artifact, artifact_id)
    if not artifact or artifact.content_id != content.id or artifact.artifact_type not in {"CoverUpload", "CoverPNG"}:
        raise WorkflowError("封面图片不存在")
    path = Path(artifact.payload.get("path", "")).resolve()
    roots = {(settings.upload_dir / content.id).resolve(), (settings.export_dir / "covers").resolve()}
    if path.parent not in roots or not path.is_file():
        raise WorkflowError("封面文件不存在或路径无效")
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
    return path, media_type
