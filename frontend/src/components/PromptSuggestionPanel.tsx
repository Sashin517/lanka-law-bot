"use client";

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
    <div className="mx-auto mb-3 w-full max-w-3xl rounded-xl border border-slate-600/40 bg-[#202020] p-3">
      <p className="text-xs font-semibold text-[#D4AF37]">Suggested prompt</p>

      {isLoading ? (
        <p className="mt-2 text-sm text-slate-400">Improving your prompt...</p>
      ) : error ? (
        <p className="mt-2 text-sm text-red-300">{error}</p>
      ) : (
        <>
          <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-200">
            {suggestedPrompt}
          </p>
          {intentSummary && (
            <p className="mt-1 text-xs text-slate-500">{intentSummary}</p>
          )}
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={onUse}
              className="rounded-md bg-[#D4AF37] px-3 py-1.5 text-xs font-semibold text-[#161B28] transition hover:bg-[#C5A030]"
            >
              Use this
            </button>
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:bg-slate-700/60"
            >
              Dismiss
            </button>
          </div>
        </>
      )}
    </div>
  );
}
