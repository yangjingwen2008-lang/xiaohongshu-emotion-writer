import pytest
from fastapi.testclient import TestClient

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app
from backend.app.plugin_security import (
    AssessmentRequest,
    PluginEvidence,
    PluginManifest,
    PluginSecurityError,
    activate_assessment,
    assess_candidate,
    isolate_and_validate,
    list_registry,
    load_builtin_manifests,
    rollback_registry,
    tool_registry,
)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def candidate_manifest(**overrides) -> PluginManifest:
    values = {
        "plugin_id": "demo-plugin",
        "name": "Demo reviewed provider",
        "version": "1.2.3",
        "provider_type": "SearchProvider",
        "source_repo": "https://github.com/example/demo-plugin",
        "pinned_ref": "0123456789abcdef0123456789abcdef01234567",
        "license": "MIT",
        "maintenance_status": "maintained",
        "permissions": ["network:https://api.example.com"],
        "allowed_domains": ["api.example.com"],
        "read_dirs": ["data/plugin_data/demo-plugin"],
        "write_dirs": ["data/plugin_data/demo-plugin/cache"],
        "secret_names": [],
        "needs_secret": False,
        "retention": "Local cache is deleted when the plugin is removed",
        "timeout_seconds": 20,
        "health_check": "manifest-only schema and checksum validation",
        "rollback_version": "1.2.2",
        "enabled": True,
        "built_in": False,
        "tools": [{
            "tool_id": "demo.search",
            "description": "Search a documented public API",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "permissions": ["network:https://api.example.com"],
            "timeout_seconds": 20,
            "max_output_bytes": 100_000,
        }],
    }
    values.update(overrides)
    return PluginManifest.model_validate(values)


def test_builtin_manifests_cover_all_provider_contracts():
    manifests = load_builtin_manifests()
    assert {item.provider_type for item in manifests} == {
        "LLMProvider", "SearchProvider", "TrendSourceProvider", "OCRProvider",
        "CoverRendererProvider", "ImageGenerationProvider", "PublicMetricsProvider",
        "ExportProvider", "EmbeddingProvider",
    }
    assert len({item.plugin_id for item in manifests}) == len(manifests)
    assert all(tool["timeout_seconds"] <= 120 for tool in tool_registry())


def test_security_gate_rejects_browser_cookie_and_unpinned_candidate():
    manifest = candidate_manifest(
        pinned_ref="main",
        permissions=["browser.cookies.read"],
        read_dirs=["C:/Users"],
    )
    with SessionLocal() as db:
        row = assess_candidate(db, AssessmentRequest(
            manifest=manifest,
            evidence=PluginEvidence(reads_browser_data=True),
            confirm=True,
        ))
        assert row.status == "rejected"
        codes = {item["code"] for item in row.findings}
        assert {"ref_not_pinned", "forbidden_permission", "directory_outside_sandbox", "reads_browser_data"} <= codes


def test_incomplete_activity_and_dependency_evidence_cannot_enter_isolation():
    with SessionLocal() as db:
        row = assess_candidate(db, AssessmentRequest(
            manifest=candidate_manifest(), evidence=PluginEvidence(), confirm=True
        ))
        assert row.status == "needs_review"
        with pytest.raises(PluginSecurityError, match="approved"):
            isolate_and_validate(db, row.id, True)


def test_approved_manifest_uses_isolation_then_activation_and_rollback():
    with SessionLocal() as db:
        assessment = assess_candidate(db, AssessmentRequest(
            manifest=candidate_manifest(),
            evidence=PluginEvidence(
                last_update="2026-07-01T00:00:00Z",
                commits_90d=12,
                maintainer_trust="known",
                dependency_count=3,
                network_targets=["api.example.com"],
            ),
            confirm=True,
        ))
        assert assessment.status == "approved"
        assessment = isolate_and_validate(db, assessment.id, True)
        assert assessment.isolation_status == "passed"
        assert assessment.regression_summary["code_executed"] is False
        active = activate_assessment(db, assessment.id, True)
        assert active.registry_version == 1
        assert active.status == "active"
        assert next(item for item in list_registry(db) if item["manifest"]["plugin_id"] == "demo-plugin")["activation_mode"] == "manifest_only"
        restored = rollback_registry(db, "demo-plugin", 1, True)
        assert restored.registry_version == 2
        assert restored.change_type == "rollback"


def test_plugin_api_requires_confirmation_and_exposes_registry():
    client = TestClient(app)
    assert client.get("/api/plugins/manifests").status_code == 200
    payload = {
        "manifest": candidate_manifest().model_dump(mode="json"),
        "evidence": PluginEvidence().model_dump(mode="json"),
        "confirm": False,
    }
    response = client.post("/api/plugins/assessments", json=payload)
    assert response.status_code == 400
    assert "confirmation" in response.json()["detail"].lower()
