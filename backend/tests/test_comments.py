from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.api import get_analytics_llm_provider
from backend.app.comments import CommentError, delete_comment, generate_reply_suggestion, list_comments, save_comments
from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.models import CommentReplySuggestion, Content, Publication
from backend.app.providers import ProviderResult
from backend.app.schemas import CommentInput


client = TestClient(app)


class FakeReplyProvider:
    def __init__(self, reply_text: str = "原来我们都在这样的时刻里，慢一点也没有关系。") -> None:
        self.calls = 0
        self.reply_text = reply_text

    async def generate_json(self, *, system_prompt: str, user_prompt: str, task_type: str) -> ProviderResult:
        self.calls += 1
        assert task_type == "comment_reply"
        assert "不自动发送" in user_prompt
        return ProviderResult(
            payload={"reply_text": self.reply_text, "tone": "温柔共情", "safety_note": "不诊断、不引流。"},
            model="fake-reply",
            input_tokens=40,
            output_tokens=20,
        )


@pytest.fixture(autouse=True)
def clean_db_and_dependency():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    app.dependency_overrides.pop(get_analytics_llm_provider, None)


def create_publication(db) -> Publication:
    content = Content(theme="雨夜", emotion="被理解", status="published")
    db.add(content)
    db.flush()
    publication = Publication(
        content_id=content.id,
        note_url="https://www.xiaohongshu.com/explore/comments-test",
        published_at=datetime.now(timezone.utc),
        final_title="雨停以后",
        final_tags=["情绪"],
    )
    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication


@pytest.mark.asyncio
async def test_manual_comments_dedupe_and_reply_requires_active_model_consent():
    provider = FakeReplyProvider()
    with SessionLocal() as db:
        publication = create_publication(db)
        with pytest.raises(CommentError, match="核对评论"):
            save_comments(db, publication.id, [CommentInput(text="很像我")], source_type="paste", confirm=False)
        saved = save_comments(
            db,
            publication.id,
            [
                CommentInput(author_label="小雨", text=" 很像我经历过的那段时间 "),
                CommentInput(author_label="小雨", text="很像我经历过的那段时间"),
            ],
            source_type="paste",
            confirm=True,
        )
        assert len(saved) == 1
        assert len(list_comments(db, publication.id)) == 1

        with pytest.raises(CommentError, match="确认将这条评论发送"):
            await generate_reply_suggestion(db, provider, saved[0].id, False)
        assert provider.calls == 0

        first = await generate_reply_suggestion(db, provider, saved[0].id, True)
        duplicate = await generate_reply_suggestion(db, provider, saved[0].id, True)
        assert duplicate.id == first.id
        assert provider.calls == 1
        assert first.payload["tone"] == "温柔共情"

        publication.final_title = "雨停以后，我们还在这里"
        db.commit()
        changed_input = await generate_reply_suggestion(db, provider, saved[0].id, True)
        assert changed_input.id != first.id
        assert provider.calls == 2

        with pytest.raises(CommentError, match="明确确认"):
            delete_comment(db, saved[0].id, False)
        delete_comment(db, saved[0].id, True)
        assert list_comments(db, publication.id) == []


@pytest.mark.asyncio
async def test_reply_safety_gate_rejects_private_contact_inducement():
    provider = FakeReplyProvider("你可以加微信，我们私聊。")
    with SessionLocal() as db:
        publication = create_publication(db)
        comment = save_comments(
            db,
            publication.id,
            [CommentInput(text="最近真的很难熬")],
            source_type="paste",
            confirm=True,
        )[0]
        with pytest.raises(CommentError, match="私聊诱导"):
            await generate_reply_suggestion(db, provider, comment.id, True)
        failed = db.scalar(select(CommentReplySuggestion).where(CommentReplySuggestion.comment_id == comment.id))
        assert failed and failed.status == "failed"
        assert failed.payload == {}


def test_comment_api_saves_multiple_comments_and_only_returns_copyable_suggestion():
    provider = FakeReplyProvider()
    app.dependency_overrides[get_analytics_llm_provider] = lambda: provider
    with SessionLocal() as db:
        publication = create_publication(db)

    saved = client.post(
        f"/api/publications/{publication.id}/comments",
        json={
            "comments": [
                {"author_label": "晚风", "text": "看到这里突然鼻子一酸"},
                {"author_label": None, "text": "谢谢你写出来"},
            ],
            "confirm": True,
        },
    )
    assert saved.status_code == 200, saved.text
    comments = saved.json()
    assert len(comments) == 2

    blocked = client.post(
        f"/api/comments/{comments[0]['id']}/reply-suggestions",
        json={"confirm_send_to_model": False},
    )
    assert blocked.status_code == 400

    generated = client.post(
        f"/api/comments/{comments[0]['id']}/reply-suggestions",
        json={"confirm_send_to_model": True},
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["payload"]["reply_text"].startswith("原来我们")

    listed = client.get(f"/api/publications/{publication.id}/comments")
    assert listed.status_code == 200
    replied = next(item for item in listed.json() if item["id"] == comments[0]["id"])
    assert len(replied["reply_suggestions"]) == 1
