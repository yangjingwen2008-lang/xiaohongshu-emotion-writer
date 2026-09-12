from pathlib import Path
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..providers import LLMProvider, ProviderError, build_llm_provider
from ..ocr import OCRProvider, OcrError, build_ocr_provider


def get_ocr_provider() -> OCRProvider:
    return build_ocr_provider()


def get_analytics_llm_provider(db: Session = Depends(get_db)) -> LLMProvider:
    try:
        return build_llm_provider(db)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _delete_ocr_image(path_value: str | None) -> None:
    if not path_value:
        return
    root = (settings.upload_dir / "ocr" / "pending").resolve()
    target = Path(path_value).resolve()
    if target.parent != root:
        raise OcrError("OCR 截图路径越界，已停止删除操作")
    if target.exists():
        target.unlink()


def _workflow_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _plugin_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))
