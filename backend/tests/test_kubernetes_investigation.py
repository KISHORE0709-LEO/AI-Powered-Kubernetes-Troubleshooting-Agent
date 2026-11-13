import json
import subprocess
from collections.abc import Callable
from unittest.mock import Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.kubernetes.kubectl import KubectlExecutor, KubectlResult
from app.kubernetes.network import NetworkInspector
from app.kubernetes.logs import LogsCollector
from app.kubernetes.pods import PodInspector
from app.main import app
from app.services.investigation import InvestigationService


class FakeExecutor:
    def __init__(self, resources: dict[str, dict[str, object]]) -> None:
        self.resources = resources

    def get_json(self, resource: str) -> KubectlResult:
        return KubectlResult(0, json.dumps(self.resources.get(resource, {"items": []})))

    def logs(self, namespace: str, pod_name: str) -> KubectlResult:
        return KubectlResult(0, "startup error: password=hunter2\nall good\n")


def test_kubectl_executor_uses_fixed_read_only_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "{}", ""))
    monkeypatch.setattr(subprocess, "run", run)

    result = KubectlExecutor().get_json("pods")

    assert result.succeeded
    assert run.call_args.args[0] == [
        "kubectl",
        "get",
        "pods",
        "--all-namespaces",
        "--output=json",
    ]
    assert run.call_args.kwargs["shell"] is False


def test_kubectl_logs_rejects_untrusted_resource_names() -> None:
    with pytest.raises(ValueError):
        KubectlExecutor().logs("default", "pod; delete pods --all")


def test_pod_inspector_detects_container_reasons() -> None:
    inspector = PodInspector(FakeExecutor({}))
    result = inspector.inspect_payload(
        {
            "items": [
                {
                    "metadata": {"name": "worker", "namespace": "jobs"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "state": {
                                    "waiting": {"reason": "CrashLoopBackOff"}
                                }
                            },
                            {
                                "lastState": {
                                    "terminated": {"reason": "OOMKilled"}
                                }
                            },
                        ],
                    },
                },
                {"metadata": {"name": "ready"}, "status": {"phase": "Running"}},
            ]
        }
    )

    assert result["healthy"] is False
    assert result["problematic_pods"] == [
        {
            "name": "worker",
            "namespace": "jobs",
            "status": "CrashLoopBackOff",
            "reasons": ["CrashLoopBackOff", "OOMKilled"],
        }
    ]


def test_logs_are_filtered_and_sensitive_values_redacted() -> None:
    result = LogsCollector(FakeExecutor({})).collect(
        [{"name": "worker", "namespace": "jobs"}]
    )

    assert result["logs"][0]["lines"] == ["startup error: password=[REDACTED]"]


def test_network_inspector_reports_service_selector_mismatch() -> None:
    executor = FakeExecutor(
        {
            "services": {
                "items": [
                    {
                        "metadata": {"name": "api", "namespace": "default"},
                        "spec": {"selector": {"app": "api"}},
                    }
                ]
            },
            "endpoints": {"items": []},
        }
    )

    result = NetworkInspector(executor).inspect(
        {"items": [{"metadata": {"namespace": "default", "labels": {"app": "web"}}}]},
        [{"dns_related": True, "message": "lookup failed"}],
    )

    assert result["services"][0]["issues"] == ["selector_mismatch"]
    assert len(result["dns_findings"]) == 1


def test_investigation_service_returns_all_evidence_sections() -> None:
    result = InvestigationService(FakeExecutor({})).investigate()

    assert result["status"] == "success"
    assert set(result["investigation"]) == {
        "pods",
        "logs",
        "events",
        "deployments",
        "network",
    }


@pytest.mark.anyio
async def test_investigate_returns_structured_error_when_kubectl_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import investigate as investigate_route

    class FailedInvestigation:
        def investigate(
            self,
            on_progress: Callable[[str], None] | None = None,
        ) -> dict[str, object]:
            if on_progress:
                on_progress("checking_pods")
            return {
                "status": "error",
                "investigation": {
                    "pods": {"healthy": False, "error": "Unable to start kubectl"},
                    "logs": {"logs": [], "errors": []},
                    "events": {"findings": [], "error": "Unable to start kubectl"},
                    "deployments": {"healthy": False, "deployments": []},
                    "network": {"services": [], "dns_findings": []},
                },
            }

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

    monkeypatch.setattr(
        investigate_route,
        "InvestigationService",
        lambda: FailedInvestigation(),
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
    assert "pods" in response.json()["investigation"]
