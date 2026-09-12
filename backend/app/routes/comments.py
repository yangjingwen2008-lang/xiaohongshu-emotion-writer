from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..comments import CommentError, delete_comment, generate_reply_suggestion, list_comments, save_comments
from ..models import CommentRecord
from ..providers import LLMProvider
from ..schemas import ConfirmationRequest, CommentBatchCreateRequest, CommentRecordView, CommentReplyGenerateRequest, CommentReplySuggestionView
from .dependencies import get_analytics_llm_provider


router = APIRouter()


@router.get("/publications/{publication_id}/comments", response_model=list[CommentRecordView])
def publication_comments(publication_id: str, db: Session = Depends(get_db)) -> list[CommentRecord]:
    try:
        return list_comments(db, publication_id)
    except CommentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/publications/{publication_id}/comments", response_model=list[CommentRecordView])
def create_publication_comments(
    publication_id: str,
    payload: CommentBatchCreateRequest,
    db: Session = Depends(get_db),
) -> list[CommentRecord]:
    try:
        return save_comments(
            db,
            publication_id,
            payload.comments,
            source_type="paste",
            confirm=payload.confirm,
        )
    except CommentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/comments/{comment_id}")
def remove_comment(
    comment_id: str,
    payload: ConfirmationRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        delete_comment(db, comment_id, payload.confirm)
        return {"deleted": True}
    except CommentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/comments/{comment_id}/reply-suggestions", response_model=CommentReplySuggestionView)
async def create_comment_reply_suggestion(
    comment_id: str,
    payload: CommentReplyGenerateRequest,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_analytics_llm_provider),
):
    try:
        return await generate_reply_suggestion(
            db,
            provider,
            comment_id,
            payload.confirm_send_to_model,
        )
    except CommentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
