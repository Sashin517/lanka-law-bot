"use client";

import { useState, useRef, useEffect } from "react";
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
} from "lucide-react";

import { ChatInputBar } from "@/components/ChatInputBar";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import {
  deleteDocument,
  getDocumentStatus,
  sendLegalQuery,
  uploadDocument,
  type SourceRef,
} from "@/lib/api";
import { sourceCardId } from "@/lib/sources";
import type { AttachedDocument, UploadedDocument } from "@/types/documents";
import type { QueryMode } from "@/types/QueryMode";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;                  // Plain text fallback
  markdownContent?: string;         // Rich markdown from backend
  attachedDocuments?: AttachedDocument[];
  sources?: SourceRef[];
  confidence?: string;
  disclaimer?: string;
  timestamp: Date;
}

/* ------------------------------------------------------------------ */
/* Main Component                                                      */
/* ------------------------------------------------------------------ */

export default function ResearchDashboard() {
  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [uploadedDocuments, setUploadedDocuments] = useState<
    UploadedDocument[]
  >([]);
  const [selectedMode, setSelectedMode] = useState<QueryMode>("quick_qa");

  // Collapsible state for bot responses (keyed by message id)
  const [expandedSources, setExpandedSources] = useState<Set<string>>(
    new Set(),
  );

  // Sidebar – Filters
  const [filterSource, setFilterSource] = useState({
    acts: true,
    caseLaws: true,
  });
  const [filterDate, setFilterDate] = useState("all");
  const [openSections, setOpenSections] = useState({
    source: true,
    date: true,
    topic: true,
    court: true,
  });

  // Sidebar – Added materials
  const [addedMaterials, setAddedMaterials] = useState<SourceRef[]>([]);

  // Auto-scroll ref
  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollingTimersRef = useRef<Map<string, ReturnType<typeof setInterval>>>(
    new Map(),
  );

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

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
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `The document was removed from this chat, but the backend could not delete "${doc.filename}".`,
            timestamp: new Date(),
          },
        ]);
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

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: inputQuery.trim(),
      attachedDocuments,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    const query = inputQuery.trim();
    setInputQuery("");
    setIsLoading(true);

    try {
      const data = await sendLegalQuery({
        question: query,
        mode: selectedMode,
        matter_id: null,
        document_ids: attachedDocuments.map((doc) => doc.document_id),
      });

      const botMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.answer || "No response generated.",
        markdownContent: data.markdown_content,
        sources: data.sources || [],
        confidence: data.confidence,
        disclaimer: data.disclaimer,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            "Unable to reach the legal research backend. Please ensure the server is running and try again.",
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleSection = (section: keyof typeof openSections) => {
    setOpenSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };


  const toggleSources = (id: string) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
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
      return "text-emerald-400 bg-emerald-400/10 border-emerald-400/30";
    if (c === "medium")
      return "text-amber-400 bg-amber-400/10 border-amber-400/30";
    return "text-red-400 bg-red-400/10 border-red-400/30";
  };

  const confidenceDots = (c?: string) => {
    const filled = c === "high" ? 3 : c === "medium" ? 2 : 1;
    return Array.from({ length: 3 }, (_, i) => (
      <span
        key={i}
        className={`inline-block w-2 h-2 rounded-full mr-0.5 ${i < filled ? "bg-current" : "bg-slate-600"}`}
      />
    ));
  };

  /* ---------------------------------------------------------------- */
  /* Render                                                            */
  /* ---------------------------------------------------------------- */

  return (
    <div className="h-screen flex flex-col bg-[#2A3241] font-sans overflow-hidden">
      {/* ── NAVBAR ── */}
      <header className="bg-[#161B28] text-white flex items-center justify-between px-8 py-4 z-10 border-b border-slate-700/50 shrink-0">
        <div className="text-2xl font-serif tracking-wide text-white flex items-center gap-2">
          <Scale size={24} className="text-[#D4AF37]" />
          LankaLawBot
        </div>
        <nav className="flex space-x-12">
          <button className="flex items-center space-x-2 text-[#D4AF37] border-b-2 border-[#D4AF37] pb-1">
            <Search size={18} />
            <span>Research</span>
          </button>
          <button className="flex items-center space-x-2 text-slate-400 hover:text-white transition">
            <PenTool size={18} />
            <span>Draft</span>
          </button>
          <button className="flex items-center space-x-2 text-slate-400 hover:text-white transition">
            <CheckSquare size={18} />
            <span>Verify</span>
          </button>
          <button className="flex items-center space-x-2 text-slate-400 hover:text-white transition">
            <BarChart2 size={18} />
            <span>Analyze</span>
          </button>
        </nav>
        <div className="bg-[#2A3241] p-2 rounded-full cursor-pointer hover:bg-slate-600 transition">
          <User size={20} className="text-slate-300" />
        </div>
      </header>

      {/* ── BODY: 3-column layout ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* ──────── LEFT SIDEBAR: FILTERS ──────── */}
        <aside className="w-[260px] bg-[#161B28] text-white p-5 overflow-y-auto shrink-0 border-r border-slate-700/40 chat-scroll">
          <h2 className="text-base font-semibold mb-4 text-slate-200">
            Filters
          </h2>

          {/* Source Type */}
          <div className="mb-4">
            <div
              onClick={() => toggleSection("source")}
              className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm"
            >
              <span>Source Type</span>
              {openSections.source ? (
                <ChevronUp size={16} />
              ) : (
                <ChevronDown size={16} />
              )}
            </div>
            {openSections.source && (
              <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input
                    type="checkbox"
                    checked={filterSource.acts}
                    onChange={(e) =>
                      setFilterSource({
                        ...filterSource,
                        acts: e.target.checked,
                      })
                    }
                    className="w-4 h-4 accent-[#D4AF37]"
                  />
                  <span>Acts</span>
                </label>
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input
                    type="checkbox"
                    checked={filterSource.caseLaws}
                    onChange={(e) =>
                      setFilterSource({
                        ...filterSource,
                        caseLaws: e.target.checked,
                      })
                    }
                    className="w-4 h-4 accent-[#D4AF37]"
                  />
                  <span>Case Laws</span>
                </label>
              </div>
            )}
          </div>

          {/* Date Range */}
          <div className="mb-4">
            <div
              onClick={() => toggleSection("date")}
              className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm"
            >
              <span>Date Range</span>
              {openSections.date ? (
                <ChevronUp size={16} />
              ) : (
                <ChevronDown size={16} />
              )}
            </div>
            {openSections.date && (
              <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                {[
                  { value: "all", label: "All Time" },
                  { value: "last5", label: "Last 5 Years" },
                  { value: "custom", label: "Custom" },
                ].map((opt) => (
                  <label
                    key={opt.value}
                    className="flex items-center space-x-3 cursor-pointer hover:text-white"
                  >
                    <input
                      type="radio"
                      name="date"
                      checked={filterDate === opt.value}
                      onChange={() => setFilterDate(opt.value)}
                      className="w-4 h-4 accent-[#D4AF37]"
                    />
                    <span>{opt.label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Topic */}
          <div className="mb-4">
            <div
              onClick={() => toggleSection("topic")}
              className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm"
            >
              <span>Topic</span>
              {openSections.topic ? (
                <ChevronUp size={16} />
              ) : (
                <ChevronDown size={16} />
              )}
            </div>
            {openSections.topic && (
              <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                {[
                  "Contract & Commercial",
                  "Property & Land",
                  "Labour & Employment",
                  "Civil Procedure",
                ].map((t) => (
                  <label
                    key={t}
                    className="flex items-center space-x-3 cursor-pointer hover:text-white"
                  >
                    <input
                      type="checkbox"
                      className="w-4 h-4 accent-[#D4AF37]"
                    />
                    <span>{t}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Court Level */}
          {filterSource.caseLaws && (
            <div className="mb-4">
              <div
                onClick={() => toggleSection("court")}
                className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm"
              >
                <span>Court Level</span>
                {openSections.court ? (
                  <ChevronUp size={16} />
                ) : (
                  <ChevronDown size={16} />
                )}
              </div>
              {openSections.court && (
                <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                  {[
                    "Supreme Court (SC)",
                    "Court of Appeal (COA)",
                    "Commercial High Court (CHC)",
                    "District Court (DC)",
                  ].map((c) => (
                    <label
                      key={c}
                      className="flex items-center space-x-3 cursor-pointer hover:text-white"
                    >
                      <input
                        type="checkbox"
                        className="w-4 h-4 accent-[#D4AF37]"
                      />
                      <span>{c}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>

        {/* ──────── CENTER: CHAT AREA ──────── */}
        <main className="flex-1 flex flex-col min-w-0 bg-[#2A3241]">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-6 chat-scroll">
            <div className="max-w-3xl mx-auto space-y-5">
              {/* Welcome state */}
              {messages.length === 0 && !isLoading && (
                <div className="flex flex-col items-center justify-center h-full py-24 text-center">
                  <Scale size={48} className="text-[#D4AF37] mb-4" />
                  <h2 className="text-xl font-serif text-white mb-2">
                    Welcome to LankaLawBot
                  </h2>
                  <p className="text-slate-400 text-sm max-w-md">
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
                      <div className="bg-[#D4AF37] text-[#161B28] px-5 py-3 rounded-2xl rounded-br-md shadow-md">
                        <p className="text-sm font-medium leading-relaxed">
                          {msg.content}
                        </p>
                        {msg.attachedDocuments &&
                          msg.attachedDocuments.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {msg.attachedDocuments.map((doc) => (
                                <div
                                  key={doc.document_id}
                                  className="flex max-w-full items-center gap-1.5 rounded-lg bg-[#161B28]/15 px-2 py-1 text-[11px] font-semibold"
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
                      <p className="text-[10px] text-slate-500 text-right mt-1 mr-1">
                        {msg.timestamp.toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                ) : (
                  /* ── Bot response ── */
                  <div key={msg.id} className="flex justify-start">
                    <div className="max-w-[85%] w-full">
                      <div className="bg-[#161B28] border border-slate-700/50 rounded-2xl rounded-bl-md shadow-lg overflow-hidden">
                        {/* Header */}
                        <div className="flex items-center gap-2 px-5 pt-4 pb-2">
                          <Scale size={16} className="text-[#D4AF37]" />
                          <span className="text-[#D4AF37] font-semibold text-sm">
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
                          {msg.markdownContent ? (
                            <MarkdownRenderer
                              content={msg.markdownContent}
                              sources={msg.sources}
                              onViewInSources={(citationId) =>
                                scrollToSource(msg.id, citationId)
                              }
                            />
                          ) : (
                            <p className="text-slate-200 text-sm leading-relaxed whitespace-pre-wrap">
                              {msg.content}
                            </p>
                          )}
                        </div>

                        {/* Sources section (collapsible) */}
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="border-t border-slate-700/40">
                            <button
                              onClick={() => toggleSources(msg.id)}
                              className="w-full flex items-center justify-between px-5 py-2.5 text-sm text-slate-300 hover:bg-slate-800/40 transition"
                            >
                              <span className="flex items-center gap-2">
                                <Info size={14} className="text-sky-400" />
                                Sources ({msg.sources.length})
                              </span>
                              {expandedSources.has(msg.id) ? (
                                <ChevronUp size={14} />
                              ) : (
                                <ChevronDown size={14} />
                              )}
                            </button>
                            {expandedSources.has(msg.id) && (
                              <div className="px-5 pb-4 space-y-2">
                                {msg.sources.map((src) => (
                                  <div
                                    key={src.citation_id}
                                    id={sourceCardId(msg.id, src.citation_id)}
                                    className="bg-slate-800/30 rounded-lg p-3 flex items-start justify-between gap-3 scroll-mt-4"
                                  >
                                    <div className="min-w-0 flex-1">
                                      <div className="flex items-center gap-2 mb-1">
                                        <span className="text-[10px] font-bold bg-sky-400/20 text-sky-400 px-1.5 py-0.5 rounded shrink-0">
                                          {src.citation_id}
                                        </span>
                                        <span className="text-sm font-medium text-slate-200 truncate">
                                          {src.title}
                                        </span>
                                      </div>
                                      <p className="text-[11px] text-slate-400">
                                        {src.year > 0
                                          ? `Year: ${src.year}`
                                          : ""}
                                        {src.section ? ` · ${src.section}` : ""}
                                      </p>
                                      {src.excerpt && (
                                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                                          {src.excerpt}
                                        </p>
                                      )}
                                    </div>
                                    <button
                                      onClick={() => addMaterial(src)}
                                      className="text-[10px] font-semibold bg-[#D4AF37]/20 text-[#D4AF37] hover:bg-[#D4AF37]/30 px-2 py-1 rounded transition shrink-0"
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
                          <div className="border-t border-slate-700/40 px-5 py-2.5 flex items-start gap-2">
                            <AlertTriangle
                              size={12}
                              className="text-amber-500 mt-0.5 shrink-0"
                            />
                            <p className="text-[11px] text-slate-500 leading-relaxed">
                              {msg.disclaimer}
                            </p>
                          </div>
                        )}
                      </div>
                      <p className="text-[10px] text-slate-500 mt-1 ml-1">
                        {msg.timestamp.toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                    </div>
                  </div>
                ),
              )}

              {/* Typing indicator */}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-[#161B28] border border-slate-700/50 rounded-2xl rounded-bl-md px-5 py-4 shadow-lg">
                    <div className="flex items-center gap-2">
                      <Scale size={14} className="text-[#D4AF37]" />
                      <span className="text-[#D4AF37] text-sm font-semibold">
                        LankaLawBot
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-2">
                      <span className="typing-dot w-2 h-2 rounded-full bg-slate-400" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-slate-400" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-slate-400" />
                      <span className="text-xs text-slate-500 ml-2">
                        Analyzing Sri Lankan law…
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>
          </div>

          {/* ── Input bar (bottom-pinned) ── */}
          <div className="shrink-0 border-t border-slate-700/40 bg-[#1E2636] px-6 py-4">
            <ChatInputBar
              value={inputQuery}
              isLoading={isLoading}
              documents={uploadedDocuments}
              selectedMode={selectedMode}
              onChange={setInputQuery}
              onFileSelected={handleFileSelected}
              onRemoveDocument={handleRemoveDocument}
              onModeChange={setSelectedMode}
              onSubmit={handleSend}
            />
          </div>
        </main>

        {/* ──────── RIGHT SIDEBAR: ADDED MATERIALS ──────── */}
        <aside className="w-[280px] bg-[#161B28] text-white p-5 overflow-y-auto shrink-0 border-l border-slate-700/40 chat-scroll">
          <h2 className="text-base font-semibold mb-4 pb-3 border-b border-slate-700 text-slate-200">
            Added Materials
          </h2>

          <div className="space-y-3">
            {addedMaterials.length === 0 ? (
              <p className="text-slate-500 text-xs italic leading-relaxed">
                No materials added yet. Expand &quot;Sources&quot; in a response
                and click &quot;+ Add&quot; to save references here for
                drafting.
              </p>
            ) : (
              addedMaterials.map((item) => (
                <div
                  key={item.citation_id}
                  className="flex justify-between items-start group bg-slate-800/30 rounded-lg p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="text-[10px] font-bold bg-sky-400/20 text-sky-400 px-1.5 py-0.5 rounded shrink-0">
                        {item.citation_id}
                      </span>
                    </div>
                    <h4 className="text-xs text-slate-200 group-hover:text-white transition leading-snug">
                      {item.title}
                    </h4>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                      {item.year > 0 ? `Year: ${item.year}` : ""}
                      {item.section ? ` · ${item.section}` : ""}
                    </p>
                  </div>
                  <button
                    onClick={() => removeMaterial(item.citation_id)}
                    className="text-slate-500 hover:text-white bg-slate-700/50 hover:bg-slate-600 rounded-full p-1 ml-2 transition shrink-0"
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
