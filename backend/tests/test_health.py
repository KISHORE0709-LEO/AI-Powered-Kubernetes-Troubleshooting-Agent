import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_health_returns_expected_payload() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "ai-kubernetes-agent",
    }


@pytest.mark.anyio
async def test_health_allows_frontend_origin() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
