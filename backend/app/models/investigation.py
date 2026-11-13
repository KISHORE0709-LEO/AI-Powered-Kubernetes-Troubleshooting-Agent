from uuid import UUID

from pydantic import BaseModel


class InvestigationRequest(BaseModel):
    investigation_id: UUID
