from app.kubernetes.kubectl import KubectlExecutor, parse_json_result


class DeploymentInspector:
    def __init__(self, executor: KubectlExecutor) -> None:
        self.executor = executor

    def inspect(self) -> dict[str, object]:
        result = self.executor.get_json("deployments")
        payload = parse_json_result(result)
        if payload is None:
            return {
                "healthy": False,
                "deployments": [],
                "error": result.error
                or result.stderr.strip()
                or "Invalid kubectl deployment response",
            }
        items = payload.get("items", [])
        if not isinstance(items, list):
            return {
                "healthy": False,
                "deployments": [],
                "error": "Invalid deployment list in kubectl response",
            }

        deployments = []
        for deployment in items:
            if not isinstance(deployment, dict):
                continue
            metadata = deployment.get("metadata") or {}
            spec = deployment.get("spec") or {}
            status = deployment.get("status") or {}
            desired = spec.get("replicas", 1)
            available = status.get("availableReplicas", 0)
            conditions = status.get("conditions", [])
            failures = [
                condition.get("reason") or condition.get("message") or condition.get("type")
                for condition in conditions
                if condition.get("status") == "False"
                and condition.get("type") in {"Available", "Progressing"}
            ]
            progress_failed = any(
                condition.get("type") == "Progressing"
                and condition.get("status") == "False"
                and condition.get("reason") == "ProgressDeadlineExceeded"
                for condition in conditions
            )
            unavailable_condition = any(
                condition.get("type") == "Available"
                and condition.get("status") == "False"
                for condition in conditions
            )
            ready = available >= desired and not progress_failed and not unavailable_condition
            deployments.append(
                {
                    "name": metadata.get("name", "unknown"),
                    "namespace": metadata.get("namespace", "default"),
                    "desired_replicas": desired,
                    "available_replicas": available,
                    "unavailable_replicas": status.get(
                        "unavailableReplicas", max(desired - available, 0)
                    ),
                    "healthy": ready,
                    "conditions": failures,
                }
            )
        return {
            "healthy": all(deployment["healthy"] for deployment in deployments),
            "deployments": deployments[:100],
        }
