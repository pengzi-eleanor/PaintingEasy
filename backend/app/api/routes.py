from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.knowledge.runtime import build_keyword_retriever
from app.models import (
    AnalyticsEventRequest,
    AnalyticsEventResponse,
    ImageAnalyzeResponse,
    ImageKeyword,
    ImageMetadata,
    ImageUploadResponse,
    SearchAssistRequest,
    SearchAssistResponse,
    TextOptimizeRequest,
    TextOptimizeResponse,
)
from app.models.schemas import KeywordSuggestion
from app.providers import (
    InMemoryUsageQuota,
    LocalImageStorageProvider,
    MockImageAnalyzeProvider,
    MockLanguageModelProvider,
)
from app.services import AnalyticsService, KeywordOptimizeService

router = APIRouter(prefix="/api")
analytics = AnalyticsService(settings=get_settings())
settings = get_settings()
image_storage = LocalImageStorageProvider(settings.image_upload_dir)
image_analyzer = MockImageAnalyzeProvider()
search_optimizer = KeywordOptimizeService(
    retriever=build_keyword_retriever(settings),
    llm_provider=MockLanguageModelProvider(),
    quota=InMemoryUsageQuota(settings.ai_smart_quota),
)


@router.post("/analytics/events", response_model=AnalyticsEventResponse)
async def track_event(payload: AnalyticsEventRequest) -> AnalyticsEventResponse:
    try:
        analytics.track(payload.event_name, payload.session_id, payload.payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AnalyticsEventResponse(success=True)


ALLOWED_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def matches_declared_image_type(content: bytes, content_type: str) -> bool:
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP",
    }
    return signatures.get(content_type, False)


@router.post("/images/upload", response_model=ImageUploadResponse)
async def upload_image(file: Annotated[UploadFile, File()]) -> ImageUploadResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            415,
            detail={
                "code": "UNSUPPORTED_IMAGE_TYPE",
                "message": "仅支持 jpg、jpeg、png、webp 格式图片",
            },
        )
    content = await file.read(MAX_IMAGE_BYTES + 1)
    await file.close()
    if not content:
        raise HTTPException(422, detail={"code": "EMPTY_IMAGE", "message": "图片文件不能为空"})
    if len(content) > settings.image_upload_max_size_mb * 1024 * 1024:
        raise HTTPException(
            413, detail={"code": "IMAGE_TOO_LARGE", "message": "图片大小不能超过 5MB"}
        )
    try:
        with Image.open(BytesIO(content)) as parsed:
            parsed.verify()
            width, height, fmt = parsed.width, parsed.height, parsed.format
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            422, detail={"code": "INVALID_IMAGE", "message": "图片损坏或无法解析"}
        ) from exc
    expected = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    if expected.get(fmt) != file.content_type:
        raise HTTPException(
            422, detail={"code": "INVALID_IMAGE", "message": "文件内容与图片类型不匹配"}
        )
    image_id = f"img_{uuid4().hex}"
    now = datetime.now(UTC)
    metadata = ImageMetadata(
        image_id=image_id,
        original_filename=file.filename or "image",
        stored_filename=f"{image_id}.{ALLOWED_IMAGE_TYPES[file.content_type]}",
        content_type=file.content_type,
        size=len(content),
        width=width,
        height=height,
        url=f"/uploads/{image_id}.{ALLOWED_IMAGE_TYPES[file.content_type]}",
        storage_path=str(
            Path(settings.image_upload_dir) / f"{image_id}.{ALLOWED_IMAGE_TYPES[file.content_type]}"
        ),
        created_at=now,
        expires_at=now + timedelta(hours=settings.image_expire_hours),
    )
    image_storage.save(content, metadata)
    return ImageUploadResponse(
        image_id=image_id,
        filename=metadata.original_filename,
        **metadata.model_dump(
            exclude={"image_id", "original_filename", "stored_filename", "storage_path", "status"}
        ),
    )


@router.post("/images/{image_id}/analyze", response_model=ImageAnalyzeResponse)
async def analyze_uploaded_image(
    image_id: str, platform: str | None = None, persona: str | None = None
) -> ImageAnalyzeResponse:
    image = image_storage.get(image_id)
    if not image:
        raise HTTPException(
            404, detail={"code": "IMAGE_NOT_FOUND", "message": "图片不存在或已过期"}
        )
    try:
        suggestions = image_analyzer.analyze(image, persona=persona, platform=platform)
    except Exception:
        suggestions = []
    candidates = [
        KeywordOptimizeService._candidate(item, index, image.original_filename)
        for index, item in enumerate(suggestions)
    ]
    return ImageAnalyzeResponse(
        image_id=image_id,
        provider="mock",
        is_ai_generated=False,
        degraded=True,
        suggestions=candidates,
        messages=["当前使用 mock 图片语义识别，未调用真实 AI API"],
    )


@router.post("/v1/search/assist", response_model=SearchAssistResponse)
async def assist_search(payload: SearchAssistRequest) -> SearchAssistResponse:
    return await run_in_threadpool(
        search_optimizer.optimize,
        payload.query,
        payload.persona,
        payload.platforms,
        payload.language,
        payload.optimization_mode,
        payload.network_expansion,
    )


@router.post("/text/optimize", response_model=TextOptimizeResponse)
async def optimize_text(payload: TextOptimizeRequest) -> TextOptimizeResponse:
    """Return deterministic mock keywords while preserving the original query."""
    return TextOptimizeResponse(
        original_query=payload.query,
        suggestions=[
            KeywordSuggestion(keyword=payload.query, category="general"),
            KeywordSuggestion(keyword="creative asset", category="style"),
            KeywordSuggestion(keyword="high quality", category="general"),
        ],
    )


@router.post("/image/analyze", response_model=ImageAnalyzeResponse)
async def analyze_image(image: Annotated[UploadFile, File()]) -> ImageAnalyzeResponse:
    """Validate an uploaded image and return deterministic mock semantics."""
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG and WebP images are supported.",
        )

    content = await image.read(MAX_IMAGE_BYTES + 1)
    await image.close()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image must not exceed 10 MB.",
        )
    if not matches_declared_image_type(content, image.content_type):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File content does not match its declared image type.",
        )

    return ImageAnalyzeResponse(
        filename=image.filename or "uploaded-image",
        keywords=[
            ImageKeyword(keyword="minimal workspace", category="scene", confidence=0.94),
            ImageKeyword(keyword="laptop", category="object", confidence=0.91),
            ImageKeyword(keyword="natural light", category="style", confidence=0.87),
            ImageKeyword(keyword="top view", category="composition", confidence=0.82),
        ],
    )
