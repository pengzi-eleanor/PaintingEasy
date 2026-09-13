import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import image_storage, router
from app.config import get_settings
from app.models import HealthResponse

settings = get_settings()
upload_directory = Path(settings.image_upload_dir)
upload_directory.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    image_storage.cleanup_expired()
    stop = asyncio.Event()

    async def cleanup_images() -> None:
        interval = settings.image_cleanup_interval_minutes * 60
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                try:
                    await asyncio.to_thread(image_storage.cleanup_expired)
                except OSError:
                    logger.warning("scheduled image cleanup failed", exc_info=True)

    task = asyncio.create_task(cleanup_images())
    try:
        yield
    finally:
        stop.set()
        await task


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
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
    return {
        "service": settings.app_name,
        "message": "Use POST /api/v1/search/assist for keyword suggestions.",
    }


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


app.include_router(router)
