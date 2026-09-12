import logging
from logging.handlers import RotatingFileHandler

from .config import settings
from .security import RedactingFilter


def configure_logging() -> None:
    settings.ensure_directories()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = RotatingFileHandler(
        settings.log_dir / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    # Signed image download URLs may contain credentials in their query string.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    root.addHandler(file_handler)
    root.addHandler(console)
