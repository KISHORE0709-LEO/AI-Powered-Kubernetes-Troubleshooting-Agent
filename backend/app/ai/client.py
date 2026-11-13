import json
import time
from typing import Protocol

import httpx
from loguru import logger


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class AIConfigurationError(Exception):
    pass


class AIServiceError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> dict[str, object]: ...


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int = 30,
        max_attempts: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.transport = transport

        if not self.api_key or not self.model:
            raise AIConfigurationError(
                "AI reasoning is not configured. Set OPENROUTER_API_KEY "
                "and OPENROUTER_MODEL."
            )

    def complete(self, messages: list[dict[str, str]]) -> dict[str, object]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "AI Kubernetes Troubleshooting Agent",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = client.post(
                        OPENROUTER_CHAT_COMPLETIONS_URL,
                        headers=headers,
                        json=payload,
                    )
                except (httpx.TimeoutException, httpx.TransportError) as error:
                    logger.warning(
                        "OpenRouter request failed on attempt {}/{} ({})",
                        attempt,
                        self.max_attempts,
                        type(error).__name__,
                    )
                    if attempt == self.max_attempts:
                        raise AIServiceError(
                            "OpenRouter request failed after retries."
                        ) from error
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue

                if response.status_code == 429 or response.status_code >= 500:
                    logger.warning(
                        "OpenRouter returned HTTP {} on attempt {}/{}",
                        response.status_code,
                        attempt,
                        self.max_attempts,
                    )
                    if attempt == self.max_attempts:
                        raise AIServiceError(
                            "OpenRouter is temporarily unavailable."
                        )
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                    continue

                if not response.is_success:
                    logger.warning(
                        "OpenRouter rejected a request with HTTP {}",
                        response.status_code,
                    )
                    raise AIServiceError(
                        f"OpenRouter rejected the request (HTTP {response.status_code})."
                    )

                return self._parse_response(response)

        raise AIServiceError("OpenRouter request did not complete.")

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, object]:
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as error:
            logger.warning("OpenRouter returned an invalid response format")
            raise AIServiceError("OpenRouter returned an invalid response.") from error

        if not isinstance(result, dict):
            raise AIServiceError("OpenRouter returned an invalid diagnosis format.")
        return result
