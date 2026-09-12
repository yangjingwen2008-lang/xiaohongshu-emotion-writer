import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContentCreate(BaseModel):
    theme: str = Field(min_length=1, max_length=240)
    emotion: str = Field(min_length=1, max_length=120)
    extra_requirements: str | None = Field(default=None, max_length=2000)


class ContentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    theme: str
    emotion: str
    title: str | None
    status: str
    current_step: str
    updated_at: datetime


class TrendScoutCandidate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    trend_signal: Literal["正在讨论", "持续讨论", "数据不足"]
    trend_basis: str = Field(min_length=4, max_length=600)
    confidence: Literal["低", "中", "高"]
    data_limitations: str = Field(min_length=2, max_length=500)


class TrendScoutResult(BaseModel):
    candidates: list[TrendScoutCandidate] = Field(default_factory=list, max_length=8)
    data_status: Literal["sufficient", "data_insufficient"]
    summary: str = Field(min_length=2, max_length=500)

    @model_validator(mode="before")
    @classmethod
    def derive_data_status(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized = dict(value)
            candidates = normalized.get("candidates")
            count = len(candidates) if isinstance(candidates, list) else 0
            normalized["data_status"] = "sufficient" if 3 <= count <= 8 else "data_insufficient"
            return normalized
        return value


class TopicStrategyCandidate(BaseModel):
    scout_candidate_index: int = Field(ge=0, le=7)
    title: str = Field(min_length=2, max_length=120)
    emotion: str = Field(min_length=1, max_length=120)
    female_emotional_angle: str = Field(min_length=4, max_length=600)
    account_fit: Literal["低", "中", "高"]
    homogeneity_risk: Literal["低", "中", "高"]
    cultural_association: str | None = Field(default=None, max_length=400)
    rewrite_logic: str = Field(min_length=4, max_length=600)


class TopicStrategyResult(BaseModel):
    candidates: list[TopicStrategyCandidate] = Field(default_factory=list, max_length=8)
    data_status: Literal["sufficient", "data_insufficient"]

    @model_validator(mode="before")
    @classmethod
    def derive_data_status(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized = dict(value)
            candidates = normalized.get("candidates")
            count = len(candidates) if isinstance(candidates, list) else 0
            normalized["data_status"] = "sufficient" if 3 <= count <= 8 else "data_insufficient"
            return normalized
        return value


class ManualTrendSourceCreate(BaseModel):
    source_type: Literal["topic", "url"]
    label: str = Field(min_length=1, max_length=240)
    source_value: str = Field(min_length=1, max_length=4000)
    confirm: bool


class ManualTrendSourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_type: str
    label: str
    source_value: str
    created_at: datetime


class OcrRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    purpose: str
    status: str
    provider: str
    original_filename: str
    media_type: str
    image_size_bytes: int
    width: int
    height: int
    recognized_text: str | None
    corrected_text: str | None
    lines: list[str]
    engine_metadata: dict[str, Any]
    retention_policy: str
    linked_manual_trend_source_id: str | None
    linked_analytics_snapshot_id: str | None
    error_summary: str | None
    created_at: datetime
    confirmed_at: datetime | None
    deleted_at: datetime | None


class OcrConfirmRequest(BaseModel):
    label: str = Field(min_length=1, max_length=240)
    corrected_text: str = Field(min_length=1, max_length=12000)
    confirm: bool


class TrendCandidateView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    title: str
    emotion: str
    source_ids: list[str]
    source_platforms: list[str]
    source_links: list[dict[str, Any]]
    trend_signal: str
    trend_basis: str
    female_emotional_angle: str
    account_fit: str
    homogeneity_risk: str
    cultural_association: str | None
    confidence: str
    data_limitations: str
    rewrite_logic: str
    used_content_id: str | None
    selected_at: datetime | None
    created_at: datetime


class TrendRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    trigger: str
    status: str
    provider: str
    query_count: int
    usage_credits: int | None
    source_count: int
    candidate_count: int
    data_status: str
    error_summary: str | None
    started_at: datetime
    ended_at: datetime | None


class ConfirmationRequest(BaseModel):
    confirm: bool


class NarrativePlan(BaseModel):
    plan_id: str
    title: str
    angle: str
    opening_example: str
    core_view: str
    narrative_structure: list[str] = Field(min_length=1)
    scenes: list[str] = Field(min_length=1)
    emotion_curve: list[str] = Field(min_length=1)
    cultural_association: str | None = None
    potential_risk: str
    detail_question: str

    @field_validator("narrative_structure", "emotion_curve", mode="before")
    @classmethod
    def split_sequence_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        parts = [
            part.strip(" \t\r\n0123456789.。！？、；;-—：（）()")
            for part in re.split(r"(?:\r?\n)+|\s*(?:→|⇒|->|；|;)\s*|(?<=[。！？])\s*", value)
        ]
        return [part for part in parts if part]

    @field_validator("scenes", mode="before")
    @classmethod
    def split_scene_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        parts = [
            part.strip(" \t\r\n0123456789.。！？、；;-—：（）()")
            for part in re.split(r"(?:\r?\n)+|\s*(?:→|⇒|->|；|;|、)\s*", value)
        ]
        return [part for part in parts if part]


class NarrativePlanSet(BaseModel):
    plans: list[NarrativePlan] = Field(min_length=3, max_length=3)

    @field_validator("plans")
    @classmethod
    def plans_are_distinct(cls, value: list[NarrativePlan]) -> list[NarrativePlan]:
        if len({plan.plan_id.strip() for plan in value}) != 3:
            raise ValueError("三个方案的 plan_id 必须不同")
        if len({plan.angle.strip() for plan in value}) != 3:
            raise ValueError("三个方案的思想切口必须不同")
        return value


class PlanSelection(BaseModel):
    plan_id: str


class DetailQuestion(BaseModel):
    question: str
    virtual_details: list[str] = Field(min_length=3, max_length=3)


class DetailSelection(BaseModel):
    mode: Literal["real", "fictional"]
    detail: str = Field(min_length=1, max_length=1200)


class EssayDraft(BaseModel):
    title: str
    body: str
    alternate_titles: list[str] = Field(min_length=2, max_length=2)
    core_tags: list[str]
    trend_tags: list[str]
    long_tail_tags: list[str]
    pinned_comment: str
    cover_copy: str = Field(max_length=18)
    recommended_publish_time: str
    recommendation_basis: str
    recommendation_confidence: Literal["低", "中", "高"]
    cultural_references: list[dict[str, Any]] = Field(default_factory=list)
    fictionality_notes: list[str] = Field(default_factory=list)

    @field_validator("alternate_titles", "core_tags", "trend_tags", "long_tail_tags", mode="before")
    @classmethod
    def normalize_short_string_lists(cls, value: Any) -> Any:
        """Accept the common case where a model serializes a short list as text."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        parts = []
        for part in re.split(r"(?:\r?\n)+|\s*[、，,；;]\s*|(?<!\S)#", text):
            part = re.sub(r"^\s*(?:[-*•]+|\d+[.)、])\s*", "", part)
            parts.append(part.strip(" \t\r\n#，,；;：:-"))
        return [part for part in parts if part]

    @field_validator("cultural_references", mode="before")
    @classmethod
    def normalize_cultural_references(cls, value: Any) -> Any:
        """Keep references verifiable even when the model returns plain text items."""
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"[]", "无", "没有", "无引用", "none", "null", "n/a"}:
                return []
            value = [text]
        if not isinstance(value, list):
            return value
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, dict):
                if any(str(part or "").strip() for part in item.values()):
                    normalized.append(item)
            elif isinstance(item, str):
                text = item.strip()
                if text and text.lower() not in {"无", "没有", "无引用", "none", "null", "n/a"}:
                    normalized.append({"text": text})
            else:
                normalized.append(item)
        return normalized

    @field_validator("fictionality_notes", mode="before")
    @classmethod
    def normalize_fictionality_notes(cls, value: Any) -> Any:
        if value is None:
            return []
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text or text.lower() in {"[]", "无", "没有", "无虚构", "none", "null", "n/a"}:
            return []
        return [text]


class ReviewDimension(BaseModel):
    name: str
    rating: Literal["低", "中", "高"]
    evidence: str


class StyleReview(BaseModel):
    dimensions: list[ReviewDimension]
    issues: list[dict[str, str]]
    strengths: list[str]
    summary: str

    @model_validator(mode="before")
    @classmethod
    def normalize_style_review_container(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        expected = {"dimensions", "issues", "strengths", "summary"}
        normalized = dict(value)
        if not expected.intersection(normalized):
            nested_candidates = [
                item
                for item in normalized.values()
                if isinstance(item, dict) and expected.intersection(item)
            ]
            if len(nested_candidates) == 1:
                normalized = dict(nested_candidates[0])
            elif len(normalized) == 1:
                only_value = next(iter(normalized.values()))
                if isinstance(only_value, dict):
                    normalized = dict(only_value)
        aliases = {
            "评价维度": "dimensions",
            "维度评价": "dimensions",
            "问题": "issues",
            "问题列表": "issues",
            "优点": "strengths",
            "优势": "strengths",
            "总结": "summary",
        }
        for source, target in aliases.items():
            if target not in normalized and source in normalized:
                normalized[target] = normalized[source]
        return normalized

    @field_validator("strengths", mode="before")
    @classmethod
    def normalize_strengths(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return value


class AIToneReview(BaseModel):
    issues: list[dict[str, str]]
    revised_body: str
    preserved_roughness: list[str]
    summary: str

    @model_validator(mode="before")
    @classmethod
    def normalize_ai_tone_container(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        expected = {"issues", "revised_body", "preserved_roughness", "summary"}
        normalized = dict(value)
        if not expected.intersection(normalized) and len(normalized) == 1:
            only_value = next(iter(normalized.values()))
            if isinstance(only_value, dict):
                normalized = dict(only_value)
        return normalized

    @field_validator("preserved_roughness", mode="before")
    @classmethod
    def normalize_preserved_roughness(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"[]", "无", "没有", "none", "null", "n/a"}:
                return []
            return [text]
        return value


class RiskItem(BaseModel):
    category: str
    level: Literal["低", "中", "高"]
    location: str
    reason: str
    suggestion: str
    blocks_submission: bool = False


class RiskReport(BaseModel):
    risks: list[RiskItem]
    blocks_submission: bool
    summary: str

    @model_validator(mode="before")
    @classmethod
    def normalize_risk_report_container(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        expected = {"risks", "blocks_submission", "summary"}
        normalized = dict(value)
        if not expected.intersection(normalized) and len(normalized) == 1:
            only_value = next(iter(normalized.values()))
            if isinstance(only_value, dict):
                normalized = dict(only_value)
        aliases = {
            "风险": "risks",
            "风险项": "risks",
            "是否阻止提交": "blocks_submission",
            "阻止提交": "blocks_submission",
            "总结": "summary",
        }
        for source, target in aliases.items():
            if target not in normalized and source in normalized:
                normalized[target] = normalized[source]
        return normalized


class OriginalityReport(BaseModel):
    local_history_completed: bool
    public_web_completed: bool
    xiaohongshu_public_completed: bool
    uncovered_sources: list[str]
    title_risk: str
    opening_risk: str
    structure_risk: str
    metaphor_risk: str
    scene_risk: str
    ending_risk: str
    matches: list[dict[str, Any]]
    suggestions: list[str]
    passes_gate: bool
    external_check_status: Literal["completed", "unavailable", "failed"] = "unavailable"
    coverage_details: list[dict[str, Any]] = Field(default_factory=list)
    web_matches: list[dict[str, Any]] = Field(default_factory=list)
    manual_matches: list[dict[str, Any]] = Field(default_factory=list)
    external_error_summary: str | None = None


class CitationVerificationItem(BaseModel):
    reference: dict[str, Any]
    status: Literal["verified", "partially_verified", "unverified"]
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: str


class CitationVerificationReport(BaseModel):
    check_status: Literal["completed", "not_needed", "unavailable", "failed"]
    provider: str
    query_count: int
    items: list[CitationVerificationItem] = Field(default_factory=list)
    coverage_note: str
    error_summary: str | None = None


class DraftUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    body_html: str = Field(min_length=1)
    body_text: str = Field(min_length=1)


class ManualOriginalitySourceCreate(BaseModel):
    source_type: Literal["url", "title", "body"]
    label: str = Field(min_length=1, max_length=240)
    source_value: str = Field(min_length=1, max_length=20000)
    confirm: bool


class ManualOriginalitySourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    content_id: str
    source_type: str
    label: str
    source_value: str
    created_at: datetime


class SubmitReviewRequest(BaseModel):
    confirm: bool


class CoverRenderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    template: Literal["whitespace", "magazine", "subtitle"] = "whitespace"
    copy_text: str | None = Field(default=None, alias="copy", max_length=18)
    focus_x: float = Field(default=0.5, ge=0, le=1)
    focus_y: float = Field(default=0.5, ge=0, le=1)
    zoom: float = Field(default=1.0, ge=1, le=3)
    output_width: int = Field(default=900, ge=450, le=2160)
    output_height: int = Field(default=1200, ge=600, le=2880)


class StyleTrainingRequest(BaseModel):
    article: str = Field(min_length=200, max_length=20000)
    source_type: str = Field(default="用户粘贴", min_length=1, max_length=80)


class StyleFeature(BaseModel):
    dimension: str
    observation: str
    preference: str
    imitation_risk: str


class StyleTrainingAnalysis(BaseModel):
    features: list[StyleFeature] = Field(min_length=5)
    preferred_patterns: list[str]
    avoid_patterns: list[str]
    imagery_tendencies: list[str]
    rhythm_summary: str
    ending_summary: str
    ai_tone_risks: list[str]
    test_text: str
    privacy_note: str

    @model_validator(mode="after")
    def require_chinese_feedback(self):
        texts: list[tuple[str, str]] = []
        for index, feature in enumerate(self.features, start=1):
            texts.extend(
                [
                    (f"第 {index} 项维度", feature.dimension),
                    (f"第 {index} 项观察", feature.observation),
                    (f"第 {index} 项偏好", feature.preference),
                    (f"第 {index} 项模仿风险", feature.imitation_risk),
                ]
            )
        for field_name in ("preferred_patterns", "avoid_patterns", "imagery_tendencies", "ai_tone_risks"):
            texts.extend((field_name, item) for item in getattr(self, field_name))
        texts.extend(
            [
                ("节奏总结", self.rhythm_summary),
                ("结尾总结", self.ending_summary),
                ("原创测试短文", self.test_text),
                ("隐私说明", self.privacy_note),
            ]
        )
        for label, value in texts:
            chinese_count = len(re.findall(r"[\u4e00-\u9fff]", value))
            latin_count = len(re.findall(r"[A-Za-z]", value))
            if chinese_count == 0 or latin_count > chinese_count * 2:
                raise ValueError(f"{label}必须以简体中文为主，不能返回整段英文")
        return self


class StyleTrainingProposalView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    source_type: str
    source_char_count: int
    analysis: Any
    prompt_version: str
    editorial_constitution_version: int
    created_at: datetime
    decided_at: datetime | None


class StyleProfileView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    version: int
    rules: Any
    change_type: str = "initial"
    source_version: int | None = None
    created_at: datetime | None = None


class StyleProfileUpdateRequest(BaseModel):
    core_rules: list[str] = Field(min_length=1, max_length=30)
    manual_preferences: list[str] = Field(default_factory=list, max_length=30)
    manual_avoid_patterns: list[str] = Field(default_factory=list, max_length=30)
    confirm: bool

    @field_validator("core_rules", "manual_preferences", "manual_avoid_patterns")
    @classmethod
    def clean_profile_rules(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("风格规则不能重复")
        return cleaned


class StyleProfileRollbackRequest(BaseModel):
    confirm: bool


class EditorialConstitutionSections(BaseModel):
    core_principles: list[str] = Field(min_length=1, max_length=30)
    title_structure_rules: list[str] = Field(min_length=1, max_length=30)
    ai_tone_prohibitions: list[str] = Field(min_length=1, max_length=30)
    evaluation_dimensions: list[str] = Field(min_length=1, max_length=30)

    @field_validator(
        "core_principles",
        "title_structure_rules",
        "ai_tone_prohibitions",
        "evaluation_dimensions",
    )
    @classmethod
    def clean_constitution_rules(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("编辑宪法同一分区内不能有重复规则")
        return cleaned


class EditorialConstitutionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    version: int
    sections: EditorialConstitutionSections
    change_type: str = "initial"
    source_version: int | None = None
    change_note: str = "文档内置初始编辑宪法"
    confirmed_at: datetime | None = None
    created_at: datetime | None = None


class EditorialConstitutionUpdateRequest(BaseModel):
    sections: EditorialConstitutionSections
    change_note: str = Field(min_length=2, max_length=500)
    confirm: bool


class EditorialConstitutionRollbackRequest(BaseModel):
    confirm: bool


class DiffMemoryCandidateView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    pattern_type: str
    rule_text: str
    status: str
    occurrence_count: int
    evidence: list[dict[str, Any]]
    profile_version_id: str | None
    first_observed_at: datetime
    last_observed_at: datetime
    decided_at: datetime | None


class DiffMemoryDecisionRequest(BaseModel):
    confirm: bool


class PublicationCreateRequest(BaseModel):
    note_url: str = Field(min_length=8, max_length=1000)
    published_at: datetime | None = None
    confirm: bool


class AnalyticsMetrics(BaseModel):
    views: int | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    favorites: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    new_followers: int | None = Field(default=None, ge=0)
    profile_visits: int | None = Field(default=None, ge=0)
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    average_read_seconds: float | None = Field(default=None, ge=0)
    follower_view_ratio: float | None = Field(default=None, ge=0, le=1)
    non_follower_view_ratio: float | None = Field(default=None, ge=0, le=1)
    extra_metrics: dict[str, float | int] = Field(default_factory=dict)


class AnalyticsOcrConfirmRequest(BaseModel):
    corrected_text: str = Field(min_length=1, max_length=20000)
    metrics: AnalyticsMetrics
    note: str | None = Field(default=None, max_length=1000)
    confirm: bool


class AnalyticsSnapshotCreateRequest(BaseModel):
    day_offset: Literal[1, 3, 7]
    metrics: AnalyticsMetrics
    note: str | None = Field(default=None, max_length=1000)
    confirm: bool


class AnalyticsSnapshotView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    publication_id: str
    day_offset: int
    captured_at: datetime
    metrics: Any
    calculated_rates: Any
    source_type: str
    note: str | None


class PublicationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    content_id: str
    note_url: str
    published_at: datetime
    final_title: str
    final_version_id: str | None
    final_tags: list[str]
    final_cover_path: str | None
    recommended_publish_time: str | None
    created_at: datetime
    snapshots: list[AnalyticsSnapshotView] = Field(default_factory=list)


class DueSnapshotView(BaseModel):
    publication_id: str
    content_id: str
    final_title: str
    day_offset: Literal[1, 3, 7]
    due_at: datetime
    overdue_days: int


class AnalyticsReportEvidence(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    finding: str = Field(min_length=4, max_length=600)
    snapshot_ids: list[str] = Field(min_length=1, max_length=12)
    confidence: Literal["低", "中", "高"]
    caveat: str = Field(min_length=2, max_length=500)


class AnalyticsReportSuggestion(BaseModel):
    suggestion_id: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    applies_to: Literal["标题", "开头", "结构", "场景", "结尾", "发布时间", "标签", "封面"]
    experiment: str = Field(min_length=4, max_length=500)
    rationale: str = Field(min_length=4, max_length=600)
    evidence_snapshot_ids: list[str] = Field(min_length=1, max_length=12)
    confidence: Literal["低", "中", "高"]


class RetrospectiveReport(BaseModel):
    report_scope: Literal["single", "weekly", "monthly"]
    sample_size: int = Field(ge=1)
    period_summary: str = Field(min_length=4, max_length=600)
    observations: list[AnalyticsReportEvidence] = Field(min_length=1, max_length=8)
    correlations_not_causes: list[str] = Field(default_factory=list, max_length=8)
    suggestions: list[AnalyticsReportSuggestion] = Field(default_factory=list, max_length=5)
    preserve_identity: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(min_length=1, max_length=8)
    conclusion: str = Field(min_length=4, max_length=800)

    @field_validator("suggestions")
    @classmethod
    def suggestion_ids_are_unique(
        cls, value: list[AnalyticsReportSuggestion]
    ) -> list[AnalyticsReportSuggestion]:
        ids = [item.suggestion_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("复盘建议 ID 不能重复")
        return value


class AnalyticsReportGenerateRequest(BaseModel):
    report_type: Literal["single", "weekly", "monthly"]
    publication_id: str | None = None
    period_start: date | None = None
    period_end: date | None = None


class AnalyticsReportDecisionRequest(BaseModel):
    selected_suggestion_ids: list[str] = Field(min_length=1, max_length=5)
    note: str | None = Field(default=None, max_length=1000)
    confirm: bool

    @field_validator("selected_suggestion_ids")
    @classmethod
    def selected_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("不能重复选择同一条建议")
        return value


class AnalyticsReportDismissRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)
    confirm: bool


class AnalyticsReportView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    report_type: str
    publication_id: str | None
    period_start: datetime
    period_end: datetime
    status: str
    input_snapshot_ids: list[str]
    model_name: str | None
    prompt_version: str
    payload: Any
    confirmed_suggestion_ids: list[str]
    decision_note: str | None
    error_summary: str | None
    created_at: datetime
    completed_at: datetime | None
    decided_at: datetime | None


class CommentInput(BaseModel):
    author_label: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=2000)


class CommentBatchCreateRequest(BaseModel):
    comments: list[CommentInput] = Field(min_length=1, max_length=50)
    confirm: bool


class CommentOcrConfirmRequest(BaseModel):
    corrected_text: str = Field(min_length=1, max_length=20000)
    comments: list[CommentInput] = Field(min_length=1, max_length=50)
    confirm: bool


class CommentReplyPayload(BaseModel):
    reply_text: str = Field(min_length=1, max_length=300)
    tone: Literal["温柔共情", "简短克制", "轻微幽默", "轻微自嘲"]
    safety_note: str = Field(min_length=2, max_length=400)


class CommentReplyGenerateRequest(BaseModel):
    confirm_send_to_model: bool


class CommentReplySuggestionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    comment_id: str
    status: str
    model_name: str | None
    prompt_version: str
    payload: Any
    error_summary: str | None
    created_at: datetime
    completed_at: datetime | None


class CommentRecordView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    publication_id: str
    source_type: str
    source_ocr_run_id: str | None
    author_label: str | None
    comment_text: str
    created_at: datetime
    reply_suggestions: list[CommentReplySuggestionView] = Field(default_factory=list)


class SetupRequest(BaseModel):
    deepseek_api_key: str | None = None
    tavily_api_key: str | None = None
    deepseek_model: str = Field(min_length=1, max_length=120)
    input_cache_hit_price_per_million: float | None = Field(default=None, ge=0)
    input_cache_miss_price_per_million: float | None = Field(default=None, ge=0)
    output_price_per_million: float | None = Field(default=None, ge=0)
    price_source: str | None = None


class ArtifactView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    artifact_type: str
    step_id: str
    version: int
    payload: Any
    confirmed: bool
    created_at: datetime


class ContentDetail(ContentSummary):
    extra_requirements: str | None
    selected_plan_id: str | None
    selected_detail: str | None
    artifacts: list[ArtifactView]
