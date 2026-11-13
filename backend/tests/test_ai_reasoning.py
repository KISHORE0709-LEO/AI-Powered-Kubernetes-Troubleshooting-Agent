import json
from collections.abc import Callable

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.client import AIConfigurationError, AIServiceError, OpenRouterClient
from app.ai.prompt_builder import PromptBuilder
from app.ai.reasoning import RootCauseAnalyzer
from app.core.config import Settings
from app.main import app
from app.models.diagnosis import Diagnosis


class FakeHistory:
    def authorize(self, _investigation_id: object, _access_token: str) -> None:
        pass

    def update(
        self,
        _investigation_id: object,
        _access_token: str,
        _values: dict[str, object],
    ) -> None:
        pass

    def close(self) -> None:
        pass


def valid_model_result() -> dict[str, object]:
    return {
        "root_cause": "The payment pod is restarting after a failed startup.",
        "explanation": "The pod is in CrashLoopBackOff and its logs show a startup error.",
        "fix": "Correct the application configuration in the Deployment.",
        "kubectl_command": "kubectl edit deployment payment-service -n default",
        "prevention_recommendation": "Validate required configuration before releasing.",
        "confidence": 92,
        "confidence_reasoning": "Pod status and startup logs agree.",
    }


def full_investigation() -> dict[str, object]:
    return {
        "pods": {"healthy": False, "problematic_pods": []},
        "logs": {"logs": [], "errors": []},
        "events": {"findings": []},
        "deployments": {"healthy": True, "deployments": []},
        "network": {"services": [], "dns_findings": []},
    }


def test_prompt_is_deterministic_and_redacts_sensitive_values() -> None:
    prompt_builder = PromptBuilder()
    investigation = {
        "pods": {"healthy": False},
        "logs": {"lines": ["password=hunter2"]},
        "events": {"findings": []},
        "deployments": {},
        "network": {},
    }

    prompt = prompt_builder.build(investigation)

    assert prompt == prompt_builder.build(investigation)
    assert "password=[REDACTED]" in prompt[1]["content"]
    assert "hunter2" not in prompt[1]["content"]
    assert "deployment health" in prompt[0]["content"].lower()
    assert "networking findings" in prompt[0]["content"].lower()


def test_openrouter_retries_temporary_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["Authorization"] == "Bearer test-key"
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(valid_model_result())}}
                ]
            },
            request=request,
        )

    monkeypatch.setattr("app.ai.client.time.sleep", lambda _: None)
    client = OpenRouterClient(
        "test-key",
        "test/model",
        transport=httpx.MockTransport(handle_request),
    )

    result = client.complete([{"role": "user", "content": "diagnose"}])

    assert calls == 2
    assert result["root_cause"] == valid_model_result()["root_cause"]


def test_openrouter_requires_key_and_model() -> None:
    with pytest.raises(AIConfigurationError):
        OpenRouterClient("", "test/model")
    with pytest.raises(AIConfigurationError):
        OpenRouterClient("test-key", "")


def test_openrouter_retries_timeouts_without_exposing_provider_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handle_request(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("private provider details")

    monkeypatch.setattr("app.ai.client.time.sleep", lambda _: None)
    client = OpenRouterClient(
        "test-key",
        "test/model",
        max_attempts=2,
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(AIServiceError) as error:
        client.complete([{"role": "user", "content": "diagnose"}])

    assert calls == 2
    assert "private provider details" not in str(error.value)


def test_analyzer_caps_confidence_when_evidence_is_incomplete() -> None:
    class FakeLLMClient:
        def complete(self, messages: list[dict[str, str]]) -> dict[str, object]:
            assert messages[0]["role"] == "system"
            assert "senior Kubernetes SRE" in messages[0]["content"]
            return valid_model_result()

    diagnosis = RootCauseAnalyzer(
        client=FakeLLMClient(),
        settings=Settings(),
    ).analyze({"pods": {"healthy": False}})

    assert diagnosis.confidence == 35
    assert "capped at 35%" in diagnosis.confidence_reasoning


def test_recommendation_engine_rejects_shell_and_destructive_commands() -> None:
    from app.ai.reasoning import FixRecommendationEngine

    engine = FixRecommendationEngine()
    result = valid_model_result()
    result["kubectl_command"] = "kubectl delete pod payment-service"

    with pytest.raises(ValueError, match="unsafe kubectl command"):
        engine.build(result)

    result["kubectl_command"] = "kubectl edit deployment payment-service; whoami"
    with pytest.raises(ValueError, match="unsafe kubectl command"):
        engine.build(result)


@pytest.mark.anyio
async def test_investigate_returns_evidence_and_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import investigate as investigate_route

    class SuccessfulInvestigation:
        def investigate(
            self,
            on_progress: Callable[[str], None] | None = None,
        ) -> dict[str, object]:
            if on_progress:
                on_progress("checking_pods")
            return {"status": "success", "investigation": full_investigation()}

    class SuccessfulAnalyzer:
        def analyze(self, investigation: dict[str, object]) -> Diagnosis:
            assert set(investigation) == {
                "pods",
                "logs",
                "events",
                "deployments",
                "network",
            }
            return Diagnosis.model_validate(valid_model_result())

    monkeypatch.setattr(
        investigate_route,
        "InvestigationService",
        SuccessfulInvestigation,
    )
    monkeypatch.setattr(
        investigate_route,
        "RootCauseAnalyzer",
        SuccessfulAnalyzer,
    )
    monkeypatch.setattr(
        investigate_route,
        "InsForgeHistoryRepository",
        lambda _url: FakeHistory(),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/investigate",
            headers={"Authorization": "Bearer user-token"},
            json={"investigation_id": "93e314ca-e7f7-46fd-a82c-3029b4b8aa19"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["investigation"] == full_investigation()
    assert response.json()["diagnosis"]["confidence"] == 92
    assert response.json()["diagnosis"]["kubectl_command"] == (
        "kubectl edit deployment payment-service -n default"
    )


@pytest.mark.anyio
async def test_investigate_reports_missing_ai_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import investigate as investigate_route

    class SuccessfulInvestigation:
        def investigate(
            self,
            on_progress: Callable[[str], None] | None = None,
        ) -> dict[str, object]:
            if on_progress:
                on_progress("checking_pods")
            return {"status": "success", "investigation": full_investigation()}

    class UnconfiguredAnalyzer:
        def __init__(self) -> None:
            raise AIConfigurationError("AI reasoning is not configured.")

    monkeypatch.setattr(
        investigate_route,
        "InvestigationService",
        SuccessfulInvestigation,
    )
    monkeypatch.setattr(
        investigate_route,
        "RootCauseAnalyzer",
        UnconfiguredAnalyzer,
    )
    monkeypatch.setattr(
        investigate_route,
        "InsForgeHistoryRepository",
        lambda _url: FakeHistory(),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/investigate",
            headers={"Authorization": "Bearer user-token"},
            json={"investigation_id": "93e314ca-e7f7-46fd-a82c-3029b4b8aa19"},
        )

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert "diagnosis" not in response.json()
    assert response.json()["investigation"] == full_investigation()
