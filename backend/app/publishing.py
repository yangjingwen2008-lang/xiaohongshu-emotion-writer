import html
import json
import logging
import re
from datetime import datetime
from io import BytesIO
from uuid import uuid4

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .cover_studio import cover_image_path, render_cover, save_cover_upload
from .models import Artifact, Content, ContentVersion
from .orchestrator import WorkflowError

__all__ = ["export_package", "render_cover", "save_cover_upload"]


def _safe_name(value: str, max_len: int = 55) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return (cleaned or "未命名")[:max_len]


def _latest_version(db: Session, content_id: str) -> ContentVersion:
    version = db.scalar(
        select(ContentVersion).where(ContentVersion.content_id == content_id).order_by(ContentVersion.version.desc()).limit(1)
    )
    if not version:
        raise WorkflowError("没有可导出的正文版本")
    return version


def _latest_draft(db: Session, content_id: str) -> dict:
    artifact = db.scalar(
        select(Artifact)
        .where(Artifact.content_id == content_id, Artifact.artifact_type == "EssayDraft")
        .order_by(Artifact.version.desc())
        .limit(1)
    )
    if not artifact:
        raise WorkflowError("没有可导出的 EssayDraft")
    return artifact.payload


def export_package(db: Session, content: Content) -> dict:
    version = _latest_version(db, content.id)
    draft = _latest_draft(db, content.id)
    cover = db.scalar(
        select(Artifact).where(Artifact.content_id == content.id, Artifact.artifact_type == "CoverPNG")
        .order_by(Artifact.version.desc()).limit(1)
    )
    if not cover:
        cover = render_cover(db, content, "whitespace", None)
    cover_path, _ = cover_image_path(db, content, cover.id)
    cover_data = BytesIO()
    with Image.open(cover_path) as image:
        image.save(cover_data, format="PNG")
    tags = " ".join(f"#{tag.lstrip('#')}" for group in ("core_tags", "trend_tags", "long_tail_tags") for tag in draft.get(group, []))
    plain = f"标题：{version.title}\n\n{version.body_text}\n\n标签：{tags}\n\n置顶评论：{draft.get('pinned_comment','')}\n"
    markdown = f"# {version.title}\n\n{version.body_text}\n\n{tags}\n\n> {draft.get('pinned_comment','')}\n"
    page = f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>{html.escape(version.title)}</title><style>body{{max-width:720px;margin:30px auto;padding:20px;font:17px/1.9 serif;background:#f4f1e9;color:#292723}}button{{padding:12px;margin:5px;background:#3f493f;color:white;border:0}}img{{max-width:280px}}pre{{white-space:pre-wrap}}</style><h1>{html.escape(version.title)}</h1><img src='封面.png'><p><button onclick="navigator.clipboard.writeText(document.querySelector('h1').textContent)">复制标题</button><button onclick="navigator.clipboard.writeText(document.querySelector('pre').textContent)">复制正文</button></p><pre>{html.escape(version.body_text)}</pre><p>{html.escape(tags)}</p><p>{html.escape(draft.get('pinned_comment',''))}</p></html>"""
    manifest = {
        "content_id": content.id,
        "version": version.version,
        "files": ["封面.png", "发布内容.txt", "发布内容.md", "手机发布页.html"],
        "originality_scope": "本地历史；公开网页检测状态见应用内报告",
        "auto_publish": False,
    }
    files = {
        "封面.png": cover_data.getvalue(),
        "发布内容.txt": plain.encode("utf-8-sig"),
        "发布内容.md": markdown.encode("utf-8"),
        "手机发布页.html": page.encode("utf-8"),
        "发布清单.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    }
    # Each export is a snapshot. Repeated exports must never alter an earlier package.
    folder = settings.export_dir / f"{datetime.now():%Y-%m-%d_%H%M%S}_{_safe_name(version.title)}_{uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    try:
        for name, data in files.items():
            (folder / name).write_bytes(data)
    except OSError as exc:
        try:
            for name in files:
                (folder / name).unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            logging.getLogger(__name__).warning("本次导出的未完成文件清理失败。")
        raise WorkflowError("发布包写入失败，请检查磁盘空间和目录权限后重新导出") from exc
    return {"folder": str(folder), "manifest": manifest}
