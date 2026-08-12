/** Persistent disclosure for live and completed multi-agent execution activity. */

"use client";

import { useId, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Loader2,
} from "lucide-react";

import { ActivityStream } from "@/components/ActivityStream";
import type { ActivityStep } from "@/types/streaming";

export interface ExecutionActivityDisclosureProps {
  steps: ActivityStep[];
  isStreaming: boolean;
  error?: string | null;
  compact?: boolean;
  className?: string;
  streamClassName?: string;
}

export function ExecutionActivityDisclosure({
  steps,
  isStreaming,
  error = null,
  compact = false,
  className = "",
  streamClassName = "",
}: ExecutionActivityDisclosureProps) {
  const contentId = useId();
  const [manualExpansion, setManualExpansion] = useState<boolean | null>(null);

  if (steps.length === 0 && !isStreaming) return null;

  // Live work and failures stay visible. Successful completion falls back to
  // the user's disclosure choice, which starts collapsed for each stream.
  const isExpanded = isStreaming || (manualExpansion ?? Boolean(error));
  const completedCount = steps.filter(
    (step) => step.status === "done" || step.status === "skipped",
  ).length;

  const status = isStreaming
    ? "Working"
    : error
      ? "Execution failed"
      : `${completedCount} of ${steps.length} steps completed`;

  return (
    <section
      className={`overflow-hidden rounded-lg border border-slate-700/50 bg-slate-900/25 ${className}`.trim()}
      aria-label="Execution activity"
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition hover:bg-slate-800/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D4AF37]/70"
        aria-controls={contentId}
        aria-expanded={isExpanded}
        onClick={() => {
          if (!isStreaming) {
            setManualExpansion((expanded) => !(expanded ?? Boolean(error)));
          }
        }}
      >
        <StatusIcon isStreaming={isStreaming} hasError={Boolean(error)} />
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-medium text-slate-300">
            Execution activity
          </span>
          <span className="block truncate text-[10px] text-slate-500">
            {status}
          </span>
        </span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-slate-500 transition-transform ${isExpanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {isExpanded && (
        <div id={contentId} className="border-t border-slate-700/40 px-3 py-2.5">
          <ActivityStream
            steps={steps}
            isStreaming={isStreaming}
            compact={compact}
            className={streamClassName}
          />
          {error && (
            <p className="mt-2 text-[10px] leading-relaxed text-red-400" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function StatusIcon({
  isStreaming,
  hasError,
}: {
  isStreaming: boolean;
  hasError: boolean;
}) {
  if (isStreaming) {
    return (
      <Loader2
        size={14}
        className="shrink-0 animate-spin text-[#D4AF37]"
        aria-hidden="true"
      />
    );
  }
  if (hasError) {
    return (
      <AlertTriangle
        size={14}
        className="shrink-0 text-red-400"
        aria-hidden="true"
      />
    );
  }
  return (
    <Check
      size={14}
      className="shrink-0 text-emerald-400"
      aria-hidden="true"
    />
  );
}
