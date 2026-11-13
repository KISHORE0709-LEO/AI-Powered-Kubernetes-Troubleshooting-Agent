from app.kubernetes.kubectl import KubectlExecutor, parse_json_result


class NetworkInspector:
    def __init__(self, executor: KubectlExecutor) -> None:
        self.executor = executor

    def inspect(
        self,
        pod_payload: dict[str, object] | None,
        event_findings: list[dict[str, object]],
    ) -> dict[str, object]:
        services_result = self.executor.get_json("services")
        services_payload = parse_json_result(services_result)
        endpoints_result = self.executor.get_json("endpoints")
        endpoints_payload = parse_json_result(endpoints_result)
        if services_payload is None or endpoints_payload is None:
            errors = [
                result.error or result.stderr.strip() or "Invalid kubectl network response"
                for result, payload in (
                    (services_result, services_payload),
                    (endpoints_result, endpoints_payload),
                )
                if payload is None
            ]
            return {"services": [], "dns_findings": self._dns_findings(event_findings), "error": "; ".join(errors)}

        pod_items = (pod_payload or {}).get("items", [])
        endpoint_items = endpoints_payload.get("items", [])
        if not isinstance(pod_items, list) or not isinstance(endpoint_items, list):
            return {"services": [], "dns_findings": self._dns_findings(event_findings), "error": "Invalid kubectl network resource list"}

        endpoints_by_service = {}
        for endpoints in endpoint_items:
            if not isinstance(endpoints, dict):
                continue
            metadata = endpoints.get("metadata") or {}
            endpoints_by_service[(metadata.get("namespace"), metadata.get("name"))] = sum(
                len(subset.get("addresses", []))
                for subset in endpoints.get("subsets", [])
            )

        findings = []
        for service in services_payload.get("items", []):
            if not isinstance(service, dict):
                continue
            metadata = service.get("metadata") or {}
            spec = service.get("spec") or {}
            namespace = metadata.get("namespace", "default")
            name = metadata.get("name", "unknown")
            selector = spec.get("selector") or {}
            endpoint_count = endpoints_by_service.get((namespace, name), 0)
            issues = []
            if selector and pod_payload is None:
                issues.append("selector_check_unavailable")
            elif selector:
                matching_pods = [
                    pod
                    for pod in pod_items
                    if isinstance(pod, dict)
                    and (pod.get("metadata") or {}).get("namespace") == namespace
                    and all(
                        ((pod.get("metadata") or {}).get("labels") or {}).get(key) == value
                        for key, value in selector.items()
                    )
                ]
                if not matching_pods:
                    issues.append("selector_mismatch")
                elif endpoint_count == 0:
                    issues.append("missing_endpoints")
            elif spec.get("type") != "ExternalName" and endpoint_count == 0:
                issues.append("missing_endpoints")
            findings.append(
                {
                    "name": name,
                    "namespace": namespace,
                    "type": spec.get("type", "ClusterIP"),
                    "selector": selector,
                    "endpoint_count": endpoint_count,
                    "healthy": not issues,
                    "issues": issues,
                }
            )
        return {
            "services": findings[:100],
            "dns_findings": self._dns_findings(event_findings),
        }

    @staticmethod
    def _dns_findings(event_findings: list[dict[str, object]]) -> list[dict[str, object]]:
        return [finding for finding in event_findings if finding.get("dns_related")]
