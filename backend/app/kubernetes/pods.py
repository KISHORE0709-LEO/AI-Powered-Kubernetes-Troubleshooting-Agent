from datetime import datetime, timedelta, timezone
from typing import Any

from app.kubernetes.kubectl import KubectlExecutor, parse_json_result

UNHEALTHY_REASONS = {
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "Pending",
    "Error",
    "Failed",
    "OOMKilled",
}
CONTAINER_CREATING_TIMEOUT = timedelta(minutes=5)


class PodInspector:
    def __init__(self, executor: KubectlExecutor) -> None:
        self.executor = executor

    def inspect(self) -> dict[str, object]:
        result = self.executor.get_json("pods")
        payload = parse_json_result(result)
        if payload is None:
            return self.error_response(
                result.error or result.stderr.strip() or "Invalid kubectl pod response"
            )
        return self.inspect_payload(payload)

    def inspect_payload(self, payload: dict[str, object]) -> dict[str, object]:
        items = payload.get("items", [])
        if not isinstance(items, list):
            return {"healthy": False, "problematic_pods": [], "error": "Invalid pod list in kubectl response"}

        problematic_pods = []
        for item in items:
            if not isinstance(item, dict):
                continue
            problem = self._pod_problem(item)
            if problem is not None:
                problematic_pods.append(problem)
        return {
            "healthy": not problematic_pods,
            "total_pods": len(items),
            "problematic_pods": problematic_pods[:100],
        }

    @staticmethod
    def error_response(error: str) -> dict[str, object]:
        return {"healthy": False, "problematic_pods": [], "error": error}

    @staticmethod
    def _pod_problem(pod: dict[str, Any]) -> dict[str, object] | None:
        metadata = pod.get("metadata") or {}
        status = pod.get("status") or {}
        reasons: list[str] = []

        phase = status.get("phase")
        if phase in {"Pending", "Error", "Failed"}:
            reasons.append(phase)

        for container_status in status.get("containerStatuses", []):
            current_state = container_status.get("state") or {}
            waiting_reason = (current_state.get("waiting") or {}).get("reason")
            if waiting_reason in UNHEALTHY_REASONS:
                reasons.append(waiting_reason)
            elif waiting_reason == "ContainerCreating" and PodInspector._is_stuck(metadata):
                reasons.append(waiting_reason)

            for state_name in ("terminated",):
                terminated_reason = (current_state.get(state_name) or {}).get("reason")
                if terminated_reason in {"Error", "OOMKilled"}:
                    reasons.append(terminated_reason)

            last_terminated_reason = (
                (container_status.get("lastState") or {}).get("terminated") or {}
            ).get("reason")
            if last_terminated_reason in {"Error", "OOMKilled"}:
                reasons.append(last_terminated_reason)

        if not reasons:
            return None
        return {
            "name": metadata.get("name", "unknown"),
            "namespace": metadata.get("namespace", "default"),
            "status": reasons[0],
            "reasons": list(dict.fromkeys(reasons)),
        }

    @staticmethod
    def _is_stuck(metadata: dict[str, Any]) -> bool:
        created_at = metadata.get("creationTimestamp")
        if not isinstance(created_at, str):
            return False
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created >= CONTAINER_CREATING_TIMEOUT
