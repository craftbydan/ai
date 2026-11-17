from fastapi import APIRouter

from hwai.config import get_settings
from hwai.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", renderer=settings.renderer, ocr=settings.ocr)
