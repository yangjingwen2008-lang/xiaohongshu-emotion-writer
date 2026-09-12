"""Limit this unauthenticated desktop service to local hosts and trusted browser origins."""
import ipaddress
import socket
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from .config import settings

DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}


def _local_host(host: str) -> bool:
    name = socket.gethostname().lower()
    if host in {"localhost", name, f"{name}.local"}:
        return True
    if settings.test_mode and host == "testserver":
        return True
    try:
        address = ipaddress.ip_address(host)
        return (address.is_loopback or address.is_private) and not (address.is_unspecified or address.is_multicast)
    except ValueError:
        return False


def _origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("Invalid origin")
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


class LocalAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            try:
                if len(headers.getlist("host")) != 1:
                    raise ValueError("Invalid host")
                destination = _origin(f"{scope['scheme']}://{headers['host']}")
                if not _local_host(destination[1]):
                    raise ValueError("Non-local host")
            except ValueError:
                await JSONResponse({"detail": "请使用本机地址或局域网地址访问工作台"}, status_code=400)(scope, receive, send)
                return
            try:
                origin = headers.get("origin")
                if origin is not None:
                    if len(headers.getlist("origin")) != 1:
                        raise ValueError("Multiple origins")
                    if origin not in DEV_ORIGINS and _origin(origin) != destination:
                        raise ValueError("Untrusted origin")
                elif headers.get("sec-fetch-site", "").lower() == "cross-site":
                    raise ValueError("Cross-site request")
            except ValueError:
                await JSONResponse({"detail": "已拒绝来自其他网站的工作台请求"}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
