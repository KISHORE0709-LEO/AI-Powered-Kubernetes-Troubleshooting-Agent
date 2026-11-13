from fastapi import APIRouter

from app.models.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="healthy", service="ai-kubernetes-agent")
