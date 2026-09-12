from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..plugin_security import AssessmentRequest, ConfirmationRequest as PluginConfirmationRequest, GitHubInspectRequest, PluginSecurityError, activate_assessment, assess_candidate, discard_isolation, inspect_github_repository, isolate_and_validate, list_assessments, list_registry, list_registry_history, rollback_registry, tool_registry
from .dependencies import _plugin_error


router = APIRouter()


@router.get("/plugins/manifests")
def plugin_manifests(db: Session = Depends(get_db)) -> list[dict]:
    return list_registry(db)


@router.get("/plugins/tools")
def plugin_tools() -> list[dict]:
    return tool_registry()


@router.get("/plugins/assessments")
def plugin_assessments(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": item.id, "plugin_id": item.plugin_id, "candidate_version": item.candidate_version,
            "source_repo": item.source_repo, "pinned_ref": item.pinned_ref,
            "manifest_hash": item.manifest_hash, "evidence": item.evidence,
            "findings": item.findings, "status": item.status,
            "isolation_status": item.isolation_status, "regression_summary": item.regression_summary,
            "error_summary": item.error_summary, "created_at": item.created_at,
        }
        for item in list_assessments(db)
    ]


@router.post("/plugins/assessments")
def create_plugin_assessment(payload: AssessmentRequest, db: Session = Depends(get_db)) -> dict:
    try:
        item = assess_candidate(db, payload)
        return {"id": item.id, "plugin_id": item.plugin_id, "status": item.status,
                "isolation_status": item.isolation_status, "findings": item.findings,
                "manifest_hash": item.manifest_hash}
    except PluginSecurityError as exc:
        raise _plugin_error(exc) from exc


@router.post("/plugins/github/inspect")
async def inspect_plugin_repository(payload: GitHubInspectRequest) -> dict:
    try:
        return await inspect_github_repository(payload)
    except PluginSecurityError as exc:
        raise _plugin_error(exc) from exc


@router.post("/plugins/assessments/{assessment_id}/isolate")
def isolate_plugin_assessment(
    assessment_id: str, payload: PluginConfirmationRequest, db: Session = Depends(get_db)
) -> dict:
    try:
        item = isolate_and_validate(db, assessment_id, payload.confirm)
        return {"id": item.id, "status": item.status, "isolation_status": item.isolation_status,
                "regression_summary": item.regression_summary, "error_summary": item.error_summary}
    except PluginSecurityError as exc:
        raise _plugin_error(exc) from exc


@router.post("/plugins/assessments/{assessment_id}/activate")
def activate_plugin_assessment(
    assessment_id: str, payload: PluginConfirmationRequest, db: Session = Depends(get_db)
) -> dict:
    try:
        row = activate_assessment(db, assessment_id, payload.confirm)
        try:
            discard_isolation(assessment_id)
            isolation_cleanup = "removed"
        except PluginSecurityError:
            isolation_cleanup = "retained_for_manual_cleanup"
        return {"id": row.id, "plugin_id": row.plugin_id, "registry_version": row.registry_version,
                "plugin_version": row.plugin_version, "status": row.status,
                "activation_mode": "manifest_only", "isolation_cleanup": isolation_cleanup}
    except PluginSecurityError as exc:
        raise _plugin_error(exc) from exc


@router.get("/plugins/{plugin_id}/history")
def plugin_history(plugin_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return [
        {"id": row.id, "plugin_id": row.plugin_id, "registry_version": row.registry_version,
         "plugin_version": row.plugin_version, "manifest_hash": row.manifest_hash,
         "status": row.status, "change_type": row.change_type,
         "source_registry_version": row.source_registry_version, "activated_at": row.activated_at}
        for row in list_registry_history(db, plugin_id)
    ]


@router.post("/plugins/{plugin_id}/rollback/{registry_version}")
def rollback_plugin(
    plugin_id: str, registry_version: int, payload: PluginConfirmationRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = rollback_registry(db, plugin_id, registry_version, payload.confirm)
        return {"id": row.id, "plugin_id": row.plugin_id, "registry_version": row.registry_version,
                "plugin_version": row.plugin_version, "status": row.status,
                "change_type": row.change_type, "source_registry_version": row.source_registry_version}
    except PluginSecurityError as exc:
        raise _plugin_error(exc) from exc
