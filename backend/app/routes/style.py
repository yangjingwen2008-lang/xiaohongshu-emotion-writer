from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import DiffMemoryCandidate, EditorialConstitutionVersion, StyleProfileVersion, StyleTrainingProposal
from ..schemas import DiffMemoryCandidateView, DiffMemoryDecisionRequest, EditorialConstitutionRollbackRequest, EditorialConstitutionUpdateRequest, EditorialConstitutionView, StyleProfileRollbackRequest, StyleProfileUpdateRequest, StyleProfileView, StyleTrainingProposalView, StyleTrainingRequest
from ..style_training import INITIAL_STYLE_PROFILE, StyleTrainingError, analyze_style, current_profile, decide_proposal, list_profile_versions, rollback_profile, update_profile
from ..diff_memory import DiffMemoryError, decide_diff_candidate, list_diff_candidates
from ..editorial_constitution import INITIAL_EDITORIAL_CONSTITUTION, EditorialConstitutionError, current_constitution, list_constitution_versions, rollback_constitution, update_constitution


router = APIRouter()


@router.post("/style-training/analyze", response_model=StyleTrainingProposalView)
async def analyze_reference_article(
    payload: StyleTrainingRequest, db: Session = Depends(get_db)
) -> StyleTrainingProposal:
    try:
        return await analyze_style(db, payload.article, payload.source_type)
    except StyleTrainingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/style-training/proposals", response_model=list[StyleTrainingProposalView])
def list_style_proposals(db: Session = Depends(get_db)) -> list[StyleTrainingProposal]:
    return list(
        db.scalars(select(StyleTrainingProposal).order_by(StyleTrainingProposal.created_at.desc()).limit(50))
    )


@router.post("/style-training/proposals/{proposal_id}/confirm", response_model=StyleTrainingProposalView)
def confirm_style_proposal(proposal_id: str, db: Session = Depends(get_db)) -> StyleTrainingProposal:
    try:
        return decide_proposal(db, proposal_id, True)
    except StyleTrainingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/style-training/proposals/{proposal_id}/reject", response_model=StyleTrainingProposalView)
def reject_style_proposal(proposal_id: str, db: Session = Depends(get_db)) -> StyleTrainingProposal:
    try:
        return decide_proposal(db, proposal_id, False)
    except StyleTrainingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/style-training/profile", response_model=StyleProfileView)
def get_style_profile(db: Session = Depends(get_db)) -> StyleProfileView:
    profile = current_profile(db)
    if not profile:
        return StyleProfileView(version=0, rules=INITIAL_STYLE_PROFILE)
    return StyleProfileView(
        id=profile.id,
        version=profile.version,
        rules=profile.rules,
        change_type=profile.change_type,
        source_version=profile.source_version,
        created_at=profile.created_at,
    )


@router.get("/style-training/profile/versions", response_model=list[StyleProfileView])
def get_style_profile_versions(db: Session = Depends(get_db)) -> list[StyleProfileVersion]:
    return list_profile_versions(db)


@router.post("/style-training/profile", response_model=StyleProfileView)
def save_style_profile(payload: StyleProfileUpdateRequest, db: Session = Depends(get_db)) -> StyleProfileVersion:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认风格档案修改")
    return update_profile(
        db,
        payload.core_rules,
        payload.manual_preferences,
        payload.manual_avoid_patterns,
    )


@router.post("/style-training/profile/rollback/{version}", response_model=StyleProfileView)
def restore_style_profile(
    version: int, payload: StyleProfileRollbackRequest, db: Session = Depends(get_db)
) -> StyleProfileVersion:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认回滚风格档案")
    try:
        return rollback_profile(db, version)
    except StyleTrainingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/editorial-constitution", response_model=EditorialConstitutionView)
def get_editorial_constitution(db: Session = Depends(get_db)) -> EditorialConstitutionView:
    constitution = current_constitution(db)
    if not constitution:
        return EditorialConstitutionView(version=0, sections=INITIAL_EDITORIAL_CONSTITUTION)
    return EditorialConstitutionView.model_validate(constitution)


@router.get("/editorial-constitution/versions", response_model=list[EditorialConstitutionView])
def get_editorial_constitution_versions(
    db: Session = Depends(get_db),
) -> list[EditorialConstitutionView]:
    versions = [EditorialConstitutionView.model_validate(item) for item in list_constitution_versions(db)]
    versions.append(EditorialConstitutionView(version=0, sections=INITIAL_EDITORIAL_CONSTITUTION))
    return versions


@router.post("/editorial-constitution", response_model=EditorialConstitutionView)
def save_editorial_constitution(
    payload: EditorialConstitutionUpdateRequest,
    db: Session = Depends(get_db),
) -> EditorialConstitutionVersion:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认编辑宪法修改")
    return update_constitution(db, payload.sections.model_dump(mode="json"), payload.change_note)


@router.post(
    "/editorial-constitution/rollback/{version}",
    response_model=EditorialConstitutionView,
)
def restore_editorial_constitution(
    version: int,
    payload: EditorialConstitutionRollbackRequest,
    db: Session = Depends(get_db),
) -> EditorialConstitutionVersion:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认恢复编辑宪法")
    try:
        return rollback_constitution(db, version)
    except EditorialConstitutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/style-training/diff-candidates", response_model=list[DiffMemoryCandidateView])
def get_diff_memory_candidates(db: Session = Depends(get_db)) -> list[DiffMemoryCandidate]:
    return list_diff_candidates(db)


@router.post(
    "/style-training/diff-candidates/{candidate_id}/confirm",
    response_model=DiffMemoryCandidateView,
)
def confirm_diff_memory_candidate(
    candidate_id: str,
    payload: DiffMemoryDecisionRequest,
    db: Session = Depends(get_db),
) -> DiffMemoryCandidate:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认差异规律写入风格档案")
    try:
        return decide_diff_candidate(db, candidate_id, True)
    except DiffMemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/style-training/diff-candidates/{candidate_id}/reject",
    response_model=DiffMemoryCandidateView,
)
def reject_diff_memory_candidate(
    candidate_id: str,
    payload: DiffMemoryDecisionRequest,
    db: Session = Depends(get_db),
) -> DiffMemoryCandidate:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="需要人工确认拒绝差异规律")
    try:
        return decide_diff_candidate(db, candidate_id, False)
    except DiffMemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
