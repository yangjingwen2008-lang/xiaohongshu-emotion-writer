import hashlib
import html
import json
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .diff_memory import analyze_human_revision
from .editorial_constitution import current_constitution_payload
from .external_checks import enrich_originality_report, verify_cultural_references
from .memory_retrieval import (
    build_memory_fingerprint,
    generation_memory_report,
    index_version,
    ngram_similarity,
    search_versions,
)
from .models import Artifact, Content, ContentVersion, WorkflowRun, WorkflowStep
from .prompt_registry import PromptSpec, get_prompt
from .providers import LLMProvider, ProviderError, SearchProvider, build_llm_provider, build_search_provider, record_usage
from .schemas import AIToneReview, DetailQuestion, EssayDraft, NarrativePlanSet, OriginalityReport, RiskReport, StyleReview
from .style_training import current_profile


T = TypeVar("T", bound=BaseModel)


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class WorkflowError(RuntimeError):
    pass


_WORKFLOW_FIELD_LABELS = {
    "plans": "三套方案",
    "plan_id": "方案编号",
    "angle": "思想切口",
    "narrative_structure": "叙事结构",
    "scenes": "场景列表",
    "emotion_curve": "情绪曲线",
    "virtual_details": "虚构细节",
    "body": "正文",
    "alternate_titles": "备选标题",
    "core_tags": "核心标签",
    "trend_tags": "趋势标签",
    "long_tail_tags": "长尾标签",
    "cultural_references": "文化引用",
    "fictionality_notes": "虚构说明",
    "dimensions": "评价维度",
    "issues": "问题列表",
    "strengths": "风格优点",
    "summary": "审阅总结",
    "revised_body": "对比稿正文",
    "preserved_roughness": "保留的自然表达",
    "risks": "风险列表",
    "blocks_submission": "是否阻止提交",
}

_WORKFLOW_STEP_LABELS = {
    "plan_generation": "三套方案生成",
    "detail_enrichment": "细节问题生成",
    "draft_generation": "初稿生成",
    "style_review": "风格审阅",
    "ai_tone_review": "AI 味审阅",
    "risk_review": "风险审阅",
}


def friendly_workflow_validation_error(exc: ValidationError) -> str:
    issues: list[str] = []
    for error in exc.errors(include_url=False, include_input=False)[:6]:
        location = tuple(error.get("loc", ("未知字段",)))
        raw_field = next(
            (str(part) for part in location if str(part) in _WORKFLOW_FIELD_LABELS),
            str(location[-1]),
        )
        field = _WORKFLOW_FIELD_LABELS.get(raw_field, raw_field)
        error_type = str(error.get("type", ""))
        if error_type == "missing":
            issue = f"缺少“{field}”"
        elif error_type == "list_type":
            issue = f"“{field}”必须是列表"
        elif error_type in {"too_short", "string_too_short"}:
            issue = f"“{field}”内容不足"
        elif error_type in {"too_long", "string_too_long"}:
            issue = f"“{field}”内容过多"
        elif error_type == "value_error":
            issue = f"“{field}”未满足差异要求"
        else:
            issue = f"“{field}”格式不符合约定"
        if issue not in issues:
            issues.append(issue)
    return "、".join(issues) or "模型返回结构无法读取"


class WorkflowOrchestrator:
    def __init__(
        self,
        db: Session,
        llm: LLMProvider | None = None,
        search: SearchProvider | None = None,
        search_configured: bool | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        self.search = search
        self.search_configured = search_configured

    def _provider(self) -> LLMProvider:
        if self.llm is None:
            self.llm = build_llm_provider(self.db)
        return self.llm

    def _search_provider(self) -> SearchProvider | None:
        if self.search is not None:
            return self.search
        if settings.test_mode and self.search_configured is None:
            return None
        if self.search_configured is False:
            return None
        try:
            self.search = build_search_provider()
        except ProviderError:
            self.search_configured = False
            return None
        self.search_configured = True
        return self.search

    def _content(self, content_id: str) -> Content:
        content = self.db.get(Content, content_id)
        if not content:
            raise WorkflowError("文章不存在")
        return content

    def _latest_artifact(self, content_id: str, artifact_type: str) -> Artifact:
        artifact = self.db.scalar(
            select(Artifact)
            .where(Artifact.content_id == content_id, Artifact.artifact_type == artifact_type)
            .order_by(Artifact.version.desc())
            .limit(1)
        )
        if not artifact:
            raise WorkflowError(f"缺少前置产物：{artifact_type}")
        return artifact

    def _new_run(self, content_id: str) -> WorkflowRun:
        run = WorkflowRun(content_id=content_id)
        self.db.add(run)
        self.db.flush()
        return run

    def _artifact(
        self,
        *,
        content_id: str,
        run_id: str | None,
        step_id: str,
        artifact_type: str,
        payload: Any,
        source_ids: list[str],
        prompt_version: str | None,
        confirmed: bool = False,
    ) -> Artifact:
        version = self.db.scalar(
            select(func.count(Artifact.id)).where(
                Artifact.content_id == content_id, Artifact.artifact_type == artifact_type
            )
        ) or 0
        artifact = Artifact(
            content_id=content_id,
            run_id=run_id,
            step_id=step_id,
            artifact_type=artifact_type,
            version=version + 1,
            payload=payload,
            source_artifact_ids=source_ids,
            prompt_version=prompt_version,
            content_hash=canonical_hash(payload),
            confirmed=confirmed,
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact

    async def _agent_step(
        self,
        *,
        content: Content,
        step_id: str,
        prompt: PromptSpec,
        user_payload: Any,
        output_model: type[T],
        artifact_type: str,
        source_ids: list[str],
    ) -> Artifact:
        input_hash = canonical_hash({"step": step_id, "prompt": prompt.version, "input": user_payload})
        existing_step = self.db.scalar(
            select(WorkflowStep)
            .where(WorkflowStep.input_hash == input_hash, WorkflowStep.status == "success")
            .order_by(WorkflowStep.attempt_no.desc())
            .limit(1)
        )
        if existing_step and existing_step.output_artifact_id:
            existing = self.db.get(Artifact, existing_step.output_artifact_id)
            if existing:
                return existing

        attempt_no = (
            self.db.scalar(select(func.max(WorkflowStep.attempt_no)).where(WorkflowStep.input_hash == input_hash))
            or 0
        ) + 1
        run = self._new_run(content.id)
        step = WorkflowStep(
            run_id=run.id,
            content_id=content.id,
            step_id=step_id,
            status="running",
            input_artifact_ids=source_ids,
            prompt_version=prompt.version,
            tool_permissions=prompt.tool_whitelist,
            input_hash=input_hash,
            attempt_no=attempt_no,
            idempotency_key=canonical_hash({"input_hash": input_hash, "attempt_no": attempt_no}),
        )
        self.db.add(step)
        self.db.flush()
        result = None
        try:
            result = await self._provider().generate_json(
                system_prompt=prompt.system_prompt,
                user_prompt=json.dumps(user_payload, ensure_ascii=False),
                task_type=step_id,
            )
            validated = output_model.model_validate(result.payload)
            artifact = self._artifact(
                content_id=content.id,
                run_id=run.id,
                step_id=step_id,
                artifact_type=artifact_type,
                payload=validated.model_dump(mode="json"),
                source_ids=source_ids,
                prompt_version=prompt.version,
            )
            record_usage(self.db, content.id, step_id, result)
            step.status = "success"
            step.output_artifact_id = artifact.id
            step.input_tokens = result.input_tokens
            step.output_tokens = result.output_tokens
            step.ended_at = datetime.now(timezone.utc)
            run.status = "success"
            run.ended_at = step.ended_at
            self.db.commit()
            return artifact
        except ValidationError as exc:
            friendly = friendly_workflow_validation_error(exc)
            if result is not None:
                step.input_tokens = result.input_tokens
                step.output_tokens = result.output_tokens
                record_usage(self.db, content.id, step_id, result)
            step.status = "failed"
            step.error_summary = f"模型返回格式不正确：{friendly}"
            step.ended_at = datetime.now(timezone.utc)
            run.status = "failed"
            run.ended_at = step.ended_at
            self.db.commit()
            label = _WORKFLOW_STEP_LABELS.get(step_id, step_id)
            raise WorkflowError(f"{label}返回格式不正确：{friendly}。请重新点击当前步骤。") from exc
        except (ProviderError, ValueError) as exc:
            step.status = "failed"
            step.error_summary = str(exc)[:1000]
            step.ended_at = datetime.now(timezone.utc)
            run.status = "failed"
            run.ended_at = step.ended_at
            self.db.commit()
            raise WorkflowError(f"{step_id} 失败：{exc}") from exc

    async def generate_plans(self, content_id: str) -> Artifact:
        content = self._content(content_id)
        prompt = get_prompt("narrative_architect")
        constitution_version, constitution = current_constitution_payload(self.db)
        artifact = await self._agent_step(
            content=content,
            step_id="plan_generation",
            prompt=prompt,
            user_payload={
                "theme": content.theme,
                "emotion": content.emotion,
                "extra_requirements": content.extra_requirements,
                "editorial_constitution": {
                    "version": constitution_version,
                    "sections": constitution,
                },
            },
            output_model=NarrativePlanSet,
            artifact_type="NarrativePlanSet",
            source_ids=[],
        )
        content.current_step = "plan_selection"
        self.db.commit()
        return artifact

    def select_plan(self, content_id: str, plan_id: str) -> Artifact:
        content = self._content(content_id)
        plan_set = self._latest_artifact(content_id, "NarrativePlanSet")
        plans = plan_set.payload["plans"]
        selected = next((plan for plan in plans if plan["plan_id"] == plan_id), None)
        if not selected:
            raise WorkflowError("所选方案不存在")
        artifact = self._artifact(
            content_id=content.id,
            run_id=None,
            step_id="plan_selection",
            artifact_type="SelectedPlan",
            payload=selected,
            source_ids=[plan_set.id],
            prompt_version=None,
            confirmed=True,
        )
        plan_set.confirmed = True
        content.selected_plan_id = plan_id
        content.current_step = "detail_enrichment"
        self.db.commit()
        return artifact

    async def generate_detail_question(self, content_id: str) -> Artifact:
        content = self._content(content_id)
        selected = self._latest_artifact(content_id, "SelectedPlan")
        prompt = get_prompt("detail_curator")
        return await self._agent_step(
            content=content,
            step_id="detail_enrichment",
            prompt=prompt,
            user_payload={"selected_plan": selected.payload},
            output_model=DetailQuestion,
            artifact_type="DetailQuestion",
            source_ids=[selected.id],
        )

    def select_detail(self, content_id: str, mode: str, detail: str) -> Artifact:
        content = self._content(content_id)
        question = self._latest_artifact(content_id, "DetailQuestion")
        payload = {"mode": mode, "detail": detail}
        artifact = self._artifact(
            content_id=content.id,
            run_id=None,
            step_id="detail_enrichment",
            artifact_type="SelectedDetail",
            payload=payload,
            source_ids=[question.id],
            prompt_version=None,
            confirmed=True,
        )
        question.confirmed = True
        content.selected_detail = detail
        content.current_step = "draft_generation"
        self.db.commit()
        return artifact

    async def generate_draft(self, content_id: str) -> Artifact:
        content = self._content(content_id)
        selected_plan = self._latest_artifact(content_id, "SelectedPlan")
        selected_detail = self._latest_artifact(content_id, "SelectedDetail")
        prompt = get_prompt("essay_writer")
        profile = current_profile(self.db)
        constitution_version, constitution = current_constitution_payload(self.db)
        memory_report = generation_memory_report(self.db, content, profile)
        memory_report["editorial_constitution_version"] = constitution_version
        memory_report["editorial_constitution_sections"] = {
            key: len(value) for key, value in constitution.items()
        }
        memory_artifact = self._artifact(
            content_id=content.id,
            run_id=None,
            step_id="draft_generation",
            artifact_type="GenerationMemoryReport",
            payload=memory_report,
            source_ids=[],
            prompt_version="memory-retrieval-v1",
        )
        artifact = await self._agent_step(
            content=content,
            step_id="draft_generation",
            prompt=prompt,
            user_payload={
                "selected_plan": selected_plan.payload,
                "selected_detail": selected_detail.payload,
                "editorial_constitution": {
                    "version": constitution_version,
                    "sections": constitution,
                },
                "style_memory_used": memory_report["style_rules_used"],
                "historical_repetitions_to_avoid": memory_report["avoid_history"],
                "confirmed_analytics_experiments": memory_report["confirmed_analytics_experiments"],
                "retrieval_scope": memory_report["retrieval_scope"],
            },
            output_model=EssayDraft,
            artifact_type="EssayDraft",
            source_ids=[selected_plan.id, selected_detail.id, memory_artifact.id],
        )
        draft = EssayDraft.model_validate(artifact.payload)
        body_html = "".join(f"<p>{html.escape(p)}</p>" for p in draft.body.split("\n") if p.strip())
        draft_metadata = draft.model_dump(mode="json")
        draft_metadata["prompt_version"] = prompt.version
        self._save_version(content, draft.title, body_html, draft.body, "initial_draft", draft_metadata)
        content.title = draft.title
        content.current_step = "human_edit"
        self.db.commit()
        return artifact

    def _save_version(
        self, content: Content, title: str, body_html: str, body_text: str, kind: str, metadata: dict[str, Any]
    ) -> ContentVersion:
        max_version = self.db.scalar(
            select(func.max(ContentVersion.version)).where(ContentVersion.content_id == content.id)
        ) or 0
        safe_metadata = dict(metadata)
        safe_metadata.pop("body", None)
        constitution_version, _ = current_constitution_payload(self.db)
        profile = current_profile(self.db)
        safe_metadata["editorial_constitution_version"] = constitution_version
        safe_metadata["style_profile_version"] = profile.version if profile else 0
        safe_metadata["memory_fingerprint"] = build_memory_fingerprint(self.db, content, body_text)
        version = ContentVersion(
            content_id=content.id,
            version=max_version + 1,
            kind=kind,
            title=title,
            body_html=body_html,
            body_text=body_text,
            metadata_json=safe_metadata,
            content_hash=canonical_hash({"title": title, "body": body_text}),
        )
        self.db.add(version)
        self.db.flush()
        index_version(self.db, content, version)
        return version

    def save_human_edit(self, content_id: str, title: str, body_html: str, body_text: str) -> ContentVersion:
        content = self._content(content_id)
        source_draft = self._latest_artifact(content_id, "EssayDraft")
        version = self._save_version(
            content,
            title,
            body_html,
            body_text,
            "human_edit",
            {"source_prompt_version": source_draft.prompt_version},
        )
        content.title = title
        content.current_step = "human_edit"
        self.db.commit()
        self.db.refresh(version)
        return version

    def _latest_version(self, content_id: str) -> ContentVersion:
        version = self.db.scalar(
            select(ContentVersion)
            .where(ContentVersion.content_id == content_id)
            .order_by(ContentVersion.version.desc())
            .limit(1)
        )
        if not version:
            raise WorkflowError("尚无可审核正文")
        return version

    def _local_originality(self, content: Content, version: ContentVersion) -> OriginalityReport:
        candidates = search_versions(
            self.db,
            f"{version.title} {version.body_text}",
            exclude_content_id=content.id,
            limit=40,
        )
        matches: list[dict[str, Any]] = []
        max_body_ngram = 0.0
        max_body_sequence = 0.0
        max_title = 0.0
        max_opening = 0.0
        max_ending = 0.0
        max_scene_overlap = 0.0
        current_fingerprint = (version.metadata_json or {}).get("memory_fingerprint", {})
        current_scenes = set(current_fingerprint.get("scenes") or [])
        for candidate in candidates:
            body_ngram = ngram_similarity(version.body_text, candidate.body_text)
            body_sequence = SequenceMatcher(None, version.body_text[:4000], candidate.body_text[:4000]).ratio()
            title_ratio = SequenceMatcher(None, version.title, candidate.title).ratio()
            opening_ratio = ngram_similarity(version.body_text[:240], candidate.body_text[:240])
            ending_ratio = ngram_similarity(version.body_text[-240:], candidate.body_text[-240:])
            candidate_fingerprint = (candidate.metadata_json or {}).get("memory_fingerprint", {})
            candidate_scenes = set(candidate_fingerprint.get("scenes") or [])
            scene_overlap = (
                len(current_scenes & candidate_scenes) / len(current_scenes | candidate_scenes)
                if current_scenes and candidate_scenes else 0.0
            )
            max_body_ngram = max(max_body_ngram, body_ngram)
            max_body_sequence = max(max_body_sequence, body_sequence)
            max_title = max(max_title, title_ratio)
            max_opening = max(max_opening, opening_ratio)
            max_ending = max(max_ending, ending_ratio)
            max_scene_overlap = max(max_scene_overlap, scene_overlap)
            if body_ngram >= 0.25 or body_sequence >= 0.35 or title_ratio >= 0.65 or opening_ratio >= 0.45:
                matches.append(
                    {
                        "content_id": candidate.content_id,
                        "version": candidate.version,
                        "title": candidate.title,
                        "title_similarity": round(title_ratio, 3),
                        "body_ngram_similarity": round(body_ngram, 3),
                        "body_sequence_similarity": round(body_sequence, 3),
                        "opening_similarity": round(opening_ratio, 3),
                        "ending_similarity": round(ending_ratio, 3),
                        "scene_overlap": round(scene_overlap, 3),
                    }
                )
        passes = (
            max_body_ngram < 0.42
            and max_body_sequence < 0.55
            and max_title < 0.8
            and max_opening < 0.62
        )
        return OriginalityReport(
            local_history_completed=True,
            public_web_completed=False,
            xiaohongshu_public_completed=False,
            uncovered_sources=["公开网页（需 Tavily 并在下一阶段启用）", "需登录的小红书内容"],
            title_risk="高" if max_title >= 0.8 else "低",
            opening_risk=f"本地 FTS5 候选中的最高 n-gram 相似度 {max_opening:.1%}",
            structure_risk=f"正文 n-gram {max_body_ngram:.1%}；整体序列 {max_body_sequence:.1%}",
            metaphor_risk="检测中文字符 n-gram 和已保存意象标签；不宣称理解全部隐喻",
            scene_risk=f"已保存场景标签最高重合度 {max_scene_overlap:.1%}",
            ending_risk=f"结尾片段最高 n-gram 相似度 {max_ending:.1%}",
            matches=matches,
            suggestions=[] if passes else ["重新设计核心场景、结构与意象，不要只替换同义词"],
            passes_gate=passes,
        )

    async def run_quality_reviews(self, content_id: str) -> list[Artifact]:
        content = self._content(content_id)
        version = self._latest_version(content_id)
        profile = current_profile(self.db)
        constitution_version, constitution = current_constitution_payload(self.db)
        source = {
            "title": version.title,
            "body": version.body_text,
            "editorial_constitution": {
                "version": constitution_version,
                "sections": constitution,
            },
            "confirmed_style_profile": profile.rules if profile else None,
        }
        style = await self._agent_step(
            content=content,
            step_id="style_review",
            prompt=get_prompt("style_guardian"),
            user_payload=source,
            output_model=StyleReview,
            artifact_type="StyleReview",
            source_ids=[],
        )
        ai_tone = await self._agent_step(
            content=content,
            step_id="ai_tone_review",
            prompt=get_prompt("ai_tone_reviewer"),
            user_payload=source,
            output_model=AIToneReview,
            artifact_type="AIToneReview",
            source_ids=[style.id],
        )
        risk = await self._agent_step(
            content=content,
            step_id="risk_review",
            prompt=get_prompt("safety_platform_reviewer"),
            user_payload=source,
            output_model=RiskReport,
            artifact_type="RiskReport",
            source_ids=[style.id],
        )
        search = self._search_provider()
        originality_payload = await enrich_originality_report(
            self.db,
            content,
            version,
            self._local_originality(content, version),
            search,
        )
        originality = self._artifact(
            content_id=content.id,
            run_id=None,
            step_id="originality_review",
            artifact_type="OriginalityReport",
            payload=originality_payload.model_dump(mode="json"),
            source_ids=[],
            prompt_version="local-fts5-ngram+tavily-basic-v1",
        )
        draft = self._latest_artifact(content_id, "EssayDraft")
        article_text = f"{version.title}\n{version.body_text}"
        active_references = [
            reference
            for reference in list(draft.payload.get("cultural_references") or [])
            if isinstance(reference, dict)
            and any(
                str(reference.get(field) or "").strip() in article_text
                for field in ("quote", "text", "work", "title")
                if str(reference.get(field) or "").strip()
            )
        ]
        citation_payload = await verify_cultural_references(
            self.db,
            content,
            active_references,
            search,
            prior_error=originality_payload.external_error_summary
            if originality_payload.external_check_status == "failed"
            else None,
        )
        citation = self._artifact(
            content_id=content.id,
            run_id=None,
            step_id="citation_verification",
            artifact_type="CitationVerificationReport",
            payload=citation_payload.model_dump(mode="json"),
            source_ids=[draft.id],
            prompt_version="tavily-citation-verifier-v1",
        )
        unresolved_citations = [item for item in citation_payload.items if item.status != "verified"]
        if unresolved_citations:
            risk_payload = dict(risk.payload)
            risk_payload["risks"] = [
                *list(risk_payload.get("risks") or []),
                {
                    "category": "文化引用",
                    "level": "高",
                    "location": "文内文化引用",
                    "reason": f"有 {len(unresolved_citations)} 条引用未完成公开来源核实，不能作为确定性出处提交。",
                    "suggestion": "删除确定性出处，或改为个人化转述后重新运行质量门禁。",
                    "blocks_submission": True,
                },
            ]
            risk_payload["blocks_submission"] = True
            risk_payload["summary"] = (
                f"文化引用核验有 {len(unresolved_citations)} 条未通过，已阻止提交。"
                f"原安全审阅：{risk_payload.get('summary') or '无'}"
            )
            risk.payload = risk_payload
            risk.source_artifact_ids = [*list(risk.source_artifact_ids or []), citation.id]
            risk.content_hash = canonical_hash(risk_payload)
        content.current_step = "human_edit"
        self.db.commit()
        return [style, ai_tone, originality, citation, risk]

    def submit_review(self, content_id: str) -> Content:
        content = self._content(content_id)
        originality = self._latest_artifact(content_id, "OriginalityReport")
        risk = self._latest_artifact(content_id, "RiskReport")
        citation = self._latest_artifact(content_id, "CitationVerificationReport")
        self._latest_artifact(content_id, "AIToneReview")
        if not originality.payload.get("passes_gate"):
            raise WorkflowError("原创度门禁未通过")
        if risk.payload.get("blocks_submission"):
            raise WorkflowError("存在阻止提交的高风险项")
        unresolved_citations = [
            item for item in citation.payload.get("items", []) if item.get("status") != "verified"
        ]
        if unresolved_citations:
            raise WorkflowError("存在未核实或仅部分核实的文化引用，请删除确定性出处、改为个人化转述后重新运行质量门禁")
        final_version = self._latest_version(content_id)
        analyze_human_revision(self.db, content, final_version)
        content.status = "pending_review"
        content.current_step = "review_submission"
        self.db.commit()
        return content
