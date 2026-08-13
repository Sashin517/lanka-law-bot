"use client";

import { Fragment, useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  ChevronDown,
  ChevronUp,
  X,
  PenTool,
  CheckSquare,
  BarChart2,
  User,
  Scale,
  AlertTriangle,
  Info,
  FileText,
  LogOut,
} from "lucide-react";
import Link from "next/link";

import { ChatInputBar } from "@/components/ChatInputBar";
import { ChatHistorySidebar } from "@/components/ChatHistorySidebar";
import { ExecutionActivityDisclosure } from "@/components/ExecutionActivityDisclosure";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { PromptSuggestionPanel } from "@/components/PromptSuggestionPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  deleteDocument,
  getDocumentStatus,
  improvePrompt,
  uploadDocument,
  type ImprovePromptResponse,
  type SourceRef,
} from "@/lib/api";
import { logOut } from "@/lib/firebase/auth";
import { sourceCardId } from "@/lib/sources";
import { useContainedAutoScroll } from "@/lib/useContainedAutoScroll";
import { useAuth } from "@/contexts/AuthProvider";
import { useDraftDocumentStore } from "@/store/draftDocumentStore";
import { useConversationStore } from "@/store/conversationStore";
import { useActivityStreamStore } from "@/store/activityStreamStore";
import type { UploadedDocument } from "@/types/documents";
import type { QueryMode } from "@/types/QueryMode";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

/* ------------------------------------------------------------------ */
/* Main Component                                                      */
/* ------------------------------------------------------------------ */

export default function ResearchDashboard() {
  const router = useRouter();
  const startDraft = useDraftDocumentStore((state) => state.startDraft);
  const messages = useConversationStore((state) => state.messages);
  const activeConversationId = useConversationStore(
    (state) => state.activeConversationId,
  );
  const isSending = useConversationStore((state) => state.isSending);
  const isCreating = useConversationStore((state) => state.isCreating);
  const isMessagesLoading = useConversationStore(
    (state) => state.isMessagesLoading,
  );
  const newConversation = useConversationStore(
    (state) => state.newConversation,
  );
  const sendConversationMessage = useConversationStore((state) => state.send);
  const stopConversationMessage = useConversationStore(
    (state) => state.stopSending,
  );
  const clearActiveConversation = useConversationStore(
    (state) => state.clearActive,
  );
  const activitySteps = useActivityStreamStore((state) => state.steps);
  const activityStreaming = useActivityStreamStore(
    (state) => state.isStreaming,
  );
  const activityError = useActivityStreamStore((state) => state.error);
  const activitySessionId = useActivityStreamStore((state) => state.sessionId);
  const [inputQuery, setInputQuery] = useState("");
  const isLoading = isSending || isCreating;
  const [uploadedDocuments, setUploadedDocuments] = useState<
    UploadedDocument[]
  >([]);
  const [selectedMode, setSelectedMode] = useState<QueryMode>("quick_qa");
  const [isImproving, setIsImproving] = useState(false);
  const [promptSuggestion, setPromptSuggestion] =
    useState<ImprovePromptResponse | null>(null);
  const [improveError, setImproveError] = useState<string | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);

  // Collapsible state for bot responses (keyed by message id)
  const [expandedSources, setExpandedSources] = useState<Set<string>>(
    new Set(),
  );

  // Sidebar – Added materials
  const [addedMaterials, setAddedMaterials] = useState<SourceRef[]>([]);

  const {
    containerRef: chatScrollRef,
    onScroll: handleChatScroll,
    scrollToBottom: scrollChatToBottom,
  } = useContainedAutoScroll<HTMLDivElement>();
  const pollingTimersRef = useRef<Map<string, ReturnType<typeof setInterval>>>(
    new Map(),
  );

  const { user, loading: authLoading } = useAuth();

  useEffect(() => {
    scrollChatToBottom();
  }, [activitySteps, isLoading, messages, scrollChatToBottom]);

  useEffect(() => {
    setExpandedSources(new Set());
    setAddedMaterials([]);
    setDocumentError(null);
  }, [activeConversationId]);

  useEffect(() => {
    const timers = pollingTimersRef.current;
    return () => {
      timers.forEach((timer) => clearInterval(timer));
      timers.clear();
    };
  }, []);

  /* ---------------------------------------------------------------- */
  /* Handlers                                                          */
  /* ---------------------------------------------------------------- */

  const validateFile = (file: File) => {
    const allowedExtensions = [".pdf", ".docx", ".txt", ".md"];
    const lowerName = file.name.toLowerCase();
    if (!allowedExtensions.some((ext) => lowerName.endsWith(ext))) {
      throw new Error("Upload a PDF, DOCX, TXT, or Markdown file.");
    }
    if (file.size > 50 * 1024 * 1024) {
      throw new Error("File size must be 50 MB or less.");
    }
  };

  const updateDocument = (
    key: string,
    updater: (doc: UploadedDocument) => UploadedDocument,
  ) => {
    setUploadedDocuments((prev) =>
      prev.map((doc) =>
        doc.local_id === key || doc.document_id === key ? updater(doc) : doc,
      ),
    );
  };

  const stopPolling = (documentId: string) => {
    const timer = pollingTimersRef.current.get(documentId);
    if (timer) {
      clearInterval(timer);
      pollingTimersRef.current.delete(documentId);
    }
  };

  const startStatusPolling = (documentId: string) => {
    stopPolling(documentId);

    const poll = async () => {
      try {
        const status = await getDocumentStatus(documentId);
        setUploadedDocuments((prev) =>
          prev.map((doc) =>
            doc.document_id === documentId
              ? {
                  ...doc,
                  job_id: status.job_id ?? doc.job_id,
                  filename: status.filename,
                  status: status.status,
                  chunk_count: status.chunk_count,
                  error: status.error,
                  file: undefined,
                }
              : doc,
          ),
        );
        if (status.status === "completed" || status.status === "failed") {
          stopPolling(documentId);
        }
      } catch (error) {
        setUploadedDocuments((prev) =>
          prev.map((doc) =>
            doc.document_id === documentId
              ? {
                  ...doc,
                  status: "failed",
                  error:
                    error instanceof Error
                      ? error.message
                      : "Unable to check document status.",
                }
              : doc,
          ),
        );
        stopPolling(documentId);
      }
    };

    void poll();
    pollingTimersRef.current.set(documentId, setInterval(poll, 1500));
  };

  const handleFileSelected = async (file: File) => {
    const localId = crypto.randomUUID();
    try {
      validateFile(file);
    } catch (error) {
      setUploadedDocuments((prev) => [
        ...prev,
        {
          local_id: localId,
          document_id: localId,
          job_id: "",
          filename: file.name,
          status: "failed",
          error: error instanceof Error ? error.message : "Invalid file.",
          file,
          uploaded_at: new Date().toISOString(),
        },
      ]);
      return;
    }

    setUploadedDocuments((prev) => [
      ...prev,
      {
        local_id: localId,
        document_id: localId,
        job_id: "",
        filename: file.name,
        status: "queued",
        file,
        uploaded_at: new Date().toISOString(),
      },
    ]);

    try {
      const uploaded = await uploadDocument(file);
      updateDocument(localId, (doc) => ({
        ...doc,
        document_id: uploaded.document_id,
        job_id: uploaded.job_id,
        filename: uploaded.filename,
        status: uploaded.status,
        file: undefined,
      }));
      startStatusPolling(uploaded.document_id);
    } catch (error) {
      updateDocument(localId, (doc) => ({
        ...doc,
        status: "failed",
        error:
          error instanceof Error ? error.message : "Document upload failed.",
      }));
    }
  };

  const handleRemoveDocument = async (documentId: string) => {
    stopPolling(documentId);
    const doc = uploadedDocuments.find(
      (item) => item.document_id === documentId || item.local_id === documentId,
    );
    setUploadedDocuments((prev) =>
      prev.filter(
        (item) =>
          item.document_id !== documentId && item.local_id !== documentId,
      ),
    );

    if (doc?.job_id && doc.document_id !== doc.local_id) {
      try {
        await deleteDocument(doc.document_id);
      } catch {
        setDocumentError(
          `The document was removed here, but the backend could not delete “${doc.filename}”.`,
        );
      }
    }
  };

  const handleSend = async () => {
    if (!inputQuery.trim() || isLoading) return;
    if (uploadedDocuments.some((doc) => doc.status !== "completed")) return;

    const attachedDocuments = uploadedDocuments
      .filter((doc) => doc.status === "completed")
      .map((doc) => ({
        document_id: doc.document_id,
        filename: doc.filename,
        status: doc.status,
      }));

    const query = inputQuery.trim();
    setInputQuery("");
    setPromptSuggestion(null);
    setImproveError(null);

    if (selectedMode === "drafting") {
      void startDraft(
        query,
        attachedDocuments.map((document) => document.document_id),
      );
      router.push("/draft");
      return;
    }

    // A deliberate submission resumes follow mode. Subsequent SSE updates stay
    // container-scoped and stop following again if the user scrolls upward.
    scrollChatToBottom(true);

    try {
      if (!activeConversationId) {
        await newConversation(selectedMode);
      }
      await sendConversationMessage(
        query,
        selectedMode,
        attachedDocuments.map((document) => document.document_id),
        attachedDocuments,
      );
    } catch {
      // Store actions expose a stable, dismissible error in the sidebar.
    }
  };

  const handleImprove = async () => {
    const draft = inputQuery.trim();
    if (!draft || isLoading || isImproving) return;
    if (uploadedDocuments.some((doc) => doc.status !== "completed")) return;

    setIsImproving(true);
    setImproveError(null);

    try {
      const result = await improvePrompt({
        draft,
        mode: selectedMode,
        has_documents: uploadedDocuments.some((doc) => doc.status === "completed"),
      });
      setPromptSuggestion(result);
    } catch (error) {
      setPromptSuggestion(null);
      setImproveError(
        error instanceof Error
          ? error.message
          : "Unable to improve the prompt right now.",
      );
    } finally {
      setIsImproving(false);
    }
  };

  const handleNewChat = async () => {
    clearActiveConversation();
    setInputQuery("");
    setUploadedDocuments([]);
    setPromptSuggestion(null);
    setImproveError(null);
    await newConversation(selectedMode);
  };

  const toggleSources = (id: string) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const scrollToSource = (messageId: string, citationId: string) => {
    setExpandedSources((prev) => new Set(prev).add(messageId));
    requestAnimationFrame(() => {
      document
        .getElementById(sourceCardId(messageId, citationId))
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  };

  const addMaterial = (src: SourceRef) => {
    if (!addedMaterials.find((m) => m.citation_id === src.citation_id)) {
      setAddedMaterials((prev) => [...prev, src]);
    }
  };

  const removeMaterial = (citationId: string) => {
    setAddedMaterials((prev) =>
      prev.filter((m) => m.citation_id !== citationId),
    );
  };

  const confidenceColor = (c?: string) => {
    if (c === "high")
      return "text-app-success bg-app-success/10 border-app-success/30";
    if (c === "medium")
      return "text-app-warning bg-app-warning/10 border-app-warning/30";
    return "text-app-danger bg-app-danger/10 border-app-danger/30";
  };

  const confidenceDots = (c?: string) => {
    const filled = c === "high" ? 3 : c === "medium" ? 2 : 1;
    return Array.from({ length: 3 }, (_, i) => (
      <span
        key={i}
        className={`inline-block w-2 h-2 rounded-full mr-0.5 ${i < filled ? "bg-current" : "bg-app-disabled"}`}
      />
    ));
  };

  const completedActivityAssistantId =
    !activityStreaming &&
    activitySteps.length > 0 &&
    messages.at(-1)?.role === "assistant"
      ? messages.at(-1)?.id
      : null;

  const renderResearchActivity = () => (
    <div className="flex justify-start">
      <div className="w-full max-w-[85%] rounded-2xl rounded-bl-md border border-app-border/50 bg-app-panel px-5 py-4 shadow-lg">
        <div className="flex items-center gap-2">
          <Scale size={14} className="text-app-accent" />
          <span className="text-app-accent text-sm font-semibold">
            LankaLawBot
          </span>
        </div>
        <ExecutionActivityDisclosure
          key={activitySessionId ?? "research-activity"}
          steps={activitySteps}
          isStreaming={activityStreaming}
          error={activityError}
          className="mt-3"
          streamClassName="max-h-64 pr-1 chat-scroll"
        />
      </div>
    </div>
  );

  /* ---------------------------------------------------------------- */
  /* Render                                                            */
  /* ---------------------------------------------------------------- */

  return (
    <div className="flex h-dvh max-h-dvh min-h-0 flex-col overflow-hidden bg-app-canvas font-sans text-app-primary">
      {/* ── NAVBAR ── */}
      <header className="bg-app-panel text-app-strong flex items-center justify-between px-8 py-4 z-10 border-b border-app-border/50 shrink-0">
        <div className="text-2xl font-serif tracking-wide text-app-strong flex items-center gap-2">
          <Scale size={24} className="text-app-accent" />
          LankaLawBot
        </div>
        <nav className="flex space-x-12">
          <button className="flex items-center space-x-2 text-app-accent border-b-2 border-app-accent pb-1">
            <Search size={18} />
            <span>Research</span>
          </button>
          <Link
            href="/draft"
            className="flex items-center space-x-2 text-app-muted hover:text-app-strong transition"
          >
            <PenTool size={18} />
            <span>Draft</span>
          </Link>
          <button className="flex items-center space-x-2 text-app-muted hover:text-app-strong transition">
            <CheckSquare size={18} />
            <span>Verify</span>
          </button>
          <button className="flex items-center space-x-2 text-app-muted hover:text-app-strong transition">
            <BarChart2 size={18} />
            <span>Analyze</span>
          </button>
        </nav>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          {authLoading ? (
            <div className="h-10 w-10 rounded-full bg-app-elevated animate-pulse" />
          ) : user ? (
            <div className="flex items-center gap-3">
              {user.photoURL ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={user.photoURL}
                  alt={user.displayName ?? "User avatar"}
                  className="h-9 w-9 rounded-full object-cover"
                />
              ) : (
                <div className="bg-app-elevated p-2 rounded-full">
                  <User size={20} className="text-app-tertiary" />
                </div>
              )}
              <div className="text-right">
                <p className="text-sm text-app-strong truncate max-w-[160px]">
                  {user.displayName || user.email}
                </p>
                {user.displayName && user.email && (
                  <p className="text-xs text-app-muted truncate max-w-[160px]">
                    {user.email}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => void logOut()}
                className="text-xs text-app-muted hover:text-app-strong transition cursor-pointer hover:bg-app-disabled p-2 rounded-full border border-app-border/50"
              >
                Log out <LogOut className="inline size-4" />
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="bg-app-elevated p-2 rounded-full cursor-pointer hover:bg-app-disabled transition"
            >
              <User size={20} className="text-app-tertiary" />
            </Link>
          )}
        </div>
      </header>

      {/* ── BODY: 3-column layout ── */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <ChatHistorySidebar onNewChat={handleNewChat} />

        {/* ──────── CENTER: CHAT AREA ──────── */}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-app-elevated">
          {/* Messages */}
          <div
            ref={chatScrollRef}
            onScroll={handleChatScroll}
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-6 [overflow-anchor:none] chat-scroll"
          >
            <div className="max-w-3xl mx-auto space-y-5">
              {/* Welcome state */}
              {messages.length === 0 && !isLoading && !isMessagesLoading && (
                <div className="flex flex-col items-center justify-center h-full py-24 text-center">
                  <Scale size={48} className="text-app-accent mb-4" />
                  <h2 className="text-xl font-serif text-app-strong mb-2">
                    Welcome to LankaLawBot
                  </h2>
                  <p className="text-app-muted text-sm max-w-md">
                    Ask any question about Sri Lankan law. The AI will search
                    through acts and case laws, then provide a cited, structured
                    answer.
                  </p>
                </div>
              )}

              {/* Chat messages */}
              {messages.map((msg) =>
                msg.role === "user" ? (
                  /* ── User bubble ── */
                  <div key={msg.id} className="flex justify-end">
                    <div className="max-w-[75%]">
                      <div className="bg-app-accent text-app-accent-contrast px-5 py-3 rounded-2xl rounded-br-md shadow-md">
                        <p className="text-sm font-medium leading-relaxed">
                          {msg.content}
                        </p>
                        {msg.attachments.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {msg.attachments.map((doc) => (
                                <div
                                  key={doc.document_id}
                                  className="flex max-w-full items-center gap-1.5 rounded-lg bg-app-panel/15 px-2 py-1 text-[11px] font-semibold"
                                  title={doc.filename}
                                >
                                  <FileText size={12} />
                                  <span className="max-w-[220px] truncate">
                                    {doc.filename}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                      </div>
                      <p className="text-[10px] text-app-subtle text-right mt-1 mr-1">
                        {new Date(msg.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                ) : (
                  /* ── Bot response ── */
                  <Fragment key={msg.id}>
                    {completedActivityAssistantId === msg.id &&
                      renderResearchActivity()}
                  <div className="flex justify-start">
                    <div className="max-w-[85%] w-full">
                      <div className="bg-app-panel border border-app-border/50 rounded-2xl rounded-bl-md shadow-lg overflow-hidden">
                        {/* Header */}
                        <div className="flex items-center gap-2 px-5 pt-4 pb-2">
                          <Scale size={16} className="text-app-accent" />
                          <span className="text-app-accent font-semibold text-sm">
                            LankaLawBot
                          </span>
                          {msg.confidence && (
                            <span
                              className={`ml-auto text-[11px] px-2 py-0.5 rounded-full border flex items-center gap-1 ${confidenceColor(msg.confidence)}`}
                            >
                              {confidenceDots(msg.confidence)}
                              <span className="ml-1 capitalize">
                                {msg.confidence}
                              </span>
                            </span>
                          )}
                        </div>

                        {/* Main content — markdown or plain text */}
                        <div className="px-5 pb-3">
                          {msg.markdown_content ? (
                            <MarkdownRenderer
                              content={msg.markdown_content}
                              sources={msg.citations}
                              onViewInSources={(citationId) =>
                                scrollToSource(msg.id, citationId)
                              }
                            />
                          ) : (
                            <p className="text-app-secondary text-sm leading-relaxed whitespace-pre-wrap">
                              {msg.content}
                            </p>
                          )}
                        </div>

                        {/* Sources section (collapsible) */}
                        {msg.citations.length > 0 && (
                          <div className="border-t border-app-border/40">
                            <button
                              onClick={() => toggleSources(msg.id)}
                              className="w-full flex items-center justify-between px-5 py-2.5 text-sm text-app-tertiary hover:bg-app-elevated/40 transition"
                            >
                              <span className="flex items-center gap-2">
                                <Info size={14} className="text-app-info" />
                                Sources ({msg.citations.length})
                              </span>
                              {expandedSources.has(msg.id) ? (
                                <ChevronUp size={14} />
                              ) : (
                                <ChevronDown size={14} />
                              )}
                            </button>
                            {expandedSources.has(msg.id) && (
                              <div className="px-5 pb-4 space-y-2">
                                {msg.citations.map((src) => (
                                  <div
                                    key={src.citation_id}
                                    id={sourceCardId(msg.id, src.citation_id)}
                                    className="bg-app-elevated/30 rounded-lg p-3 flex items-start justify-between gap-3 scroll-mt-4"
                                  >
                                    <div className="min-w-0 flex-1">
                                      <div className="flex items-center gap-2 mb-1">
                                        <span className="text-[10px] font-bold bg-app-info/20 text-app-info px-1.5 py-0.5 rounded shrink-0">
                                          {src.citation_id}
                                        </span>
                                        <span className="text-sm font-medium text-app-secondary truncate">
                                          {src.title}
                                        </span>
                                      </div>
                                      <p className="text-[11px] text-app-muted">
                                        {src.year > 0
                                          ? `Year: ${src.year}`
                                          : ""}
                                        {src.section ? ` · ${src.section}` : ""}
                                      </p>
                                      {src.excerpt && (
                                        <p className="text-xs text-app-subtle mt-1 line-clamp-2">
                                          {src.excerpt}
                                        </p>
                                      )}
                                    </div>
                                    <button
                                      onClick={() => addMaterial(src)}
                                      className="text-[10px] font-semibold bg-app-accent/20 text-app-accent hover:bg-app-accent/30 px-2 py-1 rounded transition shrink-0"
                                      title="Add to materials"
                                    >
                                      + Add
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Disclaimer */}
                        {msg.disclaimer && (
                          <div className="border-t border-app-border/40 px-5 py-2.5 flex items-start gap-2">
                            <AlertTriangle
                              size={12}
                              className="text-app-warning mt-0.5 shrink-0"
                            />
                            <p className="text-[11px] text-app-subtle leading-relaxed">
                              {msg.disclaimer}
                            </p>
                          </div>
                        )}
                      </div>
                      <p className="text-[10px] text-app-subtle mt-1 ml-1">
                        {new Date(msg.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                  </Fragment>
                ),
              )}

              {/* Live execution activity for the active research request. */}
              {(activityStreaming || activitySteps.length > 0) &&
              !completedActivityAssistantId ? (
                renderResearchActivity()
              ) : isLoading || isMessagesLoading ? (
                <div className="flex justify-start">
                  <div className="rounded-2xl rounded-bl-md border border-app-border/50 bg-app-panel px-5 py-4 shadow-lg">
                    <div className="flex items-center gap-2">
                      <Scale size={14} className="text-app-accent" />
                      <span className="text-app-accent text-sm font-semibold">
                        LankaLawBot
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-1.5">
                      <span className="typing-dot h-2 w-2 rounded-full bg-app-muted" />
                      <span className="typing-dot h-2 w-2 rounded-full bg-app-muted" />
                      <span className="typing-dot h-2 w-2 rounded-full bg-app-muted" />
                      <span className="ml-2 text-xs text-app-subtle">
                        {isMessagesLoading
                          ? "Loading conversation…"
                          : "Preparing your request…"}
                      </span>
                    </div>
                  </div>
                </div>
              ) : null}

              <div aria-hidden="true" />
            </div>
          </div>

          {/* ── Input bar (bottom-pinned) ── */}
          <div className="shrink-0 border-t border-app-border/40 bg-app-panel-muted px-6 py-4">
            {documentError && (
              <button
                type="button"
                onClick={() => setDocumentError(null)}
                className="mx-auto mb-3 block w-full max-w-3xl rounded-lg border border-app-warning/30 bg-app-warning/10 px-3 py-2 text-left text-xs text-app-warning"
                title="Dismiss document warning"
              >
                {documentError}
              </button>
            )}
            <PromptSuggestionPanel
              suggestedPrompt={promptSuggestion?.improved_prompt ?? ""}
              intentSummary={promptSuggestion?.intent_summary}
              isLoading={isImproving}
              error={improveError}
              onUse={() => {
                if (!promptSuggestion?.improved_prompt) return;
                setInputQuery(promptSuggestion.improved_prompt);
                setPromptSuggestion(null);
                setImproveError(null);
              }}
              onDismiss={() => {
                setPromptSuggestion(null);
                setImproveError(null);
              }}
            />
            <ChatInputBar
              value={inputQuery}
              isLoading={isLoading}
              canStop={isSending}
              isImproving={isImproving}
              documents={uploadedDocuments}
              selectedMode={selectedMode}
              onChange={setInputQuery}
              onFileSelected={handleFileSelected}
              onRemoveDocument={handleRemoveDocument}
              onModeChange={setSelectedMode}
              onSubmit={handleSend}
              onStop={stopConversationMessage}
              onImprove={handleImprove}
            />
          </div>
        </main>

        {/* ──────── RIGHT SIDEBAR: ADDED MATERIALS ──────── */}
        <aside className="min-h-0 w-[280px] shrink-0 overflow-y-auto border-l border-app-border/40 bg-app-panel p-5 text-app-strong chat-scroll">
          <h2 className="text-base font-semibold mb-4 pb-3 border-b border-app-border text-app-secondary">
            Added Materials
          </h2>

          <div className="space-y-3">
            {addedMaterials.length === 0 ? (
              <p className="text-app-subtle text-xs italic leading-relaxed">
                No materials added yet. Expand &quot;Sources&quot; in a response
                and click &quot;+ Add&quot; to save references here for
                drafting.
              </p>
            ) : (
              addedMaterials.map((item) => (
                <div
                  key={item.citation_id}
                  className="flex justify-between items-start group bg-app-elevated/30 rounded-lg p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="text-[10px] font-bold bg-app-info/20 text-app-info px-1.5 py-0.5 rounded shrink-0">
                        {item.citation_id}
                      </span>
                    </div>
                    <h4 className="text-xs text-app-secondary group-hover:text-app-strong transition leading-snug">
                      {item.title}
                    </h4>
                    <p className="text-[10px] text-app-subtle mt-0.5">
                      {item.year > 0 ? `Year: ${item.year}` : ""}
                      {item.section ? ` · ${item.section}` : ""}
                    </p>
                  </div>
                  <button
                    onClick={() => removeMaterial(item.citation_id)}
                    className="text-app-subtle hover:text-app-strong bg-app-hover/50 hover:bg-app-disabled rounded-full p-1 ml-2 transition shrink-0"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
