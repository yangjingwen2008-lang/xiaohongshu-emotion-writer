import logging
import re
from dataclasses import dataclass

import keyring
from keyring.errors import KeyringError

from .config import settings


SERVICE_NAME = "潮湿雨季-API凭据"
SECRET_NAMES = {"deepseek": "deepseek_api_key", "tavily": "tavily_api_key", "image": "image_api_key"}


class SecretStoreError(RuntimeError):
    pass


@dataclass
class SecretStore:
    def get(self, provider: str) -> str | None:
        username = SECRET_NAMES[provider]
        try:
            value = keyring.get_password(SERVICE_NAME, username)
        except KeyringError:
            value = None
        if value:
            return value
        return getattr(settings, username, None)

    def set(self, provider: str, value: str) -> None:
        try:
            keyring.set_password(SERVICE_NAME, SECRET_NAMES[provider], value)
        except KeyringError as exc:
            raise SecretStoreError("Windows 凭据管理器不可用，请改用项目根目录 .env。") from exc


class RedactingFilter(logging.Filter):
    patterns = [
        re.compile(r"(?i)(api[_-]?key|authorization|token|cookie|password)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+"),
        re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
        re.compile(r"tvly-[A-Za-z0-9_-]{12,}"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self.patterns:
            message = pattern.sub("[已脱敏]", message)
        record.msg = message
        record.args = ()
        return True


secret_store = SecretStore()
