import { insforge } from "@/lib/insforge/client";
import type { InvestigationHistoryRecord } from "@/types/investigation";

const HISTORY_COLUMNS =
  "id, status, phase, root_cause, namespace, confidence, created_at";

export async function getInvestigationHistory(): Promise<
  InvestigationHistoryRecord[]
> {
  const { data, error } = await insforge.database
    .from("investigation_history")
    .select(HISTORY_COLUMNS)
    .order("created_at", { ascending: false })
    .limit(10);

  if (error) {
    throw new Error(error.message);
  }
  if (!Array.isArray(data)) {
    throw new Error("InsForge returned an invalid investigation history.");
  }

  return data as InvestigationHistoryRecord[];
}

export async function createInvestigationHistory(): Promise<
  InvestigationHistoryRecord
> {
  const { data, error } = await insforge.database
    .from("investigation_history")
    .insert([{ status: "running", phase: "starting" }])
    .select(HISTORY_COLUMNS)
    .single();

  if (error) {
    throw new Error(error.message);
  }
  if (!data || typeof data.id !== "string") {
    throw new Error("InsForge did not return the new investigation record.");
  }

  return data as InvestigationHistoryRecord;
}
