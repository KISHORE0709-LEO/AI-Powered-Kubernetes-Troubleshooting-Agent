from collections.abc import Callable

from app.kubernetes.deployments import DeploymentInspector
from app.kubernetes.events import EventsAnalyzer
from app.kubernetes.kubectl import KubectlExecutor, parse_json_result
from app.kubernetes.logs import LogsCollector
from app.kubernetes.network import NetworkInspector
from app.kubernetes.pods import PodInspector


class InvestigationService:
    def __init__(self, executor: KubectlExecutor | None = None) -> None:
        self.executor = executor or KubectlExecutor()

    def investigate(
        self,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        pod_inspector = PodInspector(self.executor)
        if on_progress:
            on_progress("checking_pods")
        pod_result = self.executor.get_json("pods")
        raw_pods = parse_json_result(pod_result)
        pods = (
            pod_inspector.inspect_payload(raw_pods)
            if raw_pods is not None
            else pod_inspector.error_response(
                pod_result.error
                or pod_result.stderr.strip()
                or "Invalid kubectl pod response"
            )
        )

        problematic_pods = pods.get("problematic_pods", [])
        if on_progress:
            on_progress("reading_logs")
        logs = LogsCollector(self.executor).collect(
            problematic_pods if isinstance(problematic_pods, list) else []
        )
        if on_progress:
            on_progress("analyzing_events")
        events = EventsAnalyzer(self.executor).analyze()
        event_findings = events.get("findings", [])
        if on_progress:
            on_progress("checking_networking")
        network = NetworkInspector(self.executor).inspect(
            raw_pods,
            event_findings if isinstance(event_findings, list) else [],
        )
        if on_progress:
            on_progress("inspecting_deployments")
        deployments = DeploymentInspector(self.executor).inspect()
        investigation = {
            "pods": pods,
            "logs": logs,
            "events": events,
            "deployments": deployments,
            "network": network,
        }
        errors = [
            section["error"]
            for section in (pods, logs, events, deployments, network)
            if isinstance(section, dict) and section.get("error")
        ]
        errors.extend(
            log_entry["error"]
            for log_entry in logs.get("errors", [])
            if isinstance(log_entry, dict) and log_entry.get("error")
        )
        return {
            "status": "error" if errors else "success",
            "investigation": investigation,
        }
