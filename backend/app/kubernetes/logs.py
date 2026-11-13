import re

from app.kubernetes.kubectl import KubectlExecutor
from app.kubernetes.redaction import redact_sensitive_text

RELEVANT_LOG_PATTERN = re.compile(
    r"(?i)(exception|traceback|error|failed|failure|refused|timeout|"
    r"missing|not set|not found|unable to|cannot|startup|connection)"
)
MAX_LOG_ENTRIES = 20
MAX_RELEVANT_LINES = 20


class LogsCollector:
    def __init__(self, executor: KubectlExecutor) -> None:
        self.executor = executor

    def collect(self, problematic_pods: list[dict[str, object]]) -> dict[str, object]:
        logs = []
        errors = []
        for pod in problematic_pods[:MAX_LOG_ENTRIES]:
            namespace = str(pod.get("namespace", "default"))
            name = str(pod.get("name", ""))
            result = self.executor.logs(namespace, name)
            if not result.succeeded:
                errors.append(
                    {
                        "name": name,
                        "namespace": namespace,
                        "error": result.error or redact_sensitive_text(result.stderr.strip()) or "kubectl logs failed",
                    }
                )
                continue
            lines = result.stdout.splitlines()
            relevant = [line for line in lines if RELEVANT_LOG_PATTERN.search(line)]
            selected = relevant[-MAX_RELEVANT_LINES:] if relevant else lines[-10:]
            logs.append(
                {
                    "name": name,
                    "namespace": namespace,
                    "lines": [redact_sensitive_text(line[:1000]) for line in selected],
                }
            )
        return {"logs": logs, "errors": errors}
