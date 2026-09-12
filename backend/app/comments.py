import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import CommentRecord, CommentReplySuggestion, Publication
from .prompt_registry import get_prompt
from .providers import LLMProvider, ProviderError, record_usage
from .schemas import CommentInput, CommentReplyPayload


class CommentError(RuntimeError):
    pass


def _comment_hash(author_label: str | None, text: str) -> str:
    normalized = json.dumps(
        {"author_label": author_label or "", "text": text},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def save_comments(
    db: Session,
    publication_id: str,
    comments: list[CommentInput],
    *,
    source_type: str,
    confirm: bool,
    source_ocr_run_id: str | None = None,
    commit: bool = True,
) -> list[CommentRecord]:
    if not confirm:
        raise CommentError("必须核对评论后才能保存")
    if source_type not in {"paste", "screenshot"}:
        raise CommentError("不支持的评论来源")
    if not db.get(Publication, publication_id):
        raise CommentError("发布记录不存在")
    if not comments or len(comments) > 50:
        raise CommentError("每次需要保存 1 至 50 条评论")
    saved: list[CommentRecord] = []
    seen: set[str] = set()
    for item in comments:
        text = re.sub(r"\s+", " ", item.text).strip()
        author = re.sub(r"\s+", " ", item.author_label or "").strip() or None
        if not text:
            continue
        content_hash = _comment_hash(author, text)
        if content_hash in seen:
            continue
        seen.add(content_hash)
        existing = db.scalar(
            select(CommentRecord).where(
                CommentRecord.publication_id == publication_id,
                CommentRecord.content_hash == content_hash,
            )
        )
        if existing:
            saved.append(existing)
            continue
        row = CommentRecord(
            publication_id=publication_id,
            source_type=source_type,
            source_ocr_run_id=source_ocr_run_id,
            author_label=author,
            comment_text=text,
            content_hash=content_hash,
        )
        db.add(row)
        db.flush()
        saved.append(row)
    if not saved:
        raise CommentError("没有可保存的有效评论")
    if commit:
        db.commit()
        for row in saved:
            db.refresh(row)
    return saved


def list_comments(db: Session, publication_id: str) -> list[CommentRecord]:
    if not db.get(Publication, publication_id):
        raise CommentError("发布记录不存在")
    return list(
        db.scalars(
            select(CommentRecord)
            .options(selectinload(CommentRecord.reply_suggestions))
            .where(CommentRecord.publication_id == publication_id)
            .order_by(CommentRecord.created_at.desc())
        )
    )


def delete_comment(db: Session, comment_id: str, confirm: bool) -> None:
    if not confirm:
        raise CommentError("必须明确确认后才能永久删除评论")
    row = db.get(CommentRecord, comment_id)
    if not row:
        raise CommentError("评论不存在")
    db.delete(row)
    db.commit()


def _reply_input_hash(prompt_version: str, publication: Publication, comment: CommentRecord) -> str:
    value = json.dumps(
        {
            "prompt_version": prompt_version,
            "article_title": publication.final_title,
            "comment_id": comment.id,
            "author_label": comment.author_label,
            "comment_text": comment.comment_text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_reply(reply: CommentReplyPayload) -> None:
    compact = re.sub(r"\s+", "", reply.reply_text)
    blocked = ("加微信", "加V", "私聊我", "私信我", "关注我", "点个关注")
    if any(item.lower() in compact.lower() for item in blocked):
        raise CommentError("回复建议包含引流或私聊诱导，已停止保存")
    if re.search(r"你(?:就是|有|得了).{0,5}(?:抑郁症|焦虑症|人格障碍)", compact):
        raise CommentError("回复建议包含未经依据的心理诊断，已停止保存")


async def generate_reply_suggestion(
    db: Session,
    provider: LLMProvider,
    comment_id: str,
    confirm_send_to_model: bool,
) -> CommentReplySuggestion:
    if not confirm_send_to_model:
        raise CommentError("必须确认将这条评论发送给已配置的 DeepSeek 后才能生成建议")
    comment = db.get(CommentRecord, comment_id)
    if not comment:
        raise CommentError("评论不存在")
    publication = db.get(Publication, comment.publication_id)
    if not publication:
        raise CommentError("发布记录不存在")
    prompt = get_prompt("comment_reply")
    input_hash = _reply_input_hash(prompt.version, publication, comment)
    existing = db.scalar(
        select(CommentReplySuggestion)
        .where(
            CommentReplySuggestion.input_hash == input_hash,
            CommentReplySuggestion.status == "generated",
        )
        .order_by(CommentReplySuggestion.created_at.desc())
        .limit(1)
    )
    if existing:
        return existing
    row = CommentReplySuggestion(
        comment_id=comment.id,
        status="running",
        input_hash=input_hash,
        prompt_version=prompt.version,
        payload={},
    )
    db.add(row)
    db.flush()
    input_payload: dict[str, Any] = {
        "article_title": publication.final_title,
        "comment": {
            "comment_id": comment.id,
            "author_label": comment.author_label,
            "text": comment.comment_text,
        },
        "boundaries": [
            "只生成一条 300 字以内建议，不自动发送",
            "不做心理诊断，不诱导关注、私聊或添加联系方式",
            "不承诺解决对方问题，不泄露其他评论或账号数据",
        ],
    }
    try:
        result = await provider.generate_json(
            system_prompt=prompt.system_prompt,
            user_prompt=json.dumps(input_payload, ensure_ascii=False, separators=(",", ":")),
            task_type="comment_reply",
        )
        validated = CommentReplyPayload.model_validate(result.payload)
        _validate_reply(validated)
        row.status = "generated"
        row.model_name = result.model
        row.payload = validated.model_dump(mode="json")
        row.completed_at = datetime.now(timezone.utc)
        record_usage(db, publication.content_id, "comment_reply", result)
        db.commit()
        db.refresh(row)
        return row
    except (ProviderError, ValidationError, CommentError, ValueError) as exc:
        row.status = "failed"
        row.error_summary = str(exc)[:1000]
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise CommentError(str(exc)) from exc
