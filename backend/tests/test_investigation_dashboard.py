from collections.abc import Callable
from types import SimpleNamespace
from uuid import UUID

import pytest
import httpx
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.diagnosis import Diagnosis
from app.services.history import (
    HistoryAuthenticationError,
    InsForgeHistoryRepository,
)

INVESTIGATION_ID = UUID("93e314ca-e7f7-46fd-a82c-3029b4b8aa19")


def test_history_repository_uses_user_token_and_targets_record() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": str(INVESTIGATION_ID)}])
        return httpx.Response(200, json=[{"id": str(INVESTIGATION_ID)}])

    history = InsForgeHistoryRepository(
        "https://insforge.test",
        transport=httpx.MockTransport(handle),
    )
    try:
        history.authorize(INVESTIGATION_ID, "user-access-token")
        history.update(
            INVESTIGATION_ID,
            "user-access-token",
            {"phase": "checking_pods"},
        )
    finally:
        history.close()

    assert [request.method for request in requests] == ["GET", "PATCH"]
    assert all(
        request.headers["Authorization"] == "Bearer user-access-token"
        for request in requests
    )
    assert all(
        request.url.params["id"] == f"eq.{INVESTIGATION_ID}"
        for request in requests
    )
    assert requests[0].url.params["status"] == "eq.running"
    assert requests[0].url.params["phase"] == "eq.starting"
    assert requests[1].read() == b'{"phase":"checking_pods"}'


class FakeHistory:
    def __init__(self, *, authorization_error: bool = False) -> None:
        self.authorization_error = authorization_error
        self.authorized: list[tuple[UUID, str]] = []
        self.updates: list[dict[str, object]] = []
        self.closed = False

    def authorize(self, investigation_id: UUID, access_token: str) -> None:
        self.authorized.append((investigation_id, access_token))
        if self.authorization_error:
            raise HistoryAuthenticationError("Investigation record not owned.")

    def update(
        self,
        investigation_id: UUID,
        access_token: str,
        values: dict[str, object],
    ) -> None:
        self.updates.append(values)

    def close(self) -> None:
        self.closed = True


class SuccessfulInvestigation:
    def __init__(self, progress: list[str]) -> None:
        self.progress = progress

    def investigate(
        self,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        for phase in (
            "checking_pods",
            "reading_logs",
            "analyzing_events",
            "checking_networking",
            "inspecting_deployments",
        ):
            self.progress.append(phase)
            if on_progress:
                on_progress(phase)
        return {
            "status": "success",
            "investigation": {"pods": {"problematic_pods": []}},
        }


class FailedInvestigation:
    def investigate(
        self,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        if on_progress:
            on_progress("checking_pods")
        return {
            "status": "error",
            "investigation": {"pods": {"error": "kubectl unavailable"}},
        }


def configure_route(
    monkeypatch: pytest.MonkeyPatch,
    history: FakeHistory,
    service_factory: Callable[[], object],
) -> None:
    from app.api.routes import investigate as route

    monkeypatch.setattr(
        route,
        "get_settings",
        lambda: SimpleNamespace(insforge_url="https://insforge.test"),
    )
    monkeypatch.setattr(route, "InsForgeHistoryRepository", lambda _url: history)
    monkeypatch.setattr(route, "InvestigationService", service_factory)


@pytest.mark.anyio
async def test_investigate_requires_authenticated_user() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/investigate",
            json={"investigation_id": str(INVESTIGATION_ID)},
        )

    assert response.status_code == 401
    assert response.json()["status"] == "error"


@pytest.mark.anyio
async def test_investigate_rejects_history_record_not_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = FakeHistory(authorization_error=True)
    configure_route(monkeypatch, history, SuccessfulInvestigation)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/investigate",
            headers={"Authorization": "Bearer user-token"},
            json={"investigation_id": str(INVESTIGATION_ID)},
        )

    assert response.status_code == 401
    assert history.authorized == [(INVESTIGATION_ID, "user-token")]
    assert history.closed


@pytest.mark.anyio
async def test_investigate_publishes_progress_and_persists_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = FakeHistory()
    progress: list[str] = []
    configure_route(
        monkeypatch,
        history,
        lambda: SuccessfulInvestigation(progress),
    )

    class FakeAnalyzer:
        def analyze(self, _investigation: object) -> Diagnosis:
            return Diagnosis(
                root_cause="Image pull failed",
                explanation="The image could not be fetched.",
                fix="Check the image reference and registry access.",
                kubectl_command="kubectl describe pod app",
                prevention_recommendation="Validate image references in CI.",
                confidence=90,
                confidence_reasoning="Pod and event evidence agree.",
            )

    from app.api.routes import investigate as route

    monkeypatch.setattr(route, "RootCauseAnalyzer", FakeAnalyzer)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/investigate",
            headers={"Authorization": "Bearer user-token"},
            json={"investigation_id": str(INVESTIGATION_ID)},
        )

    assert response.status_code == 200
    assert response.json()["diagnosis"]["root_cause"] == "Image pull failed"
    assert progress == [
        "checking_pods",
        "reading_logs",
        "analyzing_events",
        "checking_networking",
        "inspecting_deployments",
    ]
    assert [update["phase"] for update in history.updates] == [
        *progress,
        "ai_reasoning",
        "root_cause_found",
    ]
    assert history.updates[-1]["status"] == "success"
    assert history.updates[-1]["confidence"] == 90
    assert history.closed


@pytest.mark.anyio
async def test_investigate_marks_history_failed_when_evidence_collection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = FakeHistory()
    configure_route(monkeypatch, history, FailedInvestigation)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/investigate",
            headers={"Authorization": "Bearer user-token"},
            json={"investigation_id": str(INVESTIGATION_ID)},
        )

    assert response.status_code == 503
    assert history.updates == [
        {"phase": "checking_pods"},
        {"status": "error", "phase": "failed"},
    ]
