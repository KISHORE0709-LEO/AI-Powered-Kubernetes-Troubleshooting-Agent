"use client";

import axios from "axios";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useInvestigationHistory } from "@/hooks/use-investigation-history";
import { insforge } from "@/lib/insforge/client";
import { createInvestigationHistory } from "@/services/history";
import { investigate } from "@/services/api";
import { SignOutButton } from "@/components/sign-out-button";
import type {
  Diagnosis,
  InvestigationHistoryRecord,
  InvestigationPhase,
  InvestigationProgressEvent,
  InvestigationStatus,
} from "@/types/investigation";

const investigationPhases: InvestigationPhase[] = [
  "starting",
  "checking_pods",
  "reading_logs",
  "analyzing_events",
  "checking_networking",
  "inspecting_deployments",
  "ai_reasoning",
  "root_cause_found",
  "failed",
];
const investigationStatuses: InvestigationStatus[] = [
  "running",
  "success",
  "error",
];

const progressSteps: { phase: InvestigationPhase; label: string }[] = [
  { phase: "checking_pods", label: "Checking pods" },
  { phase: "reading_logs", label: "Reading logs" },
  { phase: "analyzing_events", label: "Analyzing events" },
  { phase: "checking_networking", label: "Checking networking" },
  { phase: "inspecting_deployments", label: "Inspecting deployments" },
  { phase: "ai_reasoning", label: "AI reasoning" },
  { phase: "root_cause_found", label: "Root cause found" },
];

function isProgressEvent(value: unknown): value is InvestigationProgressEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const event = value as Record<string, unknown>;
  return (
    typeof event.id === "string" &&
    investigationStatuses.includes(event.status as InvestigationStatus) &&
    investigationPhases.includes(event.phase as InvestigationPhase) &&
    (typeof event.root_cause === "string" || event.root_cause === null) &&
    (typeof event.namespace === "string" || event.namespace === null) &&
    (typeof event.confidence === "number" || event.confidence === null) &&
    typeof event.created_at === "string"
  );
}

function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body: unknown = error.response?.data;
    if (typeof body === "object" && body !== null && "error" in body) {
      const message = body.error;
      if (typeof message === "string") {
        return message;
      }
    }
    return error.code === "ECONNABORTED"
      ? "The investigation timed out. Check the history for its latest status."
      : error.message;
  }
  return error instanceof Error ? error.message : "The request could not be completed.";
}

function formatStatus(status: InvestigationHistoryRecord["status"]): string {
  return status === "success"
    ? "Completed"
    : status === "error"
      ? "Needs attention"
      : "In progress";
}

export function Dashboard({
  userId,
  email,
}: {
  userId: string;
  email: string;
}) {
  const queryClient = useQueryClient();
  const historyQuery = useInvestigationHistory(userId);
  const [activeHistory, setActiveHistory] =
    useState<InvestigationHistoryRecord | null>(null);
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [isInvestigating, setIsInvestigating] = useState(false);
  const [realtimeReady, setRealtimeReady] = useState(false);
  const [realtimeError, setRealtimeError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const channel = `investigation-history:${userId}`;

  useEffect(() => {
    let active = true;
    let subscribeInProgress = false;
    const realtime = insforge.realtime;
    const subscribeToChannel = async () => {
      if (!active || subscribeInProgress) {
        return;
      }
      subscribeInProgress = true;
      try {
        const response = await realtime.subscribe(channel);
        if (!active) {
          return;
        }
        if (!response.ok) {
          throw new Error(
            response.error?.message ?? "Could not subscribe to investigation updates.",
          );
        }
        setRealtimeError(null);
        setRealtimeReady(true);
      } catch (subscribeError: unknown) {
        if (active) {
          setRealtimeError(getErrorMessage(subscribeError));
          setRealtimeReady(false);
        }
      } finally {
        subscribeInProgress = false;
      }
    };
    const handleUpdate = (payload: unknown) => {
      if (!isProgressEvent(payload)) {
        return;
      }
      setActiveHistory((current) =>
        current?.id === payload.id ? payload : current,
      );
      void queryClient.invalidateQueries({
        queryKey: ["investigation-history", userId],
      });
    };
    const handleDisconnect = () => {
      setRealtimeReady(false);
    };
    const handleConnectionError = (reason: unknown) => {
      setRealtimeError(getErrorMessage(reason));
      setRealtimeReady(false);
    };
    const handleConnect = () => {
      void subscribeToChannel();
    };

    realtime.on("investigation_updated", handleUpdate);
    realtime.on("disconnect", handleDisconnect);
    realtime.on("connect_error", handleConnectionError);
    realtime.on("connect", handleConnect);
    void subscribeToChannel();

    return () => {
      active = false;
      realtime.off("investigation_updated", handleUpdate);
      realtime.off("disconnect", handleDisconnect);
      realtime.off("connect_error", handleConnectionError);
      realtime.off("connect", handleConnect);
      realtime.unsubscribe(channel);
    };
  }, [channel, queryClient, userId]);

  async function handleInvestigate() {
    setError(null);
    setDiagnosis(null);
    if (!realtimeReady) {
      setError(
        realtimeError ??
          "Waiting for a secure realtime connection. Try again in a moment.",
      );
      return;
    }

    setIsInvestigating(true);
    let record: InvestigationHistoryRecord | null = null;
    try {
      const newRecord = await createInvestigationHistory();
      record = newRecord;
      setActiveHistory(newRecord);
      await queryClient.invalidateQueries({
        queryKey: ["investigation-history", userId],
      });

      const response = await investigate(newRecord.id);
      setDiagnosis(response.diagnosis);
      setActiveHistory((current) => {
        if (!current || current.id !== newRecord.id) {
          return current;
        }
        return {
          ...current,
          status: "success",
          phase: "root_cause_found",
          root_cause: response.diagnosis.root_cause,
          confidence: response.diagnosis.confidence,
        };
      });
      await queryClient.invalidateQueries({
        queryKey: ["investigation-history", userId],
      });
    } catch (requestError: unknown) {
      setError(getErrorMessage(requestError));
      if (record) {
        const failedId = record.id;
        setActiveHistory((current) => {
          if (!current || current.id !== failedId) {
            return current;
          }
          return { ...current, status: "error", phase: "failed" };
        });
        await queryClient.invalidateQueries({
          queryKey: ["investigation-history", userId],
        });
      }
    } finally {
      setIsInvestigating(false);
    }
  }

  const currentStepIndex = activeHistory
    ? progressSteps.findIndex((step) => step.phase === activeHistory.phase)
    : -1;
  const investigationComplete =
    activeHistory?.status === "success" ||
    activeHistory?.phase === "root_cause_found";

  return (
    <main className="mx-auto min-h-screen w-full max-w-7xl px-5 py-6 sm:px-8 lg:px-10">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-xl bg-blue-700 text-sm font-bold text-white">
            AI
          </span>
          <div>
            <p className="font-semibold tracking-tight text-slate-900">
              AI Kubernetes Agent
            </p>
            <p className="text-xs text-slate-500">On-demand cluster troubleshooting</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-slate-600 sm:inline">{email}</span>
          <SignOutButton />
        </div>
      </header>

      <section className="grid gap-6 py-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-700">
                Kubernetes incident response
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
                Troubleshoot your cluster
              </h1>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Collect cluster evidence and receive an AI-assisted diagnosis.
                Commands are suggestions only and are never run automatically.
              </p>
              <button
                type="button"
                onClick={() => void handleInvestigate()}
                disabled={isInvestigating || !realtimeReady}
                className="mt-6 inline-flex items-center gap-2 rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isInvestigating ? "Investigating..." : "Investigate Cluster"}
                {!isInvestigating && <span aria-hidden="true">→</span>}
              </button>
              <p className="mt-3 text-xs text-slate-500" role="status">
                {realtimeReady
                  ? "Realtime progress connected"
                  : realtimeError ?? "Connecting to secure progress updates..."}
              </p>
              {error && (
                <p
                  role="alert"
                  className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800"
                >
                  {error}
                </p>
              )}
            </div>
          </section>

          {activeHistory && (
            <section
              aria-labelledby="progress-heading"
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2
                    id="progress-heading"
                    className="text-lg font-semibold text-slate-950"
                  >
                    Investigation progress
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {formatStatus(activeHistory.status)}
                    {activeHistory.namespace
                      ? ` · namespace ${activeHistory.namespace}`
                      : ""}
                  </p>
                </div>
                {isInvestigating && (
                  <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                    Live
                  </span>
                )}
              </div>
              <ol className="mt-6 grid gap-3 sm:grid-cols-2">
                {progressSteps.map((step, index) => {
                  const complete =
                    investigationComplete || index < currentStepIndex;
                  const current =
                    !investigationComplete && index === currentStepIndex;
                  return (
                    <li
                      key={step.phase}
                      className="flex items-center gap-3 rounded-lg bg-slate-50 px-3.5 py-3"
                    >
                      <span
                        className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                          complete
                            ? "bg-emerald-100 text-emerald-700"
                            : current
                              ? "bg-blue-100 text-blue-700"
                              : "bg-slate-200 text-slate-500"
                        }`}
                      >
                        {complete ? "✓" : current ? "…" : index + 1}
                      </span>
                      <span
                        className={`text-sm ${
                          complete || current
                            ? "font-medium text-slate-800"
                            : "text-slate-500"
                        }`}
                      >
                        {step.label}
                      </span>
                    </li>
                  );
                })}
              </ol>
              {activeHistory.status === "error" && (
                <p className="mt-4 text-sm text-rose-700">
                  This investigation could not be completed.
                </p>
              )}
            </section>
          )}

          {diagnosis && (
            <section className="rounded-2xl border border-blue-100 bg-white p-6 shadow-sm sm:p-8">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-700">
                    Diagnosis
                  </p>
                  <h2 className="mt-2 text-xl font-semibold text-slate-950">
                    {diagnosis.root_cause}
                  </h2>
                </div>
                <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-sm font-semibold text-emerald-800">
                  {diagnosis.confidence}% confidence
                </span>
              </div>
              <div className="mt-6 grid gap-5">
                <div>
                  <h3 className="text-sm font-semibold text-slate-800">
                    Explanation
                  </h3>
                  <p className="mt-1.5 text-sm leading-6 text-slate-600">
                    {diagnosis.explanation}
                  </p>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-800">
                    Suggested fix
                  </h3>
                  <p className="mt-1.5 text-sm leading-6 text-slate-600">
                    {diagnosis.fix}
                  </p>
                </div>
                {diagnosis.kubectl_command && (
                  <div>
                    <h3 className="text-sm font-semibold text-slate-800">
                      kubectl command
                    </h3>
                    <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-950 px-4 py-3 text-xs leading-5 text-slate-100">
                      <code>{diagnosis.kubectl_command}</code>
                    </pre>
                  </div>
                )}
                <div>
                  <h3 className="text-sm font-semibold text-slate-800">
                    Prevention
                  </h3>
                  <p className="mt-1.5 text-sm leading-6 text-slate-600">
                    {diagnosis.prevention_recommendation}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    {diagnosis.confidence_reasoning}
                  </p>
                </div>
              </div>
            </section>
          )}
        </div>

        <aside className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">
                Recent investigations
              </h2>
              <p className="mt-1 text-sm text-slate-500">Your latest 10 runs</p>
            </div>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
              History
            </span>
          </div>

          {historyQuery.isPending ? (
            <p className="mt-6 text-sm text-slate-500">Loading history...</p>
          ) : historyQuery.isError ? (
            <p role="alert" className="mt-6 text-sm text-rose-700">
              Could not load history: {historyQuery.error.message}
            </p>
          ) : historyQuery.data.length === 0 ? (
            <p className="mt-6 rounded-lg bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-500">
              No investigations yet. Run an investigation to see its diagnosis
              and status here.
            </p>
          ) : (
            <ul className="mt-5 divide-y divide-slate-100">
              {historyQuery.data.map((record) => (
                <li key={record.id} className="py-4 first:pt-0 last:pb-0">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-medium leading-5 text-slate-800">
                      {record.root_cause ??
                        (record.status === "running"
                          ? "Investigation in progress"
                          : "No diagnosis available")}
                    </p>
                    <span
                      className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-medium ${
                        record.status === "success"
                          ? "bg-emerald-50 text-emerald-700"
                          : record.status === "error"
                            ? "bg-rose-50 text-rose-700"
                            : "bg-blue-50 text-blue-700"
                      }`}
                    >
                      {formatStatus(record.status)}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                    <span>{new Date(record.created_at).toLocaleString()}</span>
                    {record.namespace && <span>{record.namespace}</span>}
                    {record.confidence !== null && (
                      <span>{record.confidence}% confidence</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </section>

      <footer className="border-t border-slate-200 py-5 text-xs leading-5 text-slate-500">
        Cluster access is read-only. Diagnosis commands are suggestions for
        review and are never executed by this app.
      </footer>
    </main>
  );
}
