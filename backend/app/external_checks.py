import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .memory_retrieval import ngram_similarity
from .models import Content, ContentVersion, ExternalCheckRun, ManualOriginalitySource
from .providers import ProviderError, SearchHit, SearchProvider
from .schemas import CitationVerificationItem, CitationVerificationReport, OriginalityReport


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _compact(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _article_fragments(version: ContentVersion) -> list[tuple[str, str]]:
    paragraphs = [_compact(item, 180) for item in re.split(r"[\r\n]+", version.body_text) if item.strip()]
    opening = _compact(version.body_text, 180)
    distinctive = max(paragraphs, key=len, default=opening)
    values = [("标题", _compact(version.title, 120)), ("开头", opening), ("正文特征句", distinctive)]
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for label, value in values:
        if value and value not in seen:
            seen.add(value)
            result.append((label, value))
    return result


def _match_hit(version: ContentVersion, label: str, fragment: str, hit: SearchHit) -> dict[str, Any] | None:
    title_similarity = SequenceMatcher(None, version.title, hit.title).ratio()
    fragment_similarity = max(
        ngram_similarity(fragment, hit.title),
        ngram_similarity(fragment, hit.content),
        SequenceMatcher(None, fragment[:300], hit.content[:300]).ratio(),
    )
    if title_similarity < 0.58 and fragment_similarity < 0.32:
        return None
    risk = "高" if title_similarity >= 0.84 or fragment_similarity >= 0.58 else "中"
    return {
        "source": label,
        "title": hit.title,
        "url": hit.url,
        "snippet": hit.content,
        "provider_score": round(hit.score, 3),
        "title_similarity": round(title_similarity, 3),
        "fragment_similarity": round(fragment_similarity, 3),
        "risk": risk,
    }


def _manual_matches(db: Session, content_id: str, version: ContentVersion) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources = list(
        db.scalars(
            select(ManualOriginalitySource)
            .where(ManualOriginalitySource.content_id == content_id)
            .order_by(ManualOriginalitySource.created_at.asc())
        )
    )
    matches: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for source in sources:
        if source.source_type == "url":
            coverage.append({"source": source.label, "status": "仅记录链接，未抓取正文", "source_type": "url"})
            continue
        title_similarity = SequenceMatcher(None, version.title, source.source_value[:240]).ratio()
        body_ngram = ngram_similarity(version.body_text, source.source_value)
        body_sequence = SequenceMatcher(None, version.body_text[:4000], source.source_value[:4000]).ratio()
        max_similarity = max(title_similarity, body_ngram, body_sequence)
        coverage.append({"source": source.label, "status": "已比对用户粘贴内容", "source_type": source.source_type})
        if max_similarity >= 0.32:
            matches.append(
                {
                    "source_id": source.id,
                    "label": source.label,
                    "source_type": source.source_type,
                    "title_similarity": round(title_similarity, 3),
                    "body_ngram_similarity": round(body_ngram, 3),
                    "body_sequence_similarity": round(body_sequence, 3),
                    "risk": "高" if max_similarity >= 0.58 else "中",
                }
            )
    return matches, coverage


async def enrich_originality_report(
    db: Session,
    content: Content,
    version: ContentVersion,
    local_report: OriginalityReport,
    search: SearchProvider | None,
) -> OriginalityReport:
    manual_matches, manual_coverage = _manual_matches(db, content.id, version)
    started = _now()
    if search is None:
        local_report.external_check_status = "unavailable"
        local_report.public_web_completed = False
        local_report.xiaohongshu_public_completed = False
        local_report.manual_matches = manual_matches
        local_report.coverage_details = [
            {"source": "本地历史版本", "status": "已完成"},
            *manual_coverage,
            {"source": "Tavily 可访问的公开网页", "status": "不可用：未配置 Tavily API Key"},
            {"source": "公开可访问的小红书网页", "status": "不可用：未配置 Tavily API Key"},
        ]
        local_report.uncovered_sources = ["Tavily 可访问的公开网页", "需要登录、验证码或非公开的小红书内容"]
        local_report.passes_gate = local_report.passes_gate and not any(item["risk"] == "高" for item in manual_matches)
        db.add(
            ExternalCheckRun(
                content_id=content.id,
                check_type="originality",
                provider="tavily",
                status="unavailable",
                query_count=0,
                covered_sources=["local_history", "manual_sources"],
                unavailable_sources=["public_web", "xiaohongshu_public"],
                result_summary={"manual_match_count": len(manual_matches)},
                request_ids=[],
                error_summary="未配置 Tavily API Key",
                started_at=started,
                ended_at=_now(),
            )
        )
        return local_report

    fragments = _article_fragments(version)
    queries = [(label, f'"{value}"') for label, value in fragments[:2]]
    queries.append(("公开小红书网页", f'site:xiaohongshu.com "{fragments[0][1]}"'))
    web_matches: list[dict[str, Any]] = []
    request_ids: list[str] = []
    credits = 0
    completed_labels: list[str] = []
    try:
        for label, query in queries[:3]:
            response = await search.search(query, max_results=5)
            completed_labels.append(label)
            if response.request_id:
                request_ids.append(response.request_id)
            if response.usage_credits is not None:
                credits += response.usage_credits
            fragment = next((value for source, value in fragments if source == label), fragments[0][1])
            for hit in response.results:
                match = _match_hit(version, label, fragment, hit)
                if match and not any(item["url"] == match["url"] for item in web_matches):
                    web_matches.append(match)
    except ProviderError as exc:
        local_report.external_check_status = "failed"
        local_report.public_web_completed = False
        local_report.xiaohongshu_public_completed = False
        local_report.external_error_summary = f"公网检查在第 {len(completed_labels) + 1} 个查询停止：{exc}"
        local_report.manual_matches = manual_matches
        local_report.coverage_details = [
            {"source": "本地历史版本", "status": "已完成"},
            *manual_coverage,
            {"source": "Tavily 可访问的公开网页", "status": "失败，未自动重试或切换来源"},
            {"source": "公开可访问的小红书网页", "status": "失败或未执行"},
        ]
        local_report.uncovered_sources = ["本次未完成的公开网页", "需要登录、验证码或非公开的小红书内容"]
        local_report.passes_gate = local_report.passes_gate and not any(item["risk"] == "高" for item in manual_matches)
        db.add(
            ExternalCheckRun(
                content_id=content.id,
                check_type="originality",
                provider=search.name,
                status="failed",
                query_count=len(completed_labels),
                usage_credits=credits or None,
                covered_sources=completed_labels,
                unavailable_sources=["remaining_public_web"],
                result_summary={"web_match_count": len(web_matches), "manual_match_count": len(manual_matches)},
                request_ids=request_ids,
                error_summary=str(exc)[:1000],
                started_at=started,
                ended_at=_now(),
            )
        )
        return local_report

    local_report.external_check_status = "completed"
    local_report.public_web_completed = True
    local_report.xiaohongshu_public_completed = True
    local_report.web_matches = web_matches
    local_report.manual_matches = manual_matches
    local_report.coverage_details = [
        {"source": "本地历史版本", "status": "已完成"},
        *manual_coverage,
        {"source": "Tavily 可访问的公开网页", "status": "已完成有限关键词检索"},
        {"source": "公开可访问的小红书网页", "status": "已完成 site:xiaohongshu.com 检索"},
    ]
    local_report.uncovered_sources = ["需要登录、验证码、客户端内或非公开的小红书内容", "搜索引擎尚未收录的网页"]
    high_external = any(item["risk"] == "高" for item in [*web_matches, *manual_matches])
    local_report.passes_gate = local_report.passes_gate and not high_external
    if high_external:
        local_report.suggestions.append("发现高相似公开或手工补充来源，请重构标题、场景和表达后重新检查。")
    db.add(
        ExternalCheckRun(
            content_id=content.id,
            check_type="originality",
            provider=search.name,
            status="completed",
            query_count=len(completed_labels),
            usage_credits=credits or None,
            covered_sources=["public_web", "xiaohongshu_public", "manual_sources"],
            unavailable_sources=["login_required_or_private_content", "unindexed_pages"],
            result_summary={"web_match_count": len(web_matches), "manual_match_count": len(manual_matches)},
            request_ids=request_ids,
            started_at=started,
            ended_at=_now(),
        )
    )
    return local_report


def _reference_terms(reference: dict[str, Any]) -> tuple[list[str], str]:
    fields = ["quote", "text", "work", "title", "author", "source"]
    terms = [_compact(str(reference.get(field) or ""), 100) for field in fields]
    terms = list(dict.fromkeys(term for term in terms if term))
    return terms, " ".join(terms)[:399]


async def verify_cultural_references(
    db: Session,
    content: Content,
    references: list[dict[str, Any]],
    search: SearchProvider | None,
    prior_error: str | None = None,
) -> CitationVerificationReport:
    started = _now()
    references = [item for item in references if isinstance(item, dict) and any(item.values())]
    if not references:
        return CitationVerificationReport(
            check_status="not_needed",
            provider=search.name if search else "tavily",
            query_count=0,
            coverage_note="本稿没有需要核验的作品名、作者或短引文。",
        )
    if prior_error:
        report = CitationVerificationReport(
            check_status="failed",
            provider=search.name if search else "tavily",
            query_count=0,
            items=[
                CitationVerificationItem(
                    reference=item,
                    status="unverified",
                    recommendation="前序公网检查失败后已停止全部外部请求；请人工核验，或删除确定性出处并改为个人化转述。",
                )
                for item in references
            ],
            coverage_note="前序公网检查失败，本次引用核验未继续请求，也未自动重试或切换来源。",
            error_summary=prior_error,
        )
        db.add(
            ExternalCheckRun(
                content_id=content.id,
                check_type="citation",
                provider=report.provider,
                status="failed",
                query_count=0,
                covered_sources=[],
                unavailable_sources=["citation_public_web"],
                result_summary={"reference_count": len(references)},
                request_ids=[],
                error_summary=prior_error[:1000],
                started_at=started,
                ended_at=_now(),
            )
        )
        return report
    if search is None:
        report = CitationVerificationReport(
            check_status="unavailable",
            provider="tavily",
            query_count=0,
            items=[
                CitationVerificationItem(
                    reference=item,
                    status="unverified",
                    recommendation="未找到可靠公开来源；提交前请删除引号与出处断言，改写为个人化转述。",
                )
                for item in references
            ],
            coverage_note="未配置 Tavily，文化引用没有完成公开来源核验。",
            error_summary="未配置 Tavily API Key",
        )
        db.add(
            ExternalCheckRun(
                content_id=content.id,
                check_type="citation",
                provider="tavily",
                status="unavailable",
                query_count=0,
                covered_sources=[],
                unavailable_sources=["public_web"],
                result_summary={"reference_count": len(references)},
                request_ids=[],
                error_summary=report.error_summary,
                started_at=started,
                ended_at=_now(),
            )
        )
        return report

    items: list[CitationVerificationItem] = []
    request_ids: list[str] = []
    credits = 0
    completed = 0
    try:
        for reference in references[:5]:
            terms, query = _reference_terms(reference)
            response = await search.search(query, max_results=5)
            completed += 1
            if response.request_id:
                request_ids.append(response.request_id)
            if response.usage_credits is not None:
                credits += response.usage_credits
            evidence: list[dict[str, Any]] = []
            best_count = 0
            for hit in response.results:
                haystack = f"{hit.title} {hit.content}".casefold()
                count = sum(term.casefold() in haystack for term in terms)
                if count:
                    evidence.append({"title": hit.title, "url": hit.url, "snippet": hit.content, "matched_terms": count})
                    best_count = max(best_count, count)
            required = len(terms)
            status = "verified" if terms and best_count >= required else "partially_verified" if best_count else "unverified"
            recommendation = (
                "公开结果支持该作品、作者或短引文信息；发布前仍建议打开证据链接人工复核。"
                if status == "verified"
                else "证据不足以确认完整出处；请去掉确定性出处表述，或改写为个人化转述。"
            )
            items.append(CitationVerificationItem(reference=reference, status=status, evidence=evidence[:3], recommendation=recommendation))
        unchecked_references = references[5:]
        items.extend(
            CitationVerificationItem(
                reference=reference,
                status="unverified",
                recommendation="单次最多联网核验 5 条；该条未发起外部请求，请人工核验或改为个人化转述。",
            )
            for reference in unchecked_references
        )
    except ProviderError as exc:
        for reference in references[completed:]:
            items.append(
                CitationVerificationItem(
                    reference=reference,
                    status="unverified",
                    recommendation="核验中途停止，未自动重试或切换来源；请删除确定性出处表述或人工核验。",
                )
            )
        report = CitationVerificationReport(
            check_status="failed",
            provider=search.name,
            query_count=completed,
            items=items,
            coverage_note=f"已完成 {completed}/{min(len(references), 5)} 条引用核验；失败后已停止。",
            error_summary=str(exc),
        )
        status = "failed"
    else:
        report = CitationVerificationReport(
            check_status="completed",
            provider=search.name,
            query_count=completed,
            items=items,
            coverage_note=(
                f"已联网核验 {completed} 条文化引用"
                f"；另有 {len(references) - completed} 条超过单次上限、未发起请求"
                if len(references) > completed
                else f"已联网核验 {completed} 条文化引用"
            )
            + "；结果仅覆盖搜索服务可访问的公开网页。",
        )
        status = "completed"
    db.add(
        ExternalCheckRun(
            content_id=content.id,
            check_type="citation",
            provider=search.name,
            status=status,
            query_count=completed,
            usage_credits=credits or None,
            covered_sources=["public_web"] if completed else [],
            unavailable_sources=(
                ["references_above_limit"]
                if status == "completed" and len(references) > completed
                else []
                if status == "completed"
                else ["remaining_references"]
            ),
            result_summary={"reference_count": len(references), "verified_count": sum(item.status == "verified" for item in items)},
            request_ids=request_ids,
            error_summary=report.error_summary,
            started_at=started,
            ended_at=_now(),
        )
    )
    return report
