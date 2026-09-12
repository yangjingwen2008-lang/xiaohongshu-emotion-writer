from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PluginSecurityAssessment(Base):
    __tablename__ = "plugin_security_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_id: Mapped[str] = mapped_column(String(120), index=True)
    candidate_version: Mapped[str] = mapped_column(String(80))
    source_repo: Mapped[str] = mapped_column(String(1000))
    pinned_ref: Mapped[str] = mapped_column(String(160))
    manifest: Mapped[Any] = mapped_column(JSON)
    manifest_hash: Mapped[str] = mapped_column(String(64), index=True)
    evidence: Mapped[Any] = mapped_column(JSON, default=dict)
    findings: Mapped[Any] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), index=True)
    isolation_status: Mapped[str] = mapped_column(String(30), default="not_started", index=True)
    regression_summary: Mapped[Any] = mapped_column(JSON, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PluginRegistryVersion(Base):
    __tablename__ = "plugin_registry_versions"
    __table_args__ = (UniqueConstraint("plugin_id", "registry_version", name="uq_plugin_registry_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plugin_id: Mapped[str] = mapped_column(String(120), index=True)
    registry_version: Mapped[int] = mapped_column(Integer)
    plugin_version: Mapped[str] = mapped_column(String(80))
    manifest: Mapped[Any] = mapped_column(JSON)
    manifest_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    change_type: Mapped[str] = mapped_column(String(30), default="activation")
    source_assessment_id: Mapped[str | None] = mapped_column(
        ForeignKey("plugin_security_assessments.id", ondelete="SET NULL"), index=True
    )
    source_registry_version: Mapped[int | None] = mapped_column(Integer)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Content(Base):
    __tablename__ = "contents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    theme: Mapped[str] = mapped_column(String(240))
    emotion: Mapped[str] = mapped_column(String(120))
    extra_requirements: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    current_step: Mapped[str] = mapped_column(String(50), default="idea_intake")
    selected_plan_id: Mapped[str | None] = mapped_column(String(100))
    selected_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="content", cascade="all, delete-orphan")
    versions: Mapped[list["ContentVersion"]] = relationship(back_populates="content", cascade="all, delete-orphan")
    publication: Mapped["Publication | None"] = relationship(
        back_populates="content", cascade="all, delete-orphan", uselist=False
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_workflow_step_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="running")
    input_artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    output_artifact_id: Mapped[str | None] = mapped_column(String(36))
    prompt_version: Mapped[str | None] = mapped_column(String(60))
    tool_permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="SET NULL"))
    artifact_type: Mapped[str] = mapped_column(String(80), index=True)
    step_id: Mapped[str] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[Any] = mapped_column(JSON)
    source_artifact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    prompt_version: Mapped[str | None] = mapped_column(String(60))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content: Mapped[Content] = relationship(back_populates="artifacts")


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (UniqueConstraint("content_id", "version", name="uq_content_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(240))
    body_html: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[Any] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content: Mapped[Content] = relationship(back_populates="versions")


class ApiUsage(Base):
    __tablename__ = "api_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str | None] = mapped_column(ForeignKey("contents.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(40))
    task_type: Mapped[str] = mapped_column(String(80))
    model_name: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalCheckRun(Base):
    __tablename__ = "external_check_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    check_type: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="tavily")
    status: Mapped[str] = mapped_column(String(30), index=True)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    usage_credits: Mapped[int | None] = mapped_column(Integer)
    covered_sources: Mapped[Any] = mapped_column(JSON, default=list)
    unavailable_sources: Mapped[Any] = mapped_column(JSON, default=list)
    result_summary: Mapped[Any] = mapped_column(JSON, default=dict)
    request_ids: Mapped[Any] = mapped_column(JSON, default=list)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManualOriginalitySource(Base):
    __tablename__ = "manual_originality_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(20), index=True)
    label: Mapped[str] = mapped_column(String(240))
    source_value: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrendRefreshRun(Base):
    __tablename__ = "trend_refresh_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_trend_refresh_run_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trigger: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True, default="running")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(40), default="tavily")
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    usage_credits: Mapped[int | None] = mapped_column(Integer)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    data_status: Mapped[str] = mapped_column(String(30), default="data_insufficient")
    request_ids: Mapped[Any] = mapped_column(JSON, default=list)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ManualTrendSource(Base):
    __tablename__ = "manual_trend_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(20), index=True)
    label: Mapped[str] = mapped_column(String(240))
    source_value: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OcrRun(Base):
    __tablename__ = "ocr_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purpose: Mapped[str] = mapped_column(String(30), index=True, default="trend")
    status: Mapped[str] = mapped_column(String(30), index=True, default="pending_confirmation")
    provider: Mapped[str] = mapped_column(String(80))
    original_filename: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(80))
    image_path: Mapped[str | None] = mapped_column(String(1200))
    image_hash: Mapped[str] = mapped_column(String(64), index=True)
    image_size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    recognized_text: Mapped[str | None] = mapped_column(Text)
    corrected_text: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[Any] = mapped_column(JSON, default=list)
    engine_metadata: Mapped[Any] = mapped_column(JSON, default=dict)
    retention_policy: Mapped[str] = mapped_column(String(60), default="delete_after_confirmation")
    linked_manual_trend_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("manual_trend_sources.id", ondelete="SET NULL"), index=True
    )
    linked_analytics_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("analytics_snapshots.id", ondelete="SET NULL"), index=True
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrendSourceRecord(Base):
    __tablename__ = "trend_source_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("trend_refresh_runs.id", ondelete="CASCADE"), index=True)
    manual_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("manual_trend_sources.id", ondelete="SET NULL"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), default="public_search")
    platform: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(240))
    url: Mapped[str | None] = mapped_column(String(1200))
    snippet: Mapped[str] = mapped_column(Text)
    provider_score: Mapped[str | None] = mapped_column(String(40))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrendCandidate(Base):
    __tablename__ = "trend_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("trend_refresh_runs.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    emotion: Mapped[str] = mapped_column(String(120))
    source_ids: Mapped[Any] = mapped_column(JSON, default=list)
    source_platforms: Mapped[Any] = mapped_column(JSON, default=list)
    source_links: Mapped[Any] = mapped_column(JSON, default=list)
    trend_signal: Mapped[str] = mapped_column(String(80))
    trend_basis: Mapped[str] = mapped_column(Text)
    female_emotional_angle: Mapped[str] = mapped_column(Text)
    account_fit: Mapped[str] = mapped_column(String(20))
    homogeneity_risk: Mapped[str] = mapped_column(String(20))
    cultural_association: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20))
    data_limitations: Mapped[str] = mapped_column(Text)
    rewrite_logic: Mapped[str] = mapped_column(Text)
    used_content_id: Mapped[str | None] = mapped_column(
        ForeignKey("contents.id", ondelete="SET NULL"), index=True
    )
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StyleTrainingProposal(Base):
    __tablename__ = "style_training_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source_type: Mapped[str] = mapped_column(String(80), default="用户粘贴")
    source_hash: Mapped[str] = mapped_column(String(64))
    source_char_count: Mapped[int] = mapped_column(Integer)
    analysis: Mapped[Any] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(60))
    editorial_constitution_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StyleProfileVersion(Base):
    __tablename__ = "style_profile_versions"
    __table_args__ = (UniqueConstraint("version", name="uq_style_profile_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer)
    rules: Mapped[Any] = mapped_column(JSON)
    source_proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("style_training_proposals.id", ondelete="SET NULL")
    )
    source_diff_candidate_id: Mapped[str | None] = mapped_column(String(36))
    change_type: Mapped[str] = mapped_column(String(30), default="training")
    source_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EditorialConstitutionVersion(Base):
    __tablename__ = "editorial_constitution_versions"
    __table_args__ = (UniqueConstraint("version", name="uq_editorial_constitution_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version: Mapped[int] = mapped_column(Integer)
    sections: Mapped[Any] = mapped_column(JSON)
    change_type: Mapped[str] = mapped_column(String(30), default="manual_edit")
    source_version: Mapped[int | None] = mapped_column(Integer)
    change_note: Mapped[str] = mapped_column(String(500))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DiffMemoryCandidate(Base):
    __tablename__ = "diff_memory_candidates"
    __table_args__ = (UniqueConstraint("rule_hash", name="uq_diff_memory_rule_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pattern_type: Mapped[str] = mapped_column(String(50), index=True)
    rule_text: Mapped[str] = mapped_column(String(500))
    rule_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence: Mapped[Any] = mapped_column(JSON, default=list)
    profile_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("style_profile_versions.id", ondelete="SET NULL")
    )
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("content_id", name="uq_publication_content"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    content_id: Mapped[str] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), index=True)
    note_url: Mapped[str] = mapped_column(String(1000))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    final_title: Mapped[str] = mapped_column(String(240))
    final_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("content_versions.id", ondelete="SET NULL")
    )
    final_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    final_cover_path: Mapped[str | None] = mapped_column(String(1000))
    recommended_publish_time: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    content: Mapped[Content] = relationship(back_populates="publication")
    snapshots: Mapped[list["AnalyticsSnapshot"]] = relationship(
        back_populates="publication", cascade="all, delete-orphan", order_by="AnalyticsSnapshot.day_offset"
    )
    comments: Mapped[list["CommentRecord"]] = relationship(
        back_populates="publication", cascade="all, delete-orphan", order_by="CommentRecord.created_at"
    )


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (UniqueConstraint("publication_id", "day_offset", name="uq_publication_day_snapshot"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), index=True
    )
    day_offset: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metrics: Mapped[Any] = mapped_column(JSON, default=dict)
    calculated_rates: Mapped[Any] = mapped_column(JSON, default=dict)
    source_type: Mapped[str] = mapped_column(String(30), default="manual")
    note: Mapped[str | None] = mapped_column(Text)
    publication: Mapped[Publication] = relationship(back_populates="snapshots")


class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_type: Mapped[str] = mapped_column(String(20), index=True)
    publication_id: Mapped[str | None] = mapped_column(
        ForeignKey("publications.id", ondelete="SET NULL"), index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    input_snapshot_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(60))
    payload: Mapped[Any] = mapped_column(JSON, default=dict)
    confirmed_suggestion_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_note: Mapped[str | None] = mapped_column(String(1000))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommentRecord(Base):
    __tablename__ = "comment_records"
    __table_args__ = (UniqueConstraint("publication_id", "content_hash", name="uq_publication_comment_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), default="paste")
    source_ocr_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("ocr_runs.id", ondelete="SET NULL"), index=True
    )
    author_label: Mapped[str | None] = mapped_column(String(120))
    comment_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    publication: Mapped[Publication] = relationship(back_populates="comments")
    reply_suggestions: Mapped[list["CommentReplySuggestion"]] = relationship(
        back_populates="comment", cascade="all, delete-orphan", order_by="CommentReplySuggestion.created_at"
    )


class CommentReplySuggestion(Base):
    __tablename__ = "comment_reply_suggestions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    comment_id: Mapped[str] = mapped_column(
        ForeignKey("comment_records.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(60))
    payload: Mapped[Any] = mapped_column(JSON, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[CommentRecord] = relationship(back_populates="reply_suggestions")
