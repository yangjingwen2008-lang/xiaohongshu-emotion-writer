from fastapi.testclient import TestClient
import pytest

from backend.app.database import Base, SessionLocal, engine
from backend.app.diff_memory import analyze_human_revision
from backend.app.editorial_constitution import (
    INITIAL_EDITORIAL_CONSTITUTION,
    current_constitution_payload,
    rollback_constitution,
    update_constitution,
)
from backend.app.main import app
from backend.app.memory_retrieval import generation_memory_report
from backend.app.models import Content, ContentVersion
from backend.app.style_training import current_profile


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def test_editorial_constitution_is_versioned_and_rollback_creates_a_new_version():
    with SessionLocal() as db:
        initial_version, initial_sections = current_constitution_payload(db)
        assert initial_version == 0
        assert len(initial_sections["evaluation_dimensions"]) == 12

        changed = dict(INITIAL_EDITORIAL_CONSTITUTION)
        changed["core_principles"] = [*changed["core_principles"], "保留真实的不确定感"]
        first = update_constitution(db, changed, "增加不确定感边界")
        second = update_constitution(db, INITIAL_EDITORIAL_CONSTITUTION, "恢复初始规则")
        restored = rollback_constitution(db, first.version)

        assert first.version == 1
        assert second.version == 2
        assert restored.version == 3
        assert restored.source_version == 1
        assert restored.sections["core_principles"][-1] == "保留真实的不确定感"


def test_revision_diff_candidates_show_evidence_count_and_need_confirmation():
    opening = "她在便利店门口停了很久，手里的牛奶已经变凉。"
    initial_body = (
        opening
        + "原来我终于明白，真正的告别不是离开，而是在城市里反复看见旧日的影子。"
        + "这句话被我写得很长，因为我想把所有事情都解释清楚，也想把每一种情绪都排列整齐。"
        + "《海边的卡夫卡》让我想到那条街，后来才明白，我们终究都要学会成长和释怀。"
    )
    human_body = (
        opening
        + "我没有明白什么。\n"
        + "只是每次经过那条街，手指都会先缩进袖口。\n"
        + "店员关掉一盏灯。\n"
        + "我站了一会儿，还是没有进去。"
    )
    with SessionLocal() as db:
        content = Content(theme="分开后的旧街", emotion="迟来的想念")
        db.add(content)
        db.flush()
        initial = ContentVersion(
            content_id=content.id,
            version=1,
            kind="initial_draft",
            title="旧街还记得",
            body_html=f"<p>{initial_body}</p>",
            body_text=initial_body,
            metadata_json={"cultural_references": [{"work": "《海边的卡夫卡》"}]},
            content_hash="initial",
        )
        human = ContentVersion(
            content_id=content.id,
            version=2,
            kind="human_edit",
            title="我还是绕开那条街",
            body_html="<p>edited</p>",
            body_text=human_body,
            metadata_json={},
            content_hash="human",
        )
        db.add_all([initial, human])
        db.flush()

        candidates = analyze_human_revision(db, content, human)
        db.commit()
        deleted = next(item for item in candidates if item.pattern_type == "deleted_phrase")
        citation = next(item for item in candidates if item.pattern_type == "removed_citation")
        assert deleted.occurrence_count == 1
        assert deleted.evidence[0]["before_excerpt"]
        assert deleted.evidence[0]["after_excerpt"]
        assert citation.evidence[0]["metrics"]["removed_references"] == ["《海边的卡夫卡》"]
        assert current_profile(db) is None

        later = ContentVersion(
            content_id=content.id,
            version=3,
            kind="human_edit",
            title=human.title,
            body_html=human.body_html,
            body_text=human.body_text,
            metadata_json={},
            content_hash="human-again",
        )
        db.add(later)
        db.flush()
        analyze_human_revision(db, content, later)
        db.commit()
        db.refresh(deleted)
        assert deleted.occurrence_count == 1

        client = TestClient(app)
        refused = client.post(
            f"/api/style-training/diff-candidates/{deleted.id}/confirm",
            json={"confirm": False},
        )
        assert refused.status_code == 400
        accepted = client.post(
            f"/api/style-training/diff-candidates/{deleted.id}/confirm",
            json={"confirm": True},
        )
        assert accepted.status_code == 200
        db.expire_all()
        profile = current_profile(db)
        assert profile is not None
        assert profile.change_type == "diff_memory"
        assert profile.rules["confirmed_diff_memory"][0]["rule_text"] == deleted.rule_text
        report = generation_memory_report(db, content, profile)
        assert report["style_rules_used"][0] == deleted.rule_text


def test_editorial_constitution_api_enforces_explicit_confirmation():
    client = TestClient(app)
    initial = client.get("/api/editorial-constitution")
    assert initial.status_code == 200
    assert initial.json()["version"] == 0

    payload = {
        "sections": INITIAL_EDITORIAL_CONSTITUTION,
        "change_note": "确认初始边界",
        "confirm": False,
    }
    refused = client.post("/api/editorial-constitution", json=payload)
    assert refused.status_code == 400

    payload["confirm"] = True
    saved = client.post("/api/editorial-constitution", json=payload)
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    versions = client.get("/api/editorial-constitution/versions")
    assert [item["version"] for item in versions.json()] == [1, 0]
