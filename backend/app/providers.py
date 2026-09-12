import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from .config import settings
from .models import ApiUsage, AppSetting
from .security import secret_store


class ProviderError(RuntimeError):
    pass


@dataclass
class ProviderResult:
    payload: dict[str, Any]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    content: str
    score: float


@dataclass(frozen=True)
class SearchResponse:
    query: str
    results: list[SearchHit]
    request_id: str | None = None
    usage_credits: int | None = None


@dataclass(frozen=True)
class TrendEvidence:
    platform: str
    title: str
    url: str
    snippet: str
    provider_score: float


@dataclass(frozen=True)
class TrendCollectionResult:
    evidence: list[TrendEvidence]
    query_count: int
    request_ids: list[str]
    usage_credits: int | None = None


class TrendSourceError(ProviderError):
    def __init__(self, message: str, partial_result: TrendCollectionResult) -> None:
        super().__init__(message)
        self.partial_result = partial_result


class LLMProvider(Protocol):
    async def generate_json(self, *, system_prompt: str, user_prompt: str, task_type: str) -> ProviderResult: ...


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, max_results: int = 5) -> SearchResponse: ...


class TrendSourceProvider(Protocol):
    name: str

    async def collect(self) -> TrendCollectionResult: ...


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        value = value.removeprefix("```json").removeprefix("```")
        if value.endswith("```"):
            value = value[:-3]
    return value.strip()


class DeepSeekProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def generate_json(self, *, system_prompt: str, user_prompt: str, task_type: str) -> ProviderResult:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0.8,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
                response.raise_for_status()
                data = response.json()
            content = data["choices"][0]["message"]["content"]
            payload = json.loads(_strip_json_fence(content))
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(f"DeepSeek 调用失败：{type(exc).__name__}") from exc
        usage = data.get("usage") or {}
        return ProviderResult(
            payload=payload,
            model=self.model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        query = query.strip()[:399]
        max_results = max(1, min(int(max_results), 5))
        if not query:
            raise ProviderError("Tavily 搜索词不能为空")
        if not self.api_key:
            raise ProviderError("尚未配置 Tavily API Key")
        data: dict[str, Any]
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.tavily_base_url.rstrip('/')}/search",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "query": query,
                        "search_depth": "basic",
                        "max_results": max_results,
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Tavily 调用失败：{type(exc).__name__}") from exc
        hits = [
            SearchHit(
                title=str(item.get("title") or "")[:240],
                url=str(item.get("url") or "")[:1000],
                content=str(item.get("content") or "")[:500],
                score=float(item.get("score") or 0),
            )
            for item in (data.get("results") or [])[:max_results]
            if isinstance(item, dict)
        ]
        usage = data.get("usage") or {}
        credits = usage.get("credits") if isinstance(usage, dict) else None
        return SearchResponse(
            query=query,
            results=hits,
            request_id=str(data["request_id"]) if data.get("request_id") else None,
            usage_credits=int(credits) if isinstance(credits, (int, float)) else None,
        )


def _trend_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "xiaohongshu.com" in host:
        return "小红书"
    if "douyin.com" in host:
        return "抖音"
    if "douban.com" in host:
        return "豆瓣"
    if "zhihu.com" in host:
        return "知乎"
    if "weibo.com" in host:
        return "微博"
    if host == "x.com" or host.endswith(".x.com") or "twitter.com" in host:
        return "X/Twitter"
    return "其他公开网页"


class TavilyTrendSourceProvider:
    name = "tavily"
    queries = (
        '(site:xiaohongshu.com OR site:douban.com OR site:zhihu.com) 女性 情感 关系 讨论',
        '(site:weibo.com OR site:douyin.com) 女性 情感 关系 讨论',
        '(site:x.com OR site:twitter.com) women relationships emotional discussion',
    )

    def __init__(self, search: SearchProvider) -> None:
        self.search = search

    async def collect(self) -> TrendCollectionResult:
        evidence: list[TrendEvidence] = []
        seen_urls: set[str] = set()
        request_ids: list[str] = []
        credits = 0
        completed = 0
        for query in self.queries:
            try:
                response = await self.search.search(query, max_results=5)
            except ProviderError as exc:
                raise TrendSourceError(
                    f"公开热点查询在第 {completed + 1} 条停止：{exc}",
                    TrendCollectionResult(
                        evidence=evidence[:15],
                        query_count=completed,
                        request_ids=request_ids,
                        usage_credits=credits or None,
                    ),
                ) from exc
            completed += 1
            if response.request_id:
                request_ids.append(response.request_id)
            if response.usage_credits is not None:
                credits += response.usage_credits
            for hit in response.results:
                if not hit.url or hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                evidence.append(
                    TrendEvidence(
                        platform=_trend_platform(hit.url),
                        title=hit.title,
                        url=hit.url,
                        snippet=hit.content,
                        provider_score=hit.score,
                    )
                )
        return TrendCollectionResult(
            evidence=evidence[:15],
            query_count=completed,
            request_ids=request_ids,
            usage_credits=credits or None,
        )


def get_app_setting(db: Session, key: str, default: Any = None) -> Any:
    record = db.get(AppSetting, key)
    return record.value if record else default


def build_llm_provider(db: Session) -> LLMProvider:
    api_key = secret_store.get("deepseek")
    if not api_key:
        raise ProviderError("尚未配置 DeepSeek API Key，请先完成首次配置。")
    model = str(get_app_setting(db, "deepseek_model", settings.deepseek_model))
    return DeepSeekProvider(api_key=api_key, model=model)


def build_search_provider() -> SearchProvider:
    api_key = secret_store.get("tavily")
    if not api_key:
        raise ProviderError("尚未配置 Tavily API Key")
    return TavilySearchProvider(api_key)


def build_trend_source_provider() -> TrendSourceProvider:
    return TavilyTrendSourceProvider(build_search_provider())


def record_usage(db: Session, content_id: str | None, task_type: str, result: ProviderResult) -> None:
    db.add(
        ApiUsage(
            content_id=content_id,
            provider="deepseek",
            task_type=task_type,
            model_name=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.input_tokens + result.output_tokens,
        )
    )
