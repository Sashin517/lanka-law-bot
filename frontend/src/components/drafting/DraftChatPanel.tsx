"use client";

import {
  AlertTriangle,
  Check,
  ChevronDown,
  CircleCheck,
  LoaderCircle,
  MessageCircleQuestion,
  PencilLine,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import {
  Fragment,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { ExecutionActivityDisclosure } from "@/components/ExecutionActivityDisclosure";
import {
  chatEditService,
  StaleDraftEditError,
} from "@/lib/drafting/chatEditService";
import { documentBuilder } from "@/lib/drafting/documentBuilder";
import { isSSEEndpointUnavailableError } from "@/lib/sseClient";
import { useActivityStream } from "@/lib/useActivityStream";
import { useContainedAutoScroll } from "@/lib/useContainedAutoScroll";
import {
  StaleEditorSelectionError,
  type IEditorService,
} from "@/lib/drafting/editorService";
import { useChatEditStore } from "@/store/chatEditStore";
import { useDraftDocumentStore } from "@/store/draftDocumentStore";
import { useVersionStore } from "@/store/versionStore";
import { useActivityStreamStore } from "@/store/activityStreamStore";
import type { DraftEditResult, LegalQueryResponse } from "@/lib/api";
import type {
  ChatMessageStatus,
  DraftChatMessage,
  PendingEditSuggestion,
} from "@/types/drafting";

const HEAVY_PROGRESS_DELAY_MS = 2_500;
const HEAVY_PROGRESS_STEP_MS = 2_200;
const HEAVY_STEPS = ["Researching", "Analyzing", "Rewriting", "Verifying"];

export interface DraftChatPanelProps {
  editor: IEditorService | null;
  onBeforeRequest?: () => void;
  onViewCitationSource?: (citationId: string) => void;
}

export function DraftChatPanel({
  editor,
  onBeforeRequest,
  onViewCitationSource,
}: DraftChatPanelProps) {
  const {
    messages,
    currentSelection,
    isProcessing,
    chatMode,
    error,
    setSelection,
    setChatMode,
    addUserMessage,
    addAssistantMessage,
    markEditApplied,
    setMessageStatus,
    setProcessing,
    setError,
  } = useChatEditStore();
  const { draftId, documentIds, documentJson, updateContent, setSources } =
    useDraftDocumentStore();
  const { createVersion, getVersionCount } = useVersionStore();
  const {
    steps: activitySteps,
    isStreaming: activityStreaming,
    error: activityError,
    startStream,
  } = useActivityStream();
  const activitySessionId = useActivityStreamStore((state) => state.sessionId);

  const [input, setInput] = useState("");
  const [loadingKind, setLoadingKind] = useState<"ask" | "edit" | null>(null);
  const [showHeavyProgress, setShowHeavyProgress] = useState(false);
  const [heavyStep, setHeavyStep] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const {
    containerRef: messagesScrollRef,
    onScroll: handleMessagesScroll,
    scrollToBottom: scrollMessagesToBottom,
  } = useContainedAutoScroll<HTMLDivElement>();
  const slowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopProgress = useCallback(() => {
    if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    slowTimerRef.current = null;
    progressTimerRef.current = null;
    setShowHeavyProgress(false);
    setHeavyStep(0);
    setLoadingKind(null);
  }, []);

  const startProgress = useCallback((kind: "ask" | "edit") => {
    setLoadingKind(kind);
    setShowHeavyProgress(false);
    setHeavyStep(0);
    if (kind !== "edit") return;

    slowTimerRef.current = setTimeout(() => {
      setShowHeavyProgress(true);
      progressTimerRef.current = setInterval(() => {
        setHeavyStep((step) => Math.min(step + 1, HEAVY_STEPS.length - 1));
      }, HEAVY_PROGRESS_STEP_MS);
    }, HEAVY_PROGRESS_DELAY_MS);
  }, []);

  useEffect(
    () => () => {
      if (slowTimerRef.current) clearTimeout(slowTimerRef.current);
      if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    },
    [],
  );

  useEffect(() => {
    scrollMessagesToBottom();
  }, [activitySteps, isProcessing, messages, scrollMessagesToBottom]);

  useEffect(() => {
    if (currentSelection) inputRef.current?.focus();
  }, [currentSelection, chatMode]);

  const handleSubmit = async (event?: FormEvent) => {
    event?.preventDefault();
    const instruction = input.trim();
    if (!instruction || isProcessing || !editor || !draftId || !documentJson) {
      return;
    }

    const selection = currentSelection ? { ...currentSelection } : null;
    onBeforeRequest?.();
    const currentDocument = editor.getDocument();
    const currentMarkdown = documentBuilder.toMarkdown(currentDocument);
    addUserMessage(instruction, selection ?? undefined);
    scrollMessagesToBottom(true);
    setInput("");
    setError(null);
    setProcessing(true);
    startProgress(chatMode);

    try {
      if (chatMode === "ask") {
        const request = {
          instruction,
          selection,
          currentContent: currentMarkdown,
          documentIds,
        };
        let answer;
        try {
          const response = await startStream(
            "/api/search/stream",
            chatEditService.buildAskPayload(request),
          );
          if (!response) return;
          answer = chatEditService.mapAskResponse(
            response as unknown as LegalQueryResponse,
          );
        } catch (cause) {
          if (!isSSEEndpointUnavailableError(cause)) throw cause;
          useActivityStreamStore.getState().reset();
          answer = await chatEditService.ask(request);
        }
        addAssistantMessage(answer.content, {
          status: "informational",
          sources: answer.sources,
        });
      } else {
        const request = {
          draftId,
          instruction,
          selection,
          currentDocument,
          currentMarkdown,
          documentIds,
        };
        let suggestion;
        try {
          const response = await startStream(
            "/api/draft/edit/stream",
            chatEditService.buildEditPayload(request),
          );
          if (!response) return;
          suggestion = chatEditService.createSuggestion(
            request,
            response as unknown as DraftEditResult,
          );
        } catch (cause) {
          if (!isSSEEndpointUnavailableError(cause)) throw cause;
          useActivityStreamStore.getState().reset();
          suggestion = await chatEditService.requestEdit(request);
        }
        const isHeavy = suggestion.result.edit_path === "heavy";
        addAssistantMessage(
          isHeavy
            ? `Full revision ready: ${suggestion.result.edit_summary}`
            : `Edit ready: ${suggestion.result.edit_summary}`,
          {
            status: "pending",
            editPath: suggestion.result.edit_path,
            editOperation: chatEditService.buildOperation(suggestion),
            sources: suggestion.result.sources,
            suggestion,
          },
        );
      }
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "The drafting request failed.";
      setError(message);
      addAssistantMessage(message, { status: "failed" });
    } finally {
      stopProgress();
      setProcessing(false);
    }
  };

  const applySuggestion = (
    messageId: string,
    suggestion: PendingEditSuggestion,
  ) => {
    if (!editor) return;
    const existingVersionCount = getVersionCount();
    const targetVersion =
      existingVersionCount === 0 ? 2 : existingVersionCount + 1;

    try {
      const currentSources = useDraftDocumentStore.getState().sources;
      const applied = chatEditService.applySuggestion(
        suggestion,
        editor,
        currentSources,
        targetVersion,
      );

      if (existingVersionCount === 0) {
        createVersion(
          suggestion.baseDocument,
          currentSources,
          "Original AI-generated draft.",
          "ai",
        );
      }
      updateContent(applied.document, applied.markdown);
      setSources(applied.sources);
      createVersion(
        applied.document,
        applied.sources,
        `${applied.editPath === "heavy" ? "AI revision" : "AI edit"}: ${applied.summary}`,
        "ai",
      );
      markEditApplied(messageId);
      setSelection(null);
      setError(null);
      editor.focus();
    } catch (cause) {
      if (
        cause instanceof StaleDraftEditError ||
        cause instanceof StaleEditorSelectionError
      ) {
        setMessageStatus(messageId, "stale");
      }
      setError(
        cause instanceof Error
          ? cause.message
          : "The suggestion could not be applied.",
      );
    }
  };

  const rejectSuggestion = (messageId: string) => {
    setMessageStatus(messageId, "rejected");
  };

  const canSubmit = Boolean(
    input.trim() && editor && draftId && documentJson && !isProcessing,
  );

  const completedActivityAssistantId =
    !activityStreaming &&
    activitySteps.length > 0 &&
    messages.at(-1)?.role === "assistant"
      ? messages.at(-1)?.id
      : null;

  const renderDraftActivity = () => (
    <ExecutionActivityDisclosure
      key={activitySessionId ?? "draft-chat-activity"}
      steps={activitySteps}
      isStreaming={activityStreaming}
      error={activityError}
      compact
    />
  );

  return (
    <aside
      className="flex min-h-0 w-[360px] shrink-0 flex-col overflow-hidden border-l border-app-border/50 bg-app-panel"
      id="draft-chat-panel"
      aria-label="Drafting assistant"
    >
      <div
        ref={messagesScrollRef}
        onScroll={handleMessagesScroll}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-4 [overflow-anchor:none] chat-scroll"
        aria-live="polite"
      >
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center px-5 text-center">
            <Sparkles size={24} className="mb-3 text-app-accent" />
            <p className="text-sm font-medium text-app-secondary">
              Refine your draft
            </p>
            <p className="mt-1 text-xs leading-relaxed text-app-subtle">
              Select text to ask a question or request an edit. AI edits remain
              pending until you apply them.
            </p>
          </div>
        )}

        {messages.map((message) => (
          <Fragment key={message.id}>
            {completedActivityAssistantId === message.id &&
              renderDraftActivity()}
            <ChatMessage
              message={message}
              onApply={applySuggestion}
              onReject={rejectSuggestion}
              onViewCitationSource={onViewCitationSource}
            />
          </Fragment>
        ))}

        {(activityStreaming || activitySteps.length > 0) &&
          !completedActivityAssistantId &&
          renderDraftActivity()}

        {isProcessing && !activityStreaming && activitySteps.length === 0 && (
          <ProcessingIndicator
            kind={loadingKind}
            showHeavyProgress={showHeavyProgress}
            heavyStep={heavyStep}
          />
        )}
        <div aria-hidden="true" />
      </div>

      <form
        onSubmit={(event) => void handleSubmit(event)}
        className="shrink-0 border-t border-app-border/50 p-3"
      >
        {currentSelection && (
          <div className="mb-2 flex items-start gap-2 rounded-lg border border-app-accent/20 bg-app-accent/5 px-2.5 py-2">
            <span className="min-w-0 flex-1 truncate text-[10px] italic text-app-muted">
              “{currentSelection.text}”
            </span>
            <button
              type="button"
              onClick={() => setSelection(null)}
              className="text-app-subtle transition hover:text-app-strong"
              aria-label="Clear selected text context"
            >
              <X size={12} />
            </button>
          </div>
        )}

        <div className="rounded-lg border border-app-border/50 bg-app-panel-muted px-3 py-2.5 focus-within:border-app-accent/50">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSubmit();
              }
            }}
            rows={2}
            maxLength={12_000}
            placeholder={
              chatMode === "ask"
                ? "Ask about this document…"
                : "Edit this document…"
            }
            disabled={!editor || isProcessing}
            className="w-full resize-none bg-transparent text-sm text-app-strong outline-none placeholder:text-app-subtle disabled:cursor-not-allowed"
            id="draft-chat-input"
          />
          <div className="mt-1 flex items-center justify-between">
            <div className="flex items-center gap-1 rounded-md bg-app-overlay/30 p-0.5">
              <ModeButton
                active={chatMode === "ask"}
                icon={<MessageCircleQuestion size={12} />}
                label="Ask"
                onClick={() => setChatMode("ask")}
              />
              <ModeButton
                active={chatMode === "edit"}
                icon={<PencilLine size={12} />}
                label="Edit"
                onClick={() => setChatMode("edit")}
              />
            </div>
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded-md bg-app-accent p-1.5 text-app-accent-contrast transition hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-30"
              aria-label={chatMode === "ask" ? "Ask question" : "Request edit"}
            >
              <Send size={14} />
            </button>
          </div>
        </div>
        {error && (
          <p
            className="mt-2 flex items-start gap-1.5 text-[10px] text-app-danger"
            role="alert"
          >
            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
            {error}
          </p>
        )}
      </form>
    </aside>
  );
}

function ModeButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1 rounded px-2 py-1 text-[10px] transition ${
        active
          ? "bg-app-accent/15 text-app-accent"
          : "text-app-subtle hover:text-app-tertiary"
      }`}
      aria-pressed={active}
    >
      {icon}
      {label}
    </button>
  );
}

function ChatMessage({
  message,
  onApply,
  onReject,
  onViewCitationSource,
}: {
  message: DraftChatMessage;
  onApply: (messageId: string, suggestion: PendingEditSuggestion) => void;
  onReject: (messageId: string) => void;
  onViewCitationSource?: (citationId: string) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[92%] rounded-xl px-3 py-2.5 ${
          isUser
            ? "bg-app-accent/15 text-app-primary"
            : "border border-app-border/50 bg-app-panel-muted text-app-tertiary"
        }`}
      >
        {message.selection && isUser && (
          <p className="mb-1.5 truncate border-l-2 border-app-accent/50 pl-2 text-[9px] italic text-app-muted">
            {message.selection.text}
          </p>
        )}
        {isUser ? (
          <p className="whitespace-pre-wrap text-xs leading-relaxed">
            {message.content}
          </p>
        ) : (
          <div className="text-xs">
            <MarkdownRenderer
              content={message.content}
              sources={message.sources}
              onViewInSources={
                message.status === "applied" ? onViewCitationSource : undefined
              }
            />
          </div>
        )}

        {message.suggestion && (
          <SuggestionCard
            message={message}
            onApply={() => onApply(message.id, message.suggestion!)}
            onReject={() => onReject(message.id)}
          />
        )}

        <div className="mt-1.5 flex items-center justify-between gap-2">
          <span className="text-[9px] text-app-faint">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          {!isUser && message.status && <StatusBadge status={message.status} />}
        </div>
      </div>
    </div>
  );
}

function SuggestionCard({
  message,
  onApply,
  onReject,
}: {
  message: DraftChatMessage;
  onApply: () => void;
  onReject: () => void;
}) {
  const suggestion = message.suggestion!;
  const { result } = suggestion;
  const preview = result.edited_text.slice(0, 600);
  const pending = message.status === "pending";

  return (
    <div className="mt-2.5 rounded-lg border border-app-border/60 bg-app-overlay/30 p-2.5">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-app-accent">
          {result.edit_path === "heavy" ? "Full revision" : "Suggested edit"}
        </span>
        <span className="text-[9px] text-app-subtle">
          {result.confidence} confidence
        </span>
      </div>
      <p className="max-h-28 overflow-y-auto whitespace-pre-wrap text-[10px] leading-relaxed text-app-muted chat-scroll">
        {preview}
        {result.edited_text.length > preview.length ? "…" : ""}
      </p>

      {result.execution_trace && (
        <details className="mt-2 text-[10px] text-app-muted">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-app-tertiary">
            <ChevronDown size={11} />
            Execution trace ({result.execution_trace.steps_executed.length}{" "}
            agents)
          </summary>
          <ol className="mt-1.5 space-y-1 border-l border-app-border pl-3">
            {result.execution_trace.steps_executed.map((step, index) => (
              <li key={`${step.agent}-${index}`}>
                <span className="font-medium text-app-tertiary">{step.agent}</span>
                : {step.purpose}
              </li>
            ))}
          </ol>
        </details>
      )}

      {pending && (
        <div className="mt-2.5 flex items-center gap-2">
          <button
            type="button"
            onClick={onApply}
            className="flex flex-1 items-center justify-center gap-1 rounded-md bg-app-success/15 px-2 py-1.5 text-[10px] font-medium text-app-success transition hover:bg-app-success/25"
          >
            <Check size={12} /> Apply
          </button>
          <button
            type="button"
            onClick={onReject}
            className="flex flex-1 items-center justify-center gap-1 rounded-md bg-app-danger/10 px-2 py-1.5 text-[10px] font-medium text-app-danger transition hover:bg-app-danger/20"
          >
            <X size={12} /> Reject
          </button>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: ChatMessageStatus }) {
  const labels: Record<ChatMessageStatus, string> = {
    informational: "Answered",
    pending: "Pending review",
    applied: "Applied",
    rejected: "Rejected",
    stale: "Stale",
    failed: "Failed",
  };
  const color =
    status === "applied" || status === "informational"
      ? "text-app-success"
      : status === "pending"
        ? "text-app-accent"
        : "text-app-danger";
  return (
    <span className={`flex items-center gap-1 text-[9px] ${color}`}>
      {(status === "applied" || status === "informational") && (
        <CircleCheck size={10} />
      )}
      {labels[status]}
    </span>
  );
}

function ProcessingIndicator({
  kind,
  showHeavyProgress,
  heavyStep,
}: {
  kind: "ask" | "edit" | null;
  showHeavyProgress: boolean;
  heavyStep: number;
}) {
  if (kind === "edit" && showHeavyProgress) {
    return (
      <div className="rounded-xl border border-app-accent/20 bg-app-panel-muted p-3">
        <p className="mb-2 text-[10px] font-medium text-app-tertiary">
          Complex revision in progress…
        </p>
        <div className="grid grid-cols-4 gap-1">
          {HEAVY_STEPS.map((step, index) => (
            <div key={step} className="min-w-0">
              <div
                className={`mb-1 h-1 rounded-full ${
                  index <= heavyStep ? "bg-app-accent" : "bg-app-hover"
                }`}
              />
              <span
                className={`text-[8px] ${index <= heavyStep ? "text-app-accent" : "text-app-faint"}`}
              >
                {step}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-xl border border-app-border/50 bg-app-panel-muted px-3 py-2.5 text-[11px] text-app-muted">
      <LoaderCircle size={14} className="animate-spin text-app-accent" />
      {kind === "ask"
        ? "Researching your question…"
        : "Applying edit analysis…"}
    </div>
  );
}
