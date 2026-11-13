from collections.abc import Mapping
from uuid import UUID

import httpx


class HistoryConfigurationError(Exception):
    pass


class HistoryAuthenticationError(Exception):
    pass


class HistoryServiceError(Exception):
    pass


class InsForgeHistoryRepository:
    def __init__(
        self,
        base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized_url = base_url.strip().rstrip("/")
        if not normalized_url:
            raise HistoryConfigurationError("InsForge history is not configured.")

        self.url = f"{normalized_url}/api/database/records/investigation_history"
        self.client = httpx.Client(timeout=10, transport=transport)

    def close(self) -> None:
        self.client.close()

    def authorize(self, investigation_id: UUID, access_token: str) -> None:
        response = self._request(
            "GET",
            investigation_id,
            access_token,
            params={
                "select": "id",
                "status": "eq.running",
                "phase": "eq.starting",
            },
        )
        records = self._response_records(response)
        if not records:
            raise HistoryAuthenticationError(
                "The investigation record is unavailable to this user."
            )

    def update(
        self,
        investigation_id: UUID,
        access_token: str,
        values: Mapping[str, object],
    ) -> None:
        response = self._request(
            "PATCH",
            investigation_id,
            access_token,
            body=dict(values),
            headers={"Prefer": "return=representation"},
        )
        records = self._response_records(response)
        if not records:
            raise HistoryAuthenticationError(
                "The investigation record is unavailable to this user."
            )

    def _request(
        self,
        method: str,
        investigation_id: UUID,
        access_token: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        body: dict[str, object] | None = None,
    ) -> httpx.Response:
        request_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)
        try:
            response = self.client.request(
                method,
                self.url,
                params={"id": f"eq.{investigation_id}", **(params or {})},
                headers=request_headers,
                json=body,
            )
        except httpx.RequestError as error:
            raise HistoryServiceError("InsForge history could not be reached.") from error

        if response.status_code in (401, 403):
            raise HistoryAuthenticationError(
                "A valid user session is required for investigations."
            )
        if not response.is_success:
            raise HistoryServiceError("InsForge history request failed.")
        return response

    @staticmethod
    def _response_records(response: httpx.Response) -> list[object]:
        try:
            result = response.json()
        except ValueError as error:
            raise HistoryServiceError(
                "InsForge returned an invalid history response."
            ) from error
        if not isinstance(result, list):
            raise HistoryServiceError("InsForge returned an invalid history response.")
        return result
