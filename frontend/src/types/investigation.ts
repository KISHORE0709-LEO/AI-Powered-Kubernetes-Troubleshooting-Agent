export type InvestigationStatus = "running" | "success" | "error";

export type InvestigationPhase =
  | "starting"
  | "checking_pods"
  | "reading_logs"
  | "analyzing_events"
  | "checking_networking"
  | "inspecting_deployments"
  | "ai_reasoning"
  | "root_cause_found"
  | "failed";

export interface InvestigationHistoryRecord {
  id: string;
  status: InvestigationStatus;
  phase: InvestigationPhase;
  root_cause: string | null;
  namespace: string | null;
  confidence: number | null;
  created_at: string;
}

export interface Diagnosis {
  root_cause: string;
  explanation: string;
  fix: string;
  kubectl_command: string;
  prevention_recommendation: string;
  confidence: number;
  confidence_reasoning: string;
}

export interface InvestigationResponse {
  status: "success";
  investigation_id: string;
  investigation: Record<string, unknown>;
  diagnosis: Diagnosis;
}

export type InvestigationProgressEvent = InvestigationHistoryRecord;
