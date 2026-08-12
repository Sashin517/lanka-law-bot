/** Accessible real-time timeline for multi-agent execution activity. */

"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, Check, Loader2 } from "lucide-react";

import type { ActivityStep, StreamStepStatus } from "@/types/streaming";

export interface ActivityStreamProps {
  steps: ActivityStep[];
  isStreaming: boolean;
  className?: string;
  compact?: boolean;
}

export function ActivityStream({
  steps,
  isStreaming,
  className = "",
  compact = false,
}: ActivityStreamProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [steps]);

  if (steps.length === 0 && !isStreaming) return null;

  const waitingForNextStep =
    isStreaming &&
    steps.every((step) => step.status === "done" || step.status === "skipped");

  return (
    <div
      ref={containerRef}
      className={`space-y-1 overflow-y-auto ${className}`.trim()}
      role="log"
      aria-label="Execution activity"
      aria-live="polite"
      aria-relevant="additions text"
    >
      {steps.map((step) => (
        <StepItem key={step.id} step={step} compact={compact} />
      ))}

      {waitingForNextStep && (
        <div
          className="flex items-center gap-2 py-1 text-xs text-slate-500"
          role="status"
        >
          <Loader2
            size={12}
            className="shrink-0 animate-spin text-[#D4AF37]"
            aria-hidden="true"
          />
          <span>Processing…</span>
        </div>
      )}
    </div>
  );
}

function StepItem({ step, compact }: { step: ActivityStep; compact: boolean }) {
  const titles = sourceTitles(step);
  const details = step.stepName === "sources" && titles.length > 0
    ? []
    : step.details;
  const hasDetails = details.length > 0 || titles.length > 0;

  return (
    <div className="group" data-step-status={step.status}>
      <div className="flex items-start gap-2 py-0.5">
        <StepIcon status={step.status} />
        <span className={`text-xs leading-relaxed ${statusClass(step.status)}`}>
          {step.label}
          <span className="sr-only"> ({statusLabel(step.status)})</span>
        </span>
      </div>

      {!compact && hasDetails && (
        <details className="ml-5 pb-1" open={step.status === "running" || step.status === "error"}>
          <summary className="cursor-pointer select-none text-[10px] text-slate-500 hover:text-slate-400">
            {titles.length > 0
              ? `${titles.length} source${titles.length === 1 ? "" : "s"}`
              : `${details.length} detail${details.length === 1 ? "" : "s"}`}
          </summary>

          <div className="mt-0.5 space-y-0.5">
            {details.map((detail, index) => (
              <p
                key={`${step.id}-detail-${index}`}
                className="text-[10px] leading-relaxed text-slate-500"
              >
                {detail}
              </p>
            ))}

            {titles.slice(0, 5).map((title, index) => (
              <p
                key={`${step.id}-source-${index}-${title}`}
                className="truncate text-[10px] text-slate-600"
                title={title}
              >
                {title}
              </p>
            ))}
            {titles.length > 5 && (
              <p className="text-[10px] text-slate-600">
                …and {titles.length - 5} more
              </p>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

function StepIcon({ status }: { status: StreamStepStatus }) {
  switch (status) {
    case "running":
      return (
        <Loader2
          size={12}
          className="mt-0.5 shrink-0 animate-spin text-[#D4AF37]"
          aria-hidden="true"
        />
      );
    case "done":
      return (
        <Check
          size={12}
          className="mt-0.5 shrink-0 text-emerald-400"
          aria-hidden="true"
        />
      );
    case "error":
      return (
        <AlertTriangle
          size={12}
          className="mt-0.5 shrink-0 text-red-400"
          aria-hidden="true"
        />
      );
    default:
      return (
        <span
          className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-600"
          aria-hidden="true"
        />
      );
  }
}

function statusClass(status: StreamStepStatus): string {
  switch (status) {
    case "running":
      return "font-medium text-slate-200";
    case "done":
      return "text-slate-400";
    case "error":
      return "text-red-400";
    default:
      return "text-slate-500";
  }
}

function statusLabel(status: StreamStepStatus): string {
  if (status === "done") return "completed";
  return status;
}

function sourceTitles(step: ActivityStep): string[] {
  return Array.isArray(step.metadata.titles)
    ? step.metadata.titles.filter(
        (title): title is string => typeof title === "string" && title.trim().length > 0,
      )
    : [];
}
