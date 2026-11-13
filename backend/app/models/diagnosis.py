from pydantic import BaseModel, ConfigDict, Field


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    root_cause: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=1, max_length=3000)
    fix: str = Field(min_length=1, max_length=2000)
    kubectl_command: str = Field(max_length=1000)
    prevention_recommendation: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(ge=0, le=100)
    confidence_reasoning: str = Field(min_length=1, max_length=2000)
