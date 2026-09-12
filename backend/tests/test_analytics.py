from datetime import datetime, timedelta, timezone

import pytest

from backend.app.analytics import due_snapshots, record_publication, save_snapshot
from backend.app.database import Base, SessionLocal, engine
from backend.app.models import Artifact, Content, ContentVersion


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def test_publication_and_day_snapshots_use_real_denominators_only():
    with SessionLocal() as db:
        content = Content(
            theme="A city after goodbye",
            emotion="lingering sadness",
            title="The street remembers",
            status="pending_review",
            current_step="review_submission",
        )
        db.add(content)
        db.flush()
        version = ContentVersion(
            content_id=content.id,
            version=1,
            kind="human_edit",
            title="The street remembers",
            body_html="<p>Final body</p>",
            body_text="Final body",
            metadata_json={},
            content_hash="body-hash",
            is_final=False,
        )
        draft = Artifact(
            content_id=content.id,
            artifact_type="EssayDraft",
            step_id="draft_generation",
            version=1,
            payload={
                "core_tags": ["emotion"],
                "trend_tags": [],
                "long_tail_tags": ["city memory"],
                "recommended_publish_time": "21:30",
            },
            source_artifact_ids=[],
            content_hash="draft-hash",
            confirmed=True,
        )
        db.add_all([version, draft])
        db.commit()

        published_at = datetime.now(timezone.utc) - timedelta(days=8)
        publication = record_publication(
            db,
            content.id,
            "https://www.xiaohongshu.com/explore/example-note",
            published_at,
        )
        assert content.status == "published"
        assert publication.final_version_id == version.id
        assert publication.final_tags == ["emotion", "city memory"]

        snapshot = save_snapshot(
            db,
            publication.id,
            1,
            {"views": 1000, "likes": 80, "favorites": 40, "comments": 20},
            "manual entry",
        )
        assert snapshot.calculated_rates["like_rate"] == 0.08
        assert snapshot.calculated_rates["favorite_rate"] == 0.04
        assert snapshot.calculated_rates["engagement_denominator"] == "views"

        without_denominator = save_snapshot(
            db,
            publication.id,
            3,
            {"likes": 120, "extra_metrics": {}},
            None,
        )
        assert "like_rate" not in without_denominator.calculated_rates

        due = due_snapshots(db)
        assert [(item["day_offset"], item["publication_id"]) for item in due] == [(7, publication.id)]
