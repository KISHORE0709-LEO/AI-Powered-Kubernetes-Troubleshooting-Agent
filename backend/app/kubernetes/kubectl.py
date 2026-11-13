import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Sequence

from loguru import logger

from app.core.config import get_settings

JSON_RESOURCES = {"pods", "events", "deployments", "services", "endpoints"}
NAMESPACE_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9.]*[a-z0-9])?$")
MAX_OUTPUT_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class KubectlResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and self.error is None


class KubectlExecutor:
    def __init__(self, timeout_seconds: int | None = None) -> None:
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else get_settings().kubectl_timeout_seconds
        )

    def get_json(self, resource: str) -> KubectlResult:
        if resource not in JSON_RESOURCES:
            raise ValueError(f"Unsupported kubectl resource: {resource}")
        return self._run(
            ["get", resource, "--all-namespaces", "--output=json"]
        )

    def logs(self, namespace: str, pod_name: str) -> KubectlResult:
        if not NAMESPACE_PATTERN.fullmatch(namespace):
            raise ValueError("Invalid Kubernetes namespace")
        if not RESOURCE_NAME_PATTERN.fullmatch(pod_name):
            raise ValueError("Invalid Kubernetes pod name")
        return self._run(
            [
                "logs",
                "--namespace",
                namespace,
                pod_name,
                "--all-containers=true",
                "--tail=80",
                "--prefix=true",
            ]
        )

    def describe_deployment(self, namespace: str, name: str) -> KubectlResult:
        if not NAMESPACE_PATTERN.fullmatch(namespace):
            raise ValueError("Invalid Kubernetes namespace")
        if not RESOURCE_NAME_PATTERN.fullmatch(name):
            raise ValueError("Invalid Kubernetes deployment name")
        return self._run(["describe", "deployment", name, "--namespace", namespace])

    def _run(self, arguments: Sequence[str]) -> KubectlResult:
        command = ["kubectl", *arguments]
        environment = None
        kubeconfig_path = get_settings().kubeconfig_path.strip()
        if kubeconfig_path:
            environment = os.environ.copy()
            environment["KUBECONFIG"] = kubeconfig_path

        logger.info("Executing read-only kubectl command: {}", arguments[0])
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
                shell=False,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            logger.warning("kubectl command timed out: {}", arguments[0])
            return KubectlResult(
                returncode=-1,
                error=f"kubectl command timed out after {self.timeout_seconds} seconds",
            )
        except OSError as exc:
            logger.error("Unable to start kubectl: {}", exc)
            return KubectlResult(returncode=-1, error="Unable to start kubectl")

        output_size = len(result.stdout.encode("utf-8")) + len(
            result.stderr.encode("utf-8")
        )
        if output_size > MAX_OUTPUT_BYTES:
            logger.warning("kubectl output exceeded the configured size limit")
            return KubectlResult(
                returncode=-1,
                error="kubectl output exceeded the 5 MiB limit",
            )
        if result.returncode != 0:
            logger.warning("kubectl command failed with exit code {}", result.returncode)
        return KubectlResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )


def parse_json_result(result: KubectlResult) -> dict[str, object] | None:
    if not result.succeeded:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
