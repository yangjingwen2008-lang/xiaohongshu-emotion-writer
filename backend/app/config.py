import hashlib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "潮湿雨季"
    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = ROOT_DIR / "data"
    log_dir: Path = ROOT_DIR / "logs"
    export_dir: Path = ROOT_DIR / "exports"
    upload_dir: Path = ROOT_DIR / "uploads"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    tavily_base_url: str = "https://api.tavily.com"
    deepseek_api_key: str | None = None
    tavily_api_key: str | None = None
    image_generation_enabled: bool = False
    image_base_url: str = ""
    image_model: str = ""
    image_api_key: str | None = None
    image_timeout_seconds: float = 180.0
    request_timeout_seconds: float = 90.0
    test_mode: bool = False

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_prefix="XR_",
        extra="ignore",
    )

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.log_dir, self.export_dir, self.upload_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()


def instance_id() -> str:
    """Identify this checkout/data pair without exposing local filesystem paths."""
    value = f"{ROOT_DIR.resolve()}|{settings.data_dir.resolve()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
