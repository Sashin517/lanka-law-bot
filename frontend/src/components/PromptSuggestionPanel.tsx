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
    <div className="mx-auto mb-3 w-full max-w-3xl rounded-xl border border-app-border/40 bg-app-input p-3">
      <p className="text-xs font-semibold text-app-accent">Suggested prompt</p>

      {isLoading ? (
        <p className="mt-2 text-sm text-app-muted">Improving your prompt...</p>
      ) : error ? (
        <p className="mt-2 text-sm text-app-danger">{error}</p>
      ) : (
        <>
          <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap break-words text-sm leading-relaxed text-app-secondary">
            {suggestedPrompt}
          </p>
          {intentSummary && (
            <p className="mt-1 text-xs text-app-subtle">{intentSummary}</p>
          )}
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={onUse}
              className="rounded-md bg-app-accent px-3 py-1.5 text-xs font-semibold text-app-accent-contrast transition hover:bg-app-accent-hover"
            >
              Use this
            </button>
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-md border border-app-border px-3 py-1.5 text-xs font-semibold text-app-tertiary transition hover:bg-app-hover/60"
            >
              Dismiss
            </button>
          </div>
        </>
      )}
    </div>
  );
}
