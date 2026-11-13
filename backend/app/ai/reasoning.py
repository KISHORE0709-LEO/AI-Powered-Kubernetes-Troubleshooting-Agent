from app.ai.client import LLMClient, OpenRouterClient
from app.ai.prompt_builder import PromptBuilder
from app.core.config import Settings, get_settings
from app.models.diagnosis import Diagnosis


class FixRecommendationEngine:
    allowed_verbs = {"get", "describe", "logs", "edit", "set", "rollout", "patch"}
    forbidden_characters = {";", "|", "&", "$", "`", ">", "<", "\n", "\r"}

    def build(self, result: dict[str, object]) -> Diagnosis:
        diagnosis = Diagnosis.model_validate(result)
        if diagnosis.kubectl_command:
            self._validate_command(diagnosis.kubectl_command)
        return diagnosis

    def _validate_command(self, command: str) -> None:
        parts = command.strip().split()
        if (
            len(parts) < 2
            or parts[0] != "kubectl"
            or parts[1] not in self.allowed_verbs
            or any(character in command for character in self.forbidden_characters)
        ):
            raise ValueError("The diagnosis included an unsafe kubectl command.")


class ConfidenceEngine:
    evidence_sections = ("pods", "logs", "events", "deployments", "network")
    confidence_caps = {0: 0, 1: 35, 2: 55, 3: 70, 4: 85, 5: 95}

    @staticmethod
    def _section_available(investigation: dict[str, object], section: str) -> bool:
        result = investigation.get(section)
        return isinstance(result, dict) and not result.get("error")

    def apply(
        self,
        diagnosis: Diagnosis,
        investigation: dict[str, object],
    ) -> Diagnosis:
        available = sum(
            self._section_available(investigation, section)
            for section in self.evidence_sections
        )
        confidence_cap = self.confidence_caps[available]
        if diagnosis.confidence <= confidence_cap:
            return diagnosis

        reasoning = (
            f"{diagnosis.confidence_reasoning.rstrip()} "
            f"The score is capped at {confidence_cap}% because only "
            f"{available} of {len(self.evidence_sections)} evidence sections "
            "were available."
        )
        return diagnosis.model_copy(
            update={"confidence": confidence_cap, "confidence_reasoning": reasoning}
        )


class RootCauseAnalyzer:
    def __init__(
        self,
        client: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenRouterClient(
            api_key=self.settings.openrouter_api_key,
            model=self.settings.openrouter_model,
            timeout_seconds=self.settings.openrouter_timeout_seconds,
        )
        self.prompt_builder = PromptBuilder()
        self.fix_recommendation_engine = FixRecommendationEngine()
        self.confidence_engine = ConfidenceEngine()

    def analyze(self, investigation: dict[str, object]) -> Diagnosis:
        result = self.client.complete(self.prompt_builder.build(investigation))
        diagnosis = self.fix_recommendation_engine.build(result)
        return self.confidence_engine.apply(diagnosis, investigation)
