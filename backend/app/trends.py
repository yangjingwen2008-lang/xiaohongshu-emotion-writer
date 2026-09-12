import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .editorial_constitution import current_constitution_payload
from .models import (
    Content,
    ManualTrendSource,
    TrendCandidate,
    TrendRefreshRun,
    TrendSourceRecord,
)
from .prompt_registry import get_prompt
from .providers import (
    LLMProvider,
    ProviderError,
    TrendCollectionResult,
    TrendSourceError,
    TrendSourceProvider,
    build_llm_provider,
    build_trend_source_provider,
    record_usage,
)
from .schemas import TopicStrategyResult, TrendScoutResult


class TrendError(RuntimeError):
    def __init__(self, message: str, run_id: str | None = None) -> None:
        super().__init__(message)
        self.run_id = run_id


_TREND_FIELD_LABELS = {
    "candidates": "候选列表",
    "data_status": "数据状态",
    "source_ids": "来源编号",
    "trend_signal": "讨论状态",
    "confidence": "可信度",
    "scout_candidate_index": "线索编号",
    "account_fit": "账号匹配度",
    "homogeneity_risk": "同质化风险",
}


def friendly_trend_validation_error(exc: ValidationError) -> str:
    issues: list[str] = []
    for error in exc.errors(include_url=False, include_input=False)[:5]:
        raw_field = str(error.get("loc", ("未知字段",))[-1])
        field = _TREND_FIELD_LABELS.get(raw_field, raw_field)
        error_type = str(error.get("type", ""))
        if error_type == "missing":
            issue = f"缺少“{field}”"
        elif error_type == "literal_error":
            issue = f"“{field}”使用了不允许的值"
        elif error_type in {"string_too_short", "too_short"}:
            issue = f"“{field}”内容过短"
        elif error_type in {"string_too_long", "too_long"}:
            issue = f"“{field}”内容过长"
        else:
            issue = f"“{field}”格式不符合约定"
        if issue not in issues:
            issues.append(issue)
    return "、".join(issues) or "模型返回结构无法读取"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def scheduled_idempotency_key(now: datetime | None = None) -> str:
    local_now = (now or datetime.now().astimezone()).astimezone()
    slot = "09:00" if local_now.hour < 15 else "20:00"
    return f"scheduled:{local_now.date().isoformat()}:{slot}"


def cleanup_expired_trend_data(db: Session, now: datetime | None = None) -> dict[str, int]:
    cutoff = (now or utcnow()) - timedelta(days=30)
    expired_runs = list(
        db.scalars(
            select(TrendRefreshRun).where(
                TrendRefreshRun.started_at < cutoff,
                ~exists(
                    select(TrendCandidate.id).where(
                        TrendCandidate.run_id == TrendRefreshRun.id,
                        TrendCandidate.used_content_id.is_not(None),
                    )
                ),
            )
        )
    )
    for run in expired_runs:
        db.delete(run)
    db.flush()

    retained_manual_ids = set(
        db.scalars(
            select(TrendSourceRecord.manual_source_id)
            .join(TrendCandidate, TrendCandidate.run_id == TrendSourceRecord.run_id)
            .where(
                TrendSourceRecord.manual_source_id.is_not(None),
                TrendCandidate.used_content_id.is_not(None),
            )
        )
    )
    expired_manual = list(
        db.scalars(select(ManualTrendSource).where(ManualTrendSource.created_at < cutoff))
    )
    removed_manual = 0
    for source in expired_manual:
        if source.id not in retained_manual_ids:
            db.delete(source)
            removed_manual += 1
    db.commit()
    return {"runs": len(expired_runs), "manual_sources": removed_manual}


def create_manual_trend_source(
    db: Session,
    *,
    source_type: str,
    label: str,
    source_value: str,
) -> ManualTrendSource:
    normalized = source_value.strip()
    record = ManualTrendSource(
        source_type=source_type,
        label=label.strip(),
        source_value=normalized,
        content_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


class TrendService:
    def __init__(
        self,
        db: Session,
        *,
        llm: LLMProvider | None = None,
        source_provider: TrendSourceProvider | None = None,
        source_configured: bool | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        self.source_provider = source_provider
        self.source_configured = source_configured

    def _provider(self) -> TrendSourceProvider | None:
        if self.source_provider is not None:
            return self.source_provider
        if self.source_configured is False:
            return None
        try:
            self.source_provider = build_trend_source_provider()
        except ProviderError:
            self.source_configured = False
            return None
        self.source_configured = True
        return self.source_provider

    def _llm(self) -> LLMProvider:
        if self.llm is None:
            self.llm = build_llm_provider(self.db)
        return self.llm

    async def _agent(self, prompt_id: str, payload: dict[str, Any], output_model: type[Any]) -> Any:
        prompt = get_prompt(prompt_id)
        result = await self._llm().generate_json(
            system_prompt=prompt.system_prompt,
            user_prompt=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            task_type=prompt_id,
        )
        parsed = output_model.model_validate(result.payload)
        record_usage(self.db, None, prompt_id, result)
        return parsed

    async def refresh(self, trigger: str = "manual", now: datetime | None = None) -> TrendRefreshRun:
        cleanup_expired_trend_data(self.db, now=now)
        key = scheduled_idempotency_key(now) if trigger == "scheduled" else f"manual:{uuid4()}"
        existing = self.db.scalar(select(TrendRefreshRun).where(TrendRefreshRun.idempotency_key == key))
        if existing:
            return existing

        provider = self._provider()
        run = TrendRefreshRun(
            trigger=trigger,
            status="running",
            idempotency_key=key,
            provider=provider.name if provider else "manual_only",
            data_status="data_insufficient",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        try:
            collection = await provider.collect() if provider else TrendCollectionResult([], 0, [], None)
            run.query_count = collection.query_count
            run.usage_credits = collection.usage_credits
            run.request_ids = collection.request_ids
            for item in collection.evidence:
                self.db.add(
                    TrendSourceRecord(
                        run_id=run.id,
                        source_type="public_search",
                        platform=item.platform,
                        title=item.title or "无标题公开结果",
                        url=item.url,
                        snippet=item.snippet,
                        provider_score=f"{item.provider_score:.3f}",
                    )
                )

            manual_sources = list(
                self.db.scalars(
                    select(ManualTrendSource)
                    .order_by(ManualTrendSource.created_at.desc())
                    .limit(20)
                )
            )
            for item in manual_sources:
                self.db.add(
                    TrendSourceRecord(
                        run_id=run.id,
                        manual_source_id=item.id,
                        source_type="manual_input",
                        platform="用户手工补充",
                        title=item.label,
                        url=item.source_value if item.source_type == "url" else None,
                        snippet=item.source_value if item.source_type == "topic" else "用户仅提供公开链接，未抓取页面正文。",
                    )
                )
            self.db.flush()
            sources = list(
                self.db.scalars(
                    select(TrendSourceRecord)
                    .where(TrendSourceRecord.run_id == run.id)
                    .order_by(TrendSourceRecord.collected_at.asc())
                )
            )
            run.source_count = len(sources)
            self.db.commit()

            if not sources:
                run.status = "completed"
                run.data_status = "data_insufficient"
                run.error_summary = "未配置可用公开来源，且没有手工补充话题或链接。"
                run.ended_at = utcnow()
                self.db.commit()
                return run

            source_payload = [
                {
                    "source_id": item.id,
                    "platform": item.platform,
                    "title": item.title,
                    "url": item.url,
                    "snippet": item.snippet,
                    "collected_at": item.collected_at.isoformat(),
                    "source_type": item.source_type,
                }
                for item in sources
            ]
            scout = await self._agent(
                "trend_scout",
                {
                    "sources": source_payload,
                    "rules": {
                        "candidate_range": "3-8，证据不足时允许更少或为空",
                        "forbidden": ["伪造热度", "把搜索结果数量当平台热度", "补写来源中没有的事实"],
                    },
                },
                TrendScoutResult,
            )
            source_map = {item.id: item for item in sources}
            scout_candidates = []
            for item in scout.candidates:
                valid_ids = [source_id for source_id in item.source_ids if source_id in source_map]
                if valid_ids:
                    item.source_ids = valid_ids
                    scout_candidates.append(item)

            if not scout_candidates:
                run.status = "completed"
                run.data_status = "data_insufficient"
                run.error_summary = scout.summary
                run.ended_at = utcnow()
                self.db.commit()
                return run

            constitution_version, constitution = current_constitution_payload(self.db)
            strategy = await self._agent(
                "topic_strategist",
                {
                    "trend_candidates": [item.model_dump(mode="json") for item in scout_candidates],
                    "editorial_constitution": {"version": constitution_version, "sections": constitution},
                    "rules": {
                        "candidate_range": "3-8，宁可减少，不得硬凑",
                        "private_angle_only": True,
                        "avoid_real_person_judgment": True,
                    },
                },
                TopicStrategyResult,
            )
            created = 0
            used_indexes: set[int] = set()
            for topic in strategy.candidates:
                if topic.scout_candidate_index >= len(scout_candidates) or topic.scout_candidate_index in used_indexes:
                    continue
                used_indexes.add(topic.scout_candidate_index)
                evidence = scout_candidates[topic.scout_candidate_index]
                evidence_sources = [source_map[source_id] for source_id in evidence.source_ids]
                self.db.add(
                    TrendCandidate(
                        run_id=run.id,
                        title=topic.title,
                        emotion=topic.emotion,
                        source_ids=evidence.source_ids,
                        source_platforms=list(dict.fromkeys(item.platform for item in evidence_sources)),
                        source_links=[
                            {"title": item.title, "url": item.url, "platform": item.platform}
                            for item in evidence_sources
                            if item.url
                        ],
                        trend_signal=evidence.trend_signal,
                        trend_basis=evidence.trend_basis,
                        female_emotional_angle=topic.female_emotional_angle,
                        account_fit=topic.account_fit,
                        homogeneity_risk=topic.homogeneity_risk,
                        cultural_association=topic.cultural_association,
                        confidence=evidence.confidence,
                        data_limitations=evidence.data_limitations,
                        rewrite_logic=topic.rewrite_logic,
                    )
                )
                created += 1
                if created >= 8:
                    break
            run.candidate_count = created
            run.data_status = "sufficient" if 3 <= created <= 8 else "data_insufficient"
            run.status = "completed"
            run.error_summary = None if created else "来源存在，但没有形成可核查的候选选题。"
            run.ended_at = utcnow()
            self.db.commit()
            return run
        except TrendSourceError as exc:
            self.db.rollback()
            saved_run = self.db.get(TrendRefreshRun, run.id)
            if saved_run:
                partial = exc.partial_result
                for item in partial.evidence:
                    self.db.add(
                        TrendSourceRecord(
                            run_id=saved_run.id,
                            source_type="public_search_partial",
                            platform=item.platform,
                            title=item.title or "无标题公开结果",
                            url=item.url,
                            snippet=item.snippet,
                            provider_score=f"{item.provider_score:.3f}",
                        )
                    )
                saved_run.query_count = partial.query_count
                saved_run.usage_credits = partial.usage_credits
                saved_run.request_ids = partial.request_ids
                saved_run.source_count = len(partial.evidence)
                saved_run.status = "failed"
                saved_run.error_summary = str(exc)[:1000]
                saved_run.ended_at = utcnow()
                self.db.commit()
            raise TrendError(f"热点刷新失败，已保存前序有限摘要并停止，未自动重试：{exc}", run.id) from exc
        except ValidationError as exc:
            self.db.rollback()
            saved_run = self.db.get(TrendRefreshRun, run.id)
            friendly = friendly_trend_validation_error(exc)
            if saved_run:
                saved_run.status = "failed"
                saved_run.error_summary = (
                    f"热点模型返回格式不正确：{friendly}。已保留 {saved_run.source_count} 条有限来源摘要，"
                    "未生成候选；本次已停止且未自动重试。"
                )
                saved_run.ended_at = utcnow()
                self.db.commit()
            raise TrendError(
                f"热点模型返回格式不正确：{friendly}。已停止且未自动重试。",
                run.id,
            ) from exc
        except (ProviderError, TrendError) as exc:
            self.db.rollback()
            saved_run = self.db.get(TrendRefreshRun, run.id)
            if saved_run:
                saved_run.status = "failed"
                saved_run.error_summary = str(exc)[:1000]
                saved_run.ended_at = utcnow()
                self.db.commit()
            raise TrendError(f"热点刷新失败，已停止且未自动重试：{exc}", run.id) from exc


def use_trend_candidate(db: Session, candidate_id: str) -> Content:
    candidate = db.get(TrendCandidate, candidate_id)
    if not candidate:
        raise TrendError("热点候选不存在")
    if candidate.used_content_id:
        content = db.get(Content, candidate.used_content_id)
        if content:
            return content
    content = Content(
        theme=candidate.title,
        emotion=candidate.emotion,
        extra_requirements=(
            f"热点只作为私人情绪入口，不复刻原热点标题。\n"
            f"女性情感角度：{candidate.female_emotional_angle}\n"
            f"改写逻辑：{candidate.rewrite_logic}\n"
            f"趋势依据：{candidate.trend_basis}\n"
            f"数据边界：{candidate.data_limitations}"
        ),
    )
    db.add(content)
    db.flush()
    candidate.used_content_id = content.id
    candidate.selected_at = utcnow()
    db.commit()
    db.refresh(content)
    return content
