"""Small synchronous Images API adapter. No automatic retries or vendor fallback."""
import asyncio
import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from .config import settings
from .models import AppSetting
from .security import secret_store


MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_RESPONSE_BYTES = 22 * 1024 * 1024


def is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not ip.is_multicast


class ImageProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def validate_https_url(value: str, *, base: bool = False) -> httpx.URL:
    try:
        url = httpx.URL(value)
        if (url.scheme != "https" or not url.host or url.userinfo or url.fragment
                or (base and url.query)):
            raise ValueError
        if url.host.lower() in {"localhost", "localhost.localdomain"} or url.host.endswith(".local"):
            raise ValueError
        try:
            address = ipaddress.ip_address(url.host)
        except ValueError:
            address = None
        if address and not is_public_address(str(address)):
            raise ValueError
        return url
    except (ValueError, httpx.InvalidURL) as exc:
        raise ValueError("请填写公网 HTTPS 地址，不支持内网、账号密码、片段或带查询参数的 Base URL。") from exc


class ImageConfiguration(BaseModel):
    enabled: bool = False
    base_url: str = Field(default="", max_length=1000)
    model: str = Field(default="", max_length=120)
    timeout_seconds: float = Field(default=180, ge=30, le=600)

    @field_validator("base_url", "model", mode="before")
    @classmethod
    def trim(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def check_base_url(cls, value: str) -> str:
        if value:
            url = validate_https_url(value, base=True)
            if url.path.rstrip("/").endswith("/images/generations"):
                raise ValueError("请填写 API 基础地址（例如以 /v1 结尾），不要包含 /images/generations。")
        return value.rstrip("/")

    @model_validator(mode="after")
    def require_configuration(self) -> "ImageConfiguration":
        if self.enabled and (not self.base_url or not self.model):
            raise ValueError("启用图像生成前请填写 API Base URL 和模型名称。")
        return self


class ImageSetupRequest(ImageConfiguration):
    api_key: str | None = Field(default=None, max_length=4096, repr=False)

    @field_validator("api_key")
    @classmethod
    def check_api_key(cls, value: str | None) -> str | None:
        if value and any(ord(char) < 32 or ord(char) > 126 for char in value):
            raise ValueError("密钥包含无效字符。")
        return value.strip() or None if value else None


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    size: str | None = Field(default=None, pattern=r"^[1-9]\d{1,4}x[1-9]\d{1,4}$")

    @field_validator("prompt", mode="before")
    @classmethod
    def trim_prompt(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


def image_configuration(db: Session) -> ImageConfiguration:
    row = db.get(AppSetting, "image_generation")
    return ImageConfiguration.model_validate(row.value if row else {
        "enabled": settings.image_generation_enabled, "base_url": settings.image_base_url,
        "model": settings.image_model, "timeout_seconds": settings.image_timeout_seconds,
    })


def image_key_binding(base_url: str, key: str | None) -> str:
    return hashlib.sha256(json.dumps([base_url, key], ensure_ascii=True).encode()).hexdigest()


def image_key_matches(db: Session, config: ImageConfiguration, key: str | None) -> bool:
    binding = db.get(AppSetting, "image_credential_binding")
    # Existing installations without a binding remain compatible until the next save.
    return binding is None or (isinstance(binding.value, str)
                               and hmac.compare_digest(binding.value, image_key_binding(config.base_url, key)))


def image_status(db: Session) -> dict:
    key = secret_store.get("image")
    error = None
    try:
        config = image_configuration(db)
        if not image_key_matches(db, config, key):
            error = "图像密钥与已保存配置不一致，请重新填写当前服务的密钥并保存。"
    except ValidationError:
        config = ImageConfiguration()
        error = "图像配置无效，已暂停生图；请重新填写服务地址、模型和密钥并保存。"
    return {**config.model_dump(), "key_configured": bool(key), "configuration_error": error,
            "available": not error and config.enabled and bool(key and config.base_url and config.model)}


@dataclass
class ImageResult:
    data: bytes
    model: str
    usage: dict | None = None


class ImageGenerationProvider(Protocol):
    async def generate(self, *, prompt: str, size: str | None = None) -> ImageResult: ...


async def public_address(host: str, port: int) -> str:
    """Resolve once, reject every non-public answer, then connect to the validated IP."""
    records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not is_public_address(ip) for ip in addresses):
        raise ImageProviderError("图片服务或下载地址指向非公网地址，已停止请求。")
    return next((ip for ip in addresses if ipaddress.ip_address(ip).version == 4), addresses[0])


class OpenAICompatibleImageProvider:
    def __init__(self, config: ImageConfiguration, api_key: str):
        self.config = config
        self._api_key = api_key

    async def _request(self, client: httpx.AsyncClient, method: str, url_value: str,
                       limit: int, *, payload: dict | None = None) -> tuple[int, httpx.Headers, bytes]:
        try:
            url = validate_https_url(url_value)
        except ValueError as exc:
            raise ImageProviderError("图片服务返回了不支持的下载地址。") from exc
        address = await public_address(url.host, url.port or 443)
        headers = {"Host": url.netloc.decode("ascii")}
        if payload is not None:
            # Authorization is used only for the configured generation endpoint.
            headers["Authorization"] = f"Bearer {self._api_key}"
        client.cookies.clear()
        async with client.stream(method, url.copy_with(host=address), headers=headers, json=payload,
                                 extensions={"sni_hostname": url.host}) as response:
            data = bytearray()
            if response.status_code == 200:
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ImageProviderError("服务返回的数据过大，图片不能超过 15 MB。")
            # Never surface or persist the upstream error body, URLs, or credentials.
            return response.status_code, response.headers, bytes(data)

    async def _download(self, client: httpx.AsyncClient, url: str) -> bytes:
        for redirects in range(4):
            status, headers, data = await self._request(client, "GET", url, MAX_IMAGE_BYTES)
            if status == 200:
                return data
            if status in {301, 302, 303, 307, 308} and headers.get("location") and redirects < 3:
                url = str(httpx.URL(url).join(headers["location"]))
                continue
            raise ImageProviderError("图片已生成，但下载失败。请检查服务后再手动生成，可能已产生费用。")
        raise ImageProviderError("图片下载跳转次数过多。")

    async def generate(self, *, prompt: str, size: str | None = None) -> ImageResult:
        payload = {"model": self.config.model, "prompt": prompt, "n": 1}
        if size:
            payload["size"] = size
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.config.timeout_seconds, connect=10),
                                             follow_redirects=False, trust_env=False,
                                             limits=httpx.Limits(max_keepalive_connections=0)) as client:
                    status, _, body = await self._request(client, "POST", f"{self.config.base_url}/images/generations",
                                                         MAX_RESPONSE_BYTES, payload=payload)
                    if status != 200:
                        messages = {
                            400: "图像服务拒绝了请求，请检查描述、模型名称或生成尺寸。",
                            401: "图像服务密钥无效，请在设置中检查。",
                            403: "图像服务拒绝访问，请检查模型权限或描述是否符合服务要求。",
                            404: "找不到图像接口或模型，请检查 Base URL 和模型名称。",
                            429: "图像服务限流或额度不足，请检查账户后手动重试。",
                        }
                        raise ImageProviderError(messages.get(status, f"图像服务返回异常（HTTP {status}），未自动重试。"))
                    result = json.loads(body)
                    items = result.get("data") if isinstance(result, dict) else None
                    item = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
                    if isinstance(item.get("b64_json"), str) and item["b64_json"]:
                        data = base64.b64decode(item["b64_json"], validate=True)
                    elif isinstance(item.get("url"), str) and item["url"]:
                        data = await self._download(client, item["url"])
                    else:
                        raise ImageProviderError("服务没有返回有效图片；请确认使用同步 Images 兼容接口。")
                    if not data or len(data) > MAX_IMAGE_BYTES:
                        raise ImageProviderError("返回图片为空或超过 15 MB。")
                    usage = result.get("usage")
                    return ImageResult(data, self.config.model, usage if isinstance(usage, dict) else None)
        except ImageProviderError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ImageProviderError("图像生成超时，上游可能已计费；未自动重试，请稍后检查服务记录。", 504) from exc
        except (json.JSONDecodeError, UnicodeDecodeError, binascii.Error) as exc:
            raise ImageProviderError("服务返回的图片数据无效，请检查接口兼容性。") from exc
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise ImageProviderError("无法连接图片服务或下载图片；请求结果可能未知，未自动重试。") from exc


def build_image_provider(db: Session) -> ImageGenerationProvider:
    try:
        config = image_configuration(db)
    except ValidationError as exc:
        raise ImageProviderError("图像配置无效，请在设置页重新填写服务地址、模型和密钥。", 400) from exc
    key = secret_store.get("image")
    if not image_key_matches(db, config, key):
        raise ImageProviderError("图像密钥与服务配置不一致，请重新填写当前服务的密钥并保存。", 400)
    if not config.enabled or not config.base_url or not config.model or not key:
        raise ImageProviderError("请先在设置页配置并启用图像生成服务。", 400)
    return OpenAICompatibleImageProvider(config, key)
