from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api import router
from .config import ROOT_DIR, settings
from .database import Base, SessionLocal, engine
from .logging_config import configure_logging
from .local_access import DEV_ORIGINS, LocalAccessMiddleware
from .memory_retrieval import ensure_search_index_current
from .plugin_security import load_builtin_manifests, tool_registry
from . import models  # noqa: F401


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    settings.ensure_directories()
    load_builtin_manifests()
    tool_registry()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_search_index_current(db)
    yield


app = FastAPI(title="潮湿雨季 API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc: RequestValidationError):
    # Pydantic's default error includes raw input, including configuration secrets.
    return JSONResponse(status_code=422, content={"detail": [
        {key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()
    ]})


app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(DEV_ORIGINS),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LocalAccessMiddleware)
app.include_router(router)

frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    assets = frontend_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def frontend(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="接口不存在")
        candidate = frontend_dist / full_path
        if candidate.is_file() and frontend_dist in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")
