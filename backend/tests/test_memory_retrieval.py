import pytest
from sqlalchemy import text

from backend.app.database import Base, SessionLocal, engine
from backend.app.memory_retrieval import (
    FTS_ENGINE_NAME,
    ensure_search_index_current,
    generation_memory_report,
    index_version,
    ngram_similarity,
    search_versions,
)
from backend.app.models import Content, ContentVersion


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS content_search_fts"))
    yield


def test_fts5_ngram_retrieval_exposes_fingerprints_without_historical_body():
    sentinel = "HISTORICAL_FULL_BODY_MUST_NOT_ENTER_GENERATION_CONTEXT"
    with SessionLocal() as db:
        historical = Content(theme="分开后的城市", emotion="迟来的想念", title="旧街仍然记得")
        current = Content(theme="离开以后走过旧街", emotion="城市记忆")
        db.add_all([historical, current])
        db.flush()
        version = ContentVersion(
            content_id=historical.id,
            version=1,
            kind="human_edit",
            title="旧街仍然记得",
            body_html=f"<p>{sentinel}，她从便利店门口经过。</p>",
            body_text=f"{sentinel}，她从便利店门口经过。城市在夜里留下记忆。",
            metadata_json={
                "memory_fingerprint": {
                    "scenes": ["便利店", "旧街"],
                    "structure_tags": ["场景开头", "回忆折返"],
                    "imagery": ["夜", "街道"],
                    "ending_type": "动作或场景停顿",
                }
            },
            content_hash="historical-hash",
        )
        db.add(version)
        db.flush()
        index_version(db, historical, version)
        db.commit()

        matches = search_versions(db, "城市旧街便利店的记忆", exclude_content_id=current.id)
        assert [item.id for item in matches] == [version.id]

        report = generation_memory_report(db, current, profile=None)
        assert report["retrieval_engine"] == FTS_ENGINE_NAME
        assert report["avoid_history"][0]["scenes"] == ["便利店", "旧街"]
        assert sentinel not in str(report)
        assert "未注入历史正文" in report["retrieval_scope"]


def test_chinese_ngram_similarity_detects_rephrased_overlap():
    similar = ngram_similarity("她又走过那条旧街，城市还记得分别。", "城市记得分别以后，她走回那条旧街。")
    unrelated = ngram_similarity("她又走过那条旧街，城市还记得分别。", "清晨的厨房里，水壶正在慢慢变热。")
    assert similar > unrelated
    assert similar > 0


def test_empty_search_index_is_created_and_committed_on_startup():
    with SessionLocal() as db:
        ensure_search_index_current(db)
    with engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM content_search_fts")).scalar_one()
    assert count == 0
