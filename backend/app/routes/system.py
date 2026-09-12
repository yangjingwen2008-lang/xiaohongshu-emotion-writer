from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..config import instance_id, settings
from ..database import get_db
from ..models import AppSetting
from ..providers import ProviderError, build_llm_provider, build_search_provider
from ..schemas import SetupRequest
from ..security import SecretStoreError, secret_store
from ..image_provider import ImageConfiguration, ImageSetupRequest, image_configuration, image_status, image_key_binding, image_key_matches
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError


router = APIRouter()


@router.get("/setup/image")
def get_image_setup(db: Session = Depends(get_db)) -> dict:
    return image_status(db)


@router.post("/setup/image")
def save_image_setup(payload: ImageSetupRequest, db: Session = Depends(get_db)) -> dict:
    try:
        previous = image_configuration(db)
    except ValidationError:
        previous = None
    old_key = secret_store.get("image")
    if (old_key and not payload.api_key and payload.base_url
            and (previous is None or (previous.base_url and previous.base_url != payload.base_url))):
        raise HTTPException(status_code=400, detail="更换图像服务地址时请重新填写密钥，避免向新服务发送原密钥。")
    if previous and not payload.api_key and not image_key_matches(db, previous, old_key):
        raise HTTPException(status_code=400, detail="图像密钥与服务配置不一致，请重新填写密钥后保存。")
    if payload.enabled and not (payload.api_key or old_key):
        raise HTTPException(status_code=400, detail="启用图像生成前请填写 API 密钥。")
    try:
        if payload.api_key:
            # Commit a guard before touching the independent credential store. If the
            # final DB commit fails, the new key cannot be sent to the old endpoint.
            if db.get(AppSetting, "image_credential_binding") is None:
                db.add(AppSetting(key="image_credential_binding",
                                  value=image_key_binding(previous.base_url if previous else "", old_key)))
                db.commit()
            secret_store.set("image", payload.api_key)
        config = ImageConfiguration.model_validate(payload.model_dump(exclude={"api_key"}))
        db.merge(AppSetting(key="image_generation", value=config.model_dump(), source="用户配置图像生成服务"))
        db.merge(AppSetting(key="image_credential_binding", value=image_key_binding(config.base_url, payload.api_key or old_key)))
        db.commit()
    except SecretStoreError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="图像配置保存未完成，请检查磁盘和数据库后，重新填写密钥并保存。") from exc
    return image_status(db)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "instance_id": instance_id()}


@router.get("/setup/status")
def setup_status(db: Session = Depends(get_db)) -> dict:
    model = db.get(AppSetting, "deepseek_model")
    price = db.get(AppSetting, "deepseek_price")
    return {
        "deepseek_configured": bool(secret_store.get("deepseek")),
        "tavily_configured": bool(secret_store.get("tavily")),
        "deepseek_model": model.value if model else settings.deepseek_model,
        "price": price.value if price else None,
        "price_source": price.source if price else None,
    }


@router.post("/setup")
def save_setup(payload: SetupRequest, db: Session = Depends(get_db)) -> dict[str, bool]:
    try:
        if payload.deepseek_api_key:
            secret_store.set("deepseek", payload.deepseek_api_key)
        if payload.tavily_api_key:
            secret_store.set("tavily", payload.tavily_api_key)
    except SecretStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.merge(
        AppSetting(
            key="deepseek_model",
            value=payload.deepseek_model,
            source="用户在首次配置页填写",
        )
    )
    if any(
        value is not None
        for value in (
            payload.input_cache_hit_price_per_million,
            payload.input_cache_miss_price_per_million,
            payload.output_price_per_million,
        )
    ):
        db.merge(
            AppSetting(
                key="deepseek_price",
                value={
                    "input_cache_hit": payload.input_cache_hit_price_per_million,
                    "input_cache_miss": payload.input_cache_miss_price_per_million,
                    "output": payload.output_price_per_million,
                    "unit": "USD / 1M tokens",
                },
                source=payload.price_source,
            )
        )
    db.commit()
    return {"saved": True}


@router.post("/setup/test/{provider}")
async def test_provider(provider: Literal["deepseek", "tavily"], db: Session = Depends(get_db)) -> dict:
    if provider == "deepseek":
        try:
            llm = build_llm_provider(db)
            result = await llm.generate_json(
                system_prompt="只输出 JSON 对象。",
                user_prompt='请输出 {"ok": true}。',
                task_type="connectivity_test",
            )
            return {"ok": result.payload.get("ok") is True, "model": result.model}
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        result = await build_search_provider().search("Tavily API connectivity test", max_results=1)
        return {"ok": True, "provider": "tavily", "request_id": result.request_id}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
