from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from app.ai.client import AIConfigurationError, AIServiceError
from app.ai.reasoning import RootCauseAnalyzer
from app.core.config import get_settings
from app.models.investigation import InvestigationRequest
from app.services.investigation import InvestigationService
from app.services.history import (
    HistoryAuthenticationError,
    HistoryConfigurationError,
    HistoryServiceError,
    InsForgeHistoryRepository,
)

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/investigate")
def investigate(
    request: InvestigationRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> JSONResponse:
    if not credentials or credentials.scheme.lower() != "bearer":
        return JSONResponse(
            status_code=401,
            content={"status": "error", "error": "A valid user session is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    try:
        history = InsForgeHistoryRepository(settings.insforge_url)
    except HistoryConfigurationError as error:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "error": str(error)},
        )

    try:
        history.authorize(request.investigation_id, credentials.credentials)

        def update_progress(phase: str) -> None:
            history.update(
                request.investigation_id,
                credentials.credentials,
                {"phase": phase},
            )

        result = InvestigationService().investigate(on_progress=update_progress)
        if result["status"] != "success":
            history.update(
                request.investigation_id,
                credentials.credentials,
                {"status": "error", "phase": "failed"},
            )
            return JSONResponse(
                status_code=503,
                content={**result, "investigation_id": str(request.investigation_id)},
            )

        history.update(
            request.investigation_id,
            credentials.credentials,
            {"phase": "ai_reasoning"},
        )
        try:
            diagnosis = RootCauseAnalyzer().analyze(result["investigation"])
        except AIConfigurationError as error:
            history.update(
                request.investigation_id,
                credentials.credentials,
                {"status": "error", "phase": "failed"},
            )
            logger.warning("AI reasoning is not configured")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "investigation_id": str(request.investigation_id),
                    "investigation": result["investigation"],
                    "error": str(error),
                },
            )
        except AIServiceError as error:
            history.update(
                request.investigation_id,
                credentials.credentials,
                {"status": "error", "phase": "failed"},
            )
            logger.warning("AI reasoning request failed: {}", error)
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error",
                    "investigation_id": str(request.investigation_id),
                    "investigation": result["investigation"],
                    "error": str(error),
                },
            )
        except ValueError:
            history.update(
                request.investigation_id,
                credentials.credentials,
                {"status": "error", "phase": "failed"},
            )
            logger.warning("AI reasoning returned invalid or unsafe recommendations")
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "investigation_id": str(request.investigation_id),
                    "investigation": result["investigation"],
                    "error": "The AI provider returned an invalid diagnosis.",
                },
            )

        history_values: dict[str, object] = {
            "status": "success",
            "phase": "root_cause_found",
            "root_cause": diagnosis.root_cause,
            "confidence": diagnosis.confidence,
        }
        history_values["namespace"] = _first_problem_namespace(
            result["investigation"]
        )
        history.update(
            request.investigation_id,
            credentials.credentials,
            history_values,
        )
    except HistoryAuthenticationError as error:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "error": str(error)},
        )
    except HistoryServiceError as error:
        logger.warning("Investigation history could not be updated")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "error": str(error)},
        )
    finally:
        history.close()

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "investigation_id": str(request.investigation_id),
            "investigation": result["investigation"],
            "diagnosis": diagnosis.model_dump(mode="json"),
        },
    )


def _first_problem_namespace(investigation: object) -> str | None:
    if not isinstance(investigation, dict):
        return None
    pods = investigation.get("pods")
    if not isinstance(pods, dict):
        return None
    problematic_pods = pods.get("problematic_pods")
    if not isinstance(problematic_pods, list):
        return None
    for pod in problematic_pods:
        if isinstance(pod, dict):
            namespace = pod.get("namespace")
            if isinstance(namespace, str) and namespace:
                return namespace
    return None
