import axios from "axios";
import type { HealthResponse } from "@/types/health";
import type { InvestigationResponse } from "@/types/investigation";

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
  timeout: 5000,
});

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>("/health");
  return data;
}

export async function investigate(
  investigationId: string,
): Promise<InvestigationResponse> {
  const { data } = await axios.post<InvestigationResponse>(
    "/api/investigate",
    { investigation_id: investigationId },
    { timeout: 180_000 },
  );
  return data;
}
