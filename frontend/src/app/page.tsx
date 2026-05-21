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
  LogOut,
} from "lucide-react";
import Link from "next/link";

import { ChatInputBar } from "@/components/ChatInputBar";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";
import { PromptSuggestionPanel } from "@/components/PromptSuggestionPanel";
import {
  deleteDocument,
  getDocumentStatus,
  improvePrompt,
  sendLegalQuery,
  uploadDocument,
  type ImprovePromptResponse,
  type SourceRef,
} from "@/lib/api";
import { logOut } from "@/lib/firebase/auth";
import { sourceCardId } from "@/lib/sources";
import { useAuth } from "@/contexts/AuthProvider";
import type { AttachedDocument, UploadedDocument } from "@/types/documents";
import type { QueryMode } from "@/types/QueryMode";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  markdownContent?: string;
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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [uploadedDocuments, setUploadedDocuments] = useState<UploadedDocument[]>([]);
  const [selectedMode, setSelectedMode] = useState<QueryMode>("quick_qa");
  const [isImproving, setIsImproving] = useState(false);
  const [promptSuggestion, setPromptSuggestion] = useState<ImprovePromptResponse | null>(null);
  const [improveError, setImproveError] = useState<string | null>(null);
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set());

  const [filterSource, setFilterSource] = useState({ acts: true, caseLaws: true });
  const [filterDate, setFilterDate] = useState("all");
  const [openSections, setOpenSections] = useState({
    source: true,
    date: true,
    topic: true,
    court: true,
  });

  const [addedMaterials, setAddedMaterials] = useState<SourceRef[]>([]);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollingTimersRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  const { user, loading: authLoading } = useAuth();

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
  /* Handlers — unchanged logic, only kept for completeness           */
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

  const updateDocument = (key: string, updater: (doc: UploadedDocument) => UploadedDocument) => {
    setUploadedDocuments((prev) =>
      prev.map((doc) => (doc.local_id === key || doc.document_id === key ? updater(doc) : doc)),
    );
  };

  const stopPolling = (documentId: string) => {
    const timer = pollingTimersRef.current.get(documentId);
    if (timer) { clearInterval(timer); pollingTimersRef.current.delete(documentId); }
  };

  const startStatusPolling = (documentId: string) => {
    stopPolling(documentId);
    const poll = async () => {
      try {
        const status = await getDocumentStatus(documentId);
        setUploadedDocuments((prev) =>
          prev.map((doc) =>
            doc.document_id === documentId
              ? { ...doc, job_id: status.job_id ?? doc.job_id, filename: status.filename, status: status.status, chunk_count: status.chunk_count, error: status.error, file: undefined }
              : doc,
          ),
        );
        if (status.status === "completed" || status.status === "failed") stopPolling(documentId);
      } catch (error) {
        setUploadedDocuments((prev) =>
          prev.map((doc) =>
            doc.document_id === documentId
              ? { ...doc, status: "failed", error: error instanceof Error ? error.message : "Unable to check document status." }
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
    try { validateFile(file); } catch (error) {
      setUploadedDocuments((prev) => [...prev, { local_id: localId, document_id: localId, job_id: "", filename: file.name, status: "failed", error: error instanceof Error ? error.message : "Invalid file.", file, uploaded_at: new Date().toISOString() }]);
      return;
    }
    setUploadedDocuments((prev) => [...prev, { local_id: localId, document_id: localId, job_id: "", filename: file.name, status: "queued", file, uploaded_at: new Date().toISOString() }]);
    try {
      const uploaded = await uploadDocument(file);
      updateDocument(localId, (doc) => ({ ...doc, document_id: uploaded.document_id, job_id: uploaded.job_id, filename: uploaded.filename, status: uploaded.status, file: undefined }));
      startStatusPolling(uploaded.document_id);
    } catch (error) {
      updateDocument(localId, (doc) => ({ ...doc, status: "failed", error: error instanceof Error ? error.message : "Document upload failed." }));
    }
  };

  const handleRemoveDocument = async (documentId: string) => {
    stopPolling(documentId);
    const doc = uploadedDocuments.find((item) => item.document_id === documentId || item.local_id === documentId);
    setUploadedDocuments((prev) => prev.filter((item) => item.document_id !== documentId && item.local_id !== documentId));
    if (doc?.job_id && doc.document_id !== doc.local_id) {
      try { await deleteDocument(doc.document_id); } catch {
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", content: `The document was removed from this chat, but the backend could not delete "${doc.filename}".`, timestamp: new Date() }]);
      }
    }
  };

  const handleSend = async () => {
    if (!inputQuery.trim() || isLoading) return;
    if (uploadedDocuments.some((doc) => doc.status !== "completed")) return;
    const attachedDocuments = uploadedDocuments.filter((doc) => doc.status === "completed").map((doc) => ({ document_id: doc.document_id, filename: doc.filename, status: doc.status }));
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: inputQuery.trim(), attachedDocuments, timestamp: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    const query = inputQuery.trim();
    setInputQuery("");
    setPromptSuggestion(null);
    setImproveError(null);
    setIsLoading(true);
    try {
      const data = await sendLegalQuery({ question: query, mode: selectedMode, matter_id: null, document_ids: attachedDocuments.map((doc) => doc.document_id) });
      const botMsg: ChatMessage = { id: crypto.randomUUID(), role: "assistant", content: data.answer || "No response generated.", markdownContent: data.markdown_content, sources: data.sources || [], confidence: data.confidence, disclaimer: data.disclaimer, timestamp: new Date() };
      setMessages((prev) => [...prev, botMsg]);
    } catch {
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", content: "Unable to reach the legal research backend. Please ensure the server is running and try again.", timestamp: new Date() }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleImprove = async () => {
    const draft = inputQuery.trim();
    if (!draft || isLoading || isImproving) return;
    if (uploadedDocuments.some((doc) => doc.status !== "completed")) return;
    setIsImproving(true);
    setImproveError(null);
    try {
      const result = await improvePrompt({ draft, mode: selectedMode, has_documents: uploadedDocuments.some((doc) => doc.status === "completed") });
      setPromptSuggestion(result);
    } catch (error) {
      setPromptSuggestion(null);
      setImproveError(error instanceof Error ? error.message : "Unable to improve the prompt right now.");
    } finally {
      setIsImproving(false);
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
      document.getElementById(sourceCardId(messageId, citationId))?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  };

  const addMaterial = (src: SourceRef) => {
    if (!addedMaterials.find((m) => m.citation_id === src.citation_id)) {
      setAddedMaterials((prev) => [...prev, src]);
    }
  };

  const removeMaterial = (citationId: string) => {
    setAddedMaterials((prev) => prev.filter((m) => m.citation_id !== citationId));
  };

  const confidenceColor = (c?: string) => {
    if (c === "high") return "text-emerald-400 bg-emerald-400/10 border-emerald-400/30";
    if (c === "medium") return "text-amber-400 bg-amber-400/10 border-amber-400/30";
    return "text-red-400 bg-red-400/10 border-red-400/30";
  };

  const confidenceDots = (c?: string) => {
    const filled = c === "high" ? 3 : c === "medium" ? 2 : 1;
    return Array.from({ length: 3 }, (_, i) => (
      <span key={i} className={`inline-block w-2 h-2 rounded-full mr-0.5 ${i < filled ? "bg-current" : "bg-light-blue/40"}`} />
    ));
  };

  /* ---------------------------------------------------------------- */
  /* Render                                                            */
  /* ---------------------------------------------------------------- */

  return (
    <div className="h-screen flex flex-col bg-background font-sans overflow-hidden">

      {/* ══════════════════════════════════════════════════════════════
          NAVBAR
          - bg-dark-blue for surface consistency with cards
          - yellow accent on active nav item with bottom border
          - Playfair Display (font-serif) for brand name per design system
          - 26px icon for brand logo (mid-size from icon scale)
          - User info section uses design system spacing
      ══════════════════════════════════════════════════════════════ */}
      <header className="bg-dark-blue text-slate-100 flex items-center justify-between px-8 py-0 z-10 border-b border-light-blue/20 shrink-0 h-16">

        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <Scale size={26} className="text-yellow shrink-0" aria-hidden="true" />
          <span className="text-2xl font-serif tracking-wide text-slate-100">
            LankaLawBot
          </span>
        </div>

        {/* Primary navigation
            UX principle: Recognition over recall — visible labels + icons.
            Active state: yellow text + yellow bottom border (2px).
            Inactive state: muted slate-400, hover lifts to slate-200.
            Touch targets: h-16 full height clickable area via flex+self-stretch. */}
        <nav className="flex h-full" aria-label="Main navigation">
          {[
            { label: "Research", icon: Search, active: true },
            { label: "Draft", icon: PenTool, active: false },
            { label: "Verify", icon: CheckSquare, active: false },
            { label: "Analyze", icon: BarChart2, active: false },
          ].map(({ label, icon: Icon, active }) => (
            <button
              key={label}
              className={`
                flex items-center gap-2 px-5 text-sm font-medium border-b-2 transition-colors duration-150
                ${active
                  ? "text-yellow border-yellow"
                  : "text-slate-400 border-transparent hover:text-slate-200 hover:border-light-blue/40"
                }
              `}
            >
              <Icon size={16} aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>

        {/* User section */}
        {authLoading ? (
          <div className="h-9 w-32 rounded-lg bg-background/50 animate-pulse" />
        ) : user ? (
          <div className="flex items-center gap-3">
            {user.photoURL ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.photoURL}
                alt={user.displayName ?? "User avatar"}
                className="h-9 w-9 rounded-full object-cover ring-2 ring-light-blue/30"
              />
            ) : (
              <div className="h-9 w-9 rounded-full bg-light-blue/20 border border-light-blue/30 flex items-center justify-center">
                <User size={16} className="text-slate-300" aria-hidden="true" />
              </div>
            )}
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-slate-200 truncate max-w-[160px] leading-tight">
                {user.displayName || user.email}
              </p>
              {user.displayName && user.email && (
                <p className="text-xs text-slate-500 truncate max-w-[160px] leading-tight">
                  {user.email}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void logOut()}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 hover:bg-light-blue/10 transition-colors px-3 py-2 rounded-lg border border-light-blue/20"
            >
              <LogOut size={14} aria-hidden="true" />
              <span className="hidden sm:inline">Log out</span>
            </button>
          </div>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-2 text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-light-blue/10 transition-colors px-3 py-2 rounded-lg border border-light-blue/20"
          >
            <User size={16} aria-hidden="true" />
            Sign in
          </Link>
        )}
      </header>

      {/* ══════════════════════════════════════════════════════════════
          BODY — 3-column layout
      ══════════════════════════════════════════════════════════════ */}
      <div className="flex flex-1 overflow-hidden">

        {/* ────────────────────────────────────────────────────────────
            LEFT SIDEBAR — FILTERS
            - bg-dark-blue: card surface token
            - Filter section headers: use light-blue/20 bg instead of
              the old #C5D0E6 which clashed badly with the dark theme
            - Consistent border: border-light-blue/20
            - 8pt spacing rhythm throughout (p-2, p-4, gap-2, space-y-2)
        ──────────────────────────────────────────────────────────── */}
        <aside
          className="w-64 bg-dark-blue text-slate-300 flex flex-col shrink-0 border-r border-light-blue/20 overflow-hidden"
          aria-label="Search filters"
        >
          {/* Sidebar header */}
          <div className="px-5 py-4 border-b border-light-blue/20 shrink-0">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-light-blue">
              Filters
            </h2>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 chat-scroll">

            {/* Reusable filter section — Source Type */}
            <FilterSection
              label="Source Type"
              open={openSections.source}
              onToggle={() => toggleSection("source")}
            >
              <label className="flex items-center gap-3 cursor-pointer text-sm hover:text-slate-100 transition-colors py-1">
                <input
                  type="checkbox"
                  checked={filterSource.acts}
                  onChange={(e) => setFilterSource({ ...filterSource, acts: e.target.checked })}
                  className="w-4 h-4 accent-yellow rounded"
                />
                Acts
              </label>
              <label className="flex items-center gap-3 cursor-pointer text-sm hover:text-slate-100 transition-colors py-1">
                <input
                  type="checkbox"
                  checked={filterSource.caseLaws}
                  onChange={(e) => setFilterSource({ ...filterSource, caseLaws: e.target.checked })}
                  className="w-4 h-4 accent-yellow rounded"
                />
                Case Laws
              </label>
            </FilterSection>

            {/* Date Range */}
            <FilterSection
              label="Date Range"
              open={openSections.date}
              onToggle={() => toggleSection("date")}
            >
              {[
                { value: "all", label: "All Time" },
                { value: "last5", label: "Last 5 Years" },
                { value: "custom", label: "Custom Range" },
              ].map((opt) => (
                <label key={opt.value} className="flex items-center gap-3 cursor-pointer text-sm hover:text-slate-100 transition-colors py-1">
                  <input
                    type="radio"
                    name="date"
                    checked={filterDate === opt.value}
                    onChange={() => setFilterDate(opt.value)}
                    className="w-4 h-4 accent-yellow"
                  />
                  {opt.label}
                </label>
              ))}
            </FilterSection>

            {/* Topic */}
            <FilterSection
              label="Topic"
              open={openSections.topic}
              onToggle={() => toggleSection("topic")}
            >
              {["Contract & Commercial", "Property & Land", "Labour & Employment", "Civil Procedure"].map((t) => (
                <label key={t} className="flex items-center gap-3 cursor-pointer text-sm hover:text-slate-100 transition-colors py-1">
                  <input type="checkbox" className="w-4 h-4 accent-yellow rounded" />
                  {t}
                </label>
              ))}
            </FilterSection>

            {/* Court Level — only shown when case laws filter is active */}
            {filterSource.caseLaws && (
              <FilterSection
                label="Court Level"
                open={openSections.court}
                onToggle={() => toggleSection("court")}
              >
                {["Supreme Court (SC)", "Court of Appeal (COA)", "Commercial High Court (CHC)", "District Court (DC)"].map((c) => (
                  <label key={c} className="flex items-center gap-3 cursor-pointer text-sm hover:text-slate-100 transition-colors py-1">
                    <input type="checkbox" className="w-4 h-4 accent-yellow rounded" />
                    {c}
                  </label>
                ))}
              </FilterSection>
            )}
          </div>
        </aside>

        {/* ────────────────────────────────────────────────────────────
            CENTER — CHAT AREA
            - bg-background: global app background token
            - Welcome state uses font-serif (Playfair Display) for the
              heading, consistent with login/signup pages
            - User bubbles: bg-yellow text-dark-blue (CTA color as bubble)
            - Bot cards: bg-dark-blue, border border-light-blue/20
            - Confidence dots use light-blue/40 for unfilled state
            - Typing dots use the yellow accent
        ──────────────────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col min-w-0 bg-background">

          {/* Messages scrollable area */}
          <div className="flex-1 overflow-y-auto px-6 py-6 chat-scroll">
            <div className="max-w-3xl mx-auto space-y-6">

              {/* ── Welcome state ── */}
              {messages.length === 0 && !isLoading && (
                <div className="flex flex-col items-center justify-center py-24 text-center select-none">
                  {/* Decorative ring around icon */}
                  <div className="w-20 h-20 rounded-full border-2 border-yellow/30 bg-dark-blue flex items-center justify-center mb-6 shadow-lg">
                    <Scale size={32} className="text-yellow" aria-hidden="true" />
                  </div>
                  <h2 className="text-3xl font-serif text-slate-100 mb-3 tracking-tight">
                    Welcome to LankaLawBot
                  </h2>
                  <p className="text-slate-400 text-base max-w-md leading-relaxed">
                    Ask any question about Sri Lankan law. The AI searches
                    through acts and case laws, then provides a cited,
                    structured answer.
                  </p>
                  {/* Quick-start suggestion pills */}
                  <div className="mt-8 flex flex-wrap gap-2 justify-center max-w-lg">
                    {[
                      "What are the grounds for termination under Sri Lankan labour law?",
                      "Explain the procedure for filing a civil suit",
                      "What does the Land Acquisition Act say about compensation?",
                    ].map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setInputQuery(suggestion)}
                        className="text-xs text-slate-300 bg-dark-blue border border-light-blue/30 hover:border-yellow/50 hover:text-yellow transition-colors px-3 py-2 rounded-lg text-left"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Chat messages ── */}
              {messages.map((msg) =>
                msg.role === "user" ? (

                  /* ── USER BUBBLE ──
                     bg-yellow text-dark-blue: primary CTA color used for
                     user messages — high contrast, matches design system.
                     Rounded corners: 2xl with br-sm for chat tail shape. */
                  <div key={msg.id} className="flex justify-end">
                    <div className="max-w-[75%]">
                      <div className="bg-yellow text-dark-blue px-5 py-3.5 rounded-2xl rounded-br-sm shadow-md">
                        <p className="text-sm font-medium leading-relaxed">
                          {msg.content}
                        </p>
                        {msg.attachedDocuments && msg.attachedDocuments.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {msg.attachedDocuments.map((doc) => (
                              <div
                                key={doc.document_id}
                                className="flex items-center gap-1.5 rounded-lg bg-dark-blue/20 px-2 py-1 text-[11px] font-semibold"
                                title={doc.filename}
                              >
                                <FileText size={12} aria-hidden="true" />
                                <span className="max-w-[220px] truncate">{doc.filename}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <p className="text-[10px] text-light-blue/60 text-right mt-1 mr-1">
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>

                ) : (

                  /* ── BOT RESPONSE CARD ──
                     bg-dark-blue: surface card token
                     border-light-blue/20: subtle system border
                     Yellow accent for brand identity in header
                     Rounded corners match login/signup cards (rounded-2xl) */
                  <div key={msg.id} className="flex justify-start">
                    <div className="max-w-[85%] w-full">
                      <div className="bg-dark-blue border border-light-blue/20 rounded-2xl rounded-bl-sm shadow-lg overflow-hidden">

                        {/* Card header */}
                        <div className="flex items-center gap-2.5 px-5 pt-4 pb-2 border-b border-light-blue/10">
                          <Scale size={16} className="text-yellow shrink-0" aria-hidden="true" />
                          <span className="text-yellow font-semibold text-sm font-serif">LankaLawBot</span>
                          {msg.confidence && (
                            <span className={`ml-auto text-[11px] px-2.5 py-0.5 rounded-full border flex items-center gap-1 ${confidenceColor(msg.confidence)}`}>
                              {confidenceDots(msg.confidence)}
                              <span className="ml-1 capitalize">{msg.confidence}</span>
                            </span>
                          )}
                        </div>

                        {/* Content */}
                        <div className="px-5 py-4">
                          {msg.markdownContent ? (
                            <MarkdownRenderer
                              content={msg.markdownContent}
                              sources={msg.sources}
                              onViewInSources={(citationId) => scrollToSource(msg.id, citationId)}
                            />
                          ) : (
                            <p className="text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">
                              {msg.content}
                            </p>
                          )}
                        </div>

                        {/* Sources (collapsible) */}
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="border-t border-light-blue/10">
                            <button
                              onClick={() => toggleSources(msg.id)}
                              className="w-full flex items-center justify-between px-5 py-3 text-sm text-slate-400 hover:text-slate-200 hover:bg-light-blue/5 transition-colors"
                              aria-expanded={expandedSources.has(msg.id)}
                            >
                              <span className="flex items-center gap-2">
                                <Info size={14} className="text-sky-400" aria-hidden="true" />
                                {msg.sources.length} {msg.sources.length === 1 ? "Source" : "Sources"}
                              </span>
                              {expandedSources.has(msg.id)
                                ? <ChevronUp size={14} aria-hidden="true" />
                                : <ChevronDown size={14} aria-hidden="true" />
                              }
                            </button>

                            {expandedSources.has(msg.id) && (
                              <div className="px-5 pb-4 space-y-2">
                                {msg.sources.map((src) => (
                                  <div
                                    key={src.citation_id}
                                    id={sourceCardId(msg.id, src.citation_id)}
                                    className="bg-background/60 border border-light-blue/15 rounded-xl p-3 flex items-start justify-between gap-3 scroll-mt-4 hover:border-light-blue/30 transition-colors"
                                  >
                                    <div className="min-w-0 flex-1">
                                      <div className="flex items-center gap-2 mb-1">
                                        <span className="text-[10px] font-bold bg-sky-400/15 text-sky-400 px-1.5 py-0.5 rounded shrink-0">
                                          {src.citation_id}
                                        </span>
                                        <span className="text-sm font-medium text-slate-200 truncate">
                                          {src.title}
                                        </span>
                                      </div>
                                      <p className="text-[11px] text-light-blue">
                                        {src.year > 0 ? `Year: ${src.year}` : ""}
                                        {src.section ? ` · ${src.section}` : ""}
                                      </p>
                                      {src.excerpt && (
                                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">{src.excerpt}</p>
                                      )}
                                    </div>
                                    <button
                                      onClick={() => addMaterial(src)}
                                      className="text-[10px] font-semibold bg-yellow/15 text-yellow hover:bg-yellow/25 px-2.5 py-1 rounded-lg transition-colors shrink-0 border border-yellow/20"
                                      title="Save to materials"
                                    >
                                      + Save
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Disclaimer */}
                        {msg.disclaimer && (
                          <div className="border-t border-light-blue/10 px-5 py-3 flex items-start gap-2">
                            <AlertTriangle size={12} className="text-amber-500 mt-0.5 shrink-0" aria-hidden="true" />
                            <p className="text-[11px] text-slate-500 leading-relaxed">{msg.disclaimer}</p>
                          </div>
                        )}
                      </div>

                      <p className="text-[10px] text-light-blue/60 mt-1 ml-1">
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ),
              )}

              {/* Typing indicator */}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-dark-blue border border-light-blue/20 rounded-2xl rounded-bl-sm px-5 py-4 shadow-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <Scale size={14} className="text-yellow" aria-hidden="true" />
                      <span className="text-yellow text-sm font-semibold font-serif">LankaLawBot</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="typing-dot w-2 h-2 rounded-full bg-light-blue" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-light-blue" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-light-blue" />
                      <span className="text-xs text-slate-500 ml-1">Analysing Sri Lankan law…</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>
          </div>

          {/* ── Input bar (bottom-pinned) ── */}
          <div className="shrink-0 border-t border-light-blue/20 bg-dark-blue px-6 py-4">
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
              onDismiss={() => { setPromptSuggestion(null); setImproveError(null); }}
            />
            <ChatInputBar
              value={inputQuery}
              isLoading={isLoading}
              isImproving={isImproving}
              documents={uploadedDocuments}
              selectedMode={selectedMode}
              onChange={setInputQuery}
              onFileSelected={handleFileSelected}
              onRemoveDocument={handleRemoveDocument}
              onModeChange={setSelectedMode}
              onSubmit={handleSend}
              onImprove={handleImprove}
            />
          </div>
        </main>

        {/* ────────────────────────────────────────────────────────────
            RIGHT SIDEBAR — ADDED MATERIALS
            - bg-dark-blue: card surface token
            - border-light-blue/20: system border
            - Citation tags: sky-400 (consistent with sources section)
            - Empty state: italic muted text with good line-height
        ──────────────────────────────────────────────────────────── */}
        <aside
          className="w-72 bg-dark-blue text-slate-300 flex flex-col shrink-0 border-l border-light-blue/20 overflow-hidden"
          aria-label="Saved materials"
        >
          {/* Header */}
          <div className="px-5 py-4 border-b border-light-blue/20 shrink-0 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-light-blue">
              Saved Materials
            </h2>
            {addedMaterials.length > 0 && (
              <span className="text-[11px] font-medium bg-yellow/15 text-yellow px-2 py-0.5 rounded-full border border-yellow/20">
                {addedMaterials.length}
              </span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2.5 chat-scroll">
            {addedMaterials.length === 0 ? (
              <div className="flex flex-col items-center text-center py-10 px-2">
                <div className="w-12 h-12 rounded-full border border-light-blue/20 bg-background/50 flex items-center justify-center mb-3">
                  <FileText size={20} className="text-light-blue/50" aria-hidden="true" />
                </div>
                <p className="text-slate-500 text-xs leading-relaxed">
                  No materials saved yet. Expand &ldquo;Sources&rdquo; in any
                  response and click&nbsp;<span className="text-yellow">+ Save</span>&nbsp;to
                  collect references for drafting.
                </p>
              </div>
            ) : (
              addedMaterials.map((item) => (
                <div
                  key={item.citation_id}
                  className="group bg-background/50 border border-light-blue/15 rounded-xl p-3 hover:border-light-blue/30 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 mb-1">
                        <span className="text-[10px] font-bold bg-sky-400/15 text-sky-400 px-1.5 py-0.5 rounded shrink-0">
                          {item.citation_id}
                        </span>
                      </div>
                      <h4 className="text-xs text-slate-300 group-hover:text-slate-100 transition-colors leading-snug">
                        {item.title}
                      </h4>
                      <p className="text-[10px] text-light-blue/70 mt-1">
                        {item.year > 0 ? `Year: ${item.year}` : ""}
                        {item.section ? ` · ${item.section}` : ""}
                      </p>
                    </div>
                    <button
                      onClick={() => removeMaterial(item.citation_id)}
                      className="text-slate-600 hover:text-slate-300 bg-light-blue/10 hover:bg-light-blue/20 rounded-lg p-1.5 transition-colors shrink-0"
                      aria-label={`Remove ${item.title}`}
                    >
                      <X size={12} aria-hidden="true" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* FilterSection — reusable collapsible sidebar section               */
/* Uses design system tokens consistently instead of hardcoded colors  */
/* ------------------------------------------------------------------ */

interface FilterSectionProps {
  label: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function FilterSection({ label, open, onToggle, children }: FilterSectionProps) {
  return (
    <div className="rounded-xl overflow-hidden border border-light-blue/15">
      {/* Section header — uses background token, yellow accent on hover */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-background/40 hover:bg-light-blue/10 transition-colors text-left"
        aria-expanded={open}
      >
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wide">
          {label}
        </span>
        {open
          ? <ChevronUp size={14} className="text-light-blue shrink-0" aria-hidden="true" />
          : <ChevronDown size={14} className="text-light-blue shrink-0" aria-hidden="true" />
        }
      </button>

      {/* Section body */}
      {open && (
        <div className="px-4 py-3 space-y-0.5 bg-dark-blue/40">
          {children}
        </div>
      )}
    </div>
  );
}