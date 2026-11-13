from app.kubernetes.kubectl import KubectlExecutor, parse_json_result
from app.kubernetes.redaction import redact_sensitive_text

IMPORTANT_REASONS = {
    "FailedScheduling",
    "BackOff",
    "FailedMount",
    "FailedPull",
    "ErrImagePull",
    "Unhealthy",
}
DNS_KEYWORDS = ("dns", "name resolution", "no such host", "could not resolve")
MAX_FINDINGS = 100


class EventsAnalyzer:
    def __init__(self, executor: KubectlExecutor) -> None:
        self.executor = executor

    def analyze(self) -> dict[str, object]:
        result = self.executor.get_json("events")
        payload = parse_json_result(result)
        if payload is None:
            return {"findings": [], "error": result.error or result.stderr.strip() or "Invalid kubectl events response"}
        items = payload.get("items", [])
        if not isinstance(items, list):
            return {"findings": [], "error": "Invalid event list in kubectl response"}

        findings = []
        for event in items:
            if not isinstance(event, dict):
                continue
            metadata = event.get("metadata") or {}
            involved_object = event.get("involvedObject") or {}
            reason = str(event.get("reason", ""))
            message = str(event.get("message", ""))
            dns_issue = any(keyword in message.lower() for keyword in DNS_KEYWORDS)
            if reason not in IMPORTANT_REASONS and not dns_issue:
                continue
            findings.append(
                {
                    "reason": reason or "Networking",
                    "type": event.get("type", "Unknown"),
                    "namespace": metadata.get("namespace", "default"),
                    "object": involved_object.get("name", "unknown"),
                    "message": redact_sensitive_text(message)[:1000],
                    "count": event.get("count", 1),
                    "dns_related": dns_issue,
                }
            )
            if len(findings) >= MAX_FINDINGS:
                break
        return {"findings": findings}
