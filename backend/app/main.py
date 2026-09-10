from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes import router
from app.config import get_settings
from app.models import HealthResponse

settings = get_settings()
upload_directory = Path(settings.image_upload_dir)
upload_directory.mkdir(parents=True, exist_ok=True)
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=str(upload_directory)), name="uploads")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "message": "Use POST /api/v1/search/assist for keyword suggestions."}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


app.include_router(router)
