"use client";

import { Sparkles, X } from "lucide-react";

interface PromptSuggestionPanelProps {
  suggestedPrompt: string;
  intentSummary?: string | null;
  isLoading: boolean;
  error?: string | null;
  onUse: () => void;
  onDismiss: () => void;
}

export function PromptSuggestionPanel({
  suggestedPrompt,
  intentSummary,
  isLoading,
  error,
  onUse,
  onDismiss,
}: PromptSuggestionPanelProps) {
  if (!isLoading && !error && !suggestedPrompt) return null;

  return (
    /* ── Design system tokens ──
       bg-background + border-light-blue/20: matches the input bar below
       Left yellow border accent: signals this is an AI suggestion
       (Same yellow CTA language used throughout the system)            */
    <div className="mx-auto mb-3 w-full max-w-3xl rounded-xl border border-light-blue/20 bg-background overflow-hidden">
      {/* Yellow left-border accent strip */}
      <div className="flex">
        <div className="w-0.5 bg-yellow/60 shrink-0" />
        <div className="flex-1 p-3">

          {/* Header row */}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <Sparkles size={13} className="text-yellow" aria-hidden="true" />
              <p className="text-xs font-semibold text-yellow">Suggested prompt</p>
            </div>
            {!isLoading && (
              <button
                type="button"
                onClick={onDismiss}
                className="text-slate-600 hover:text-slate-300 transition-colors p-0.5 rounded"
                aria-label="Dismiss suggestion"
              >
                <X size={13} aria-hidden="true" />
              </button>
            )}
          </div>

          {/* Content */}
          {isLoading ? (
            <div className="space-y-1.5 mt-1">
              <div className="h-3 bg-light-blue/10 rounded animate-pulse w-full" />
              <div className="h-3 bg-light-blue/10 rounded animate-pulse w-4/5" />
              <div className="h-3 bg-light-blue/10 rounded animate-pulse w-3/5" />
            </div>
          ) : error ? (
            <p className="text-sm text-red-400 leading-relaxed">{error}</p>
          ) : (
            <>
              <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
                {suggestedPrompt}
              </p>
              {intentSummary && (
                <p className="mt-1.5 text-xs text-light-blue/70 italic">{intentSummary}</p>
              )}
              {/* Action buttons
                  Primary: bg-yellow text-dark-blue — matches system CTA
                  Secondary: ghost border — matches login page secondary btn */}
              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={onUse}
                  className="rounded-lg bg-yellow px-3.5 py-1.5 text-xs font-bold text-dark-blue hover:bg-yellow/90 active:scale-95 transition-all shadow-sm"
                >
                  Use this
                </button>
                <button
                  type="button"
                  onClick={onDismiss}
                  className="rounded-lg border border-light-blue/30 px-3.5 py-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-light-blue/10 transition-colors"
                >
                  Dismiss
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}