"use client";

import { useState, useRef, useEffect } from "react";
import {
  Search,
  Send,
  ChevronDown,
  ChevronUp,
  X,
  PenTool,
  CheckSquare,
  BarChart2,
  User,
  Scale,
  BookOpen,
  AlertTriangle,
  Info,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface SourceRef {
  citation_id: string;
  title: string;
  section: string | null;
  year: number;
  breadcrumb: string | null;
  excerpt: string;
}

interface AnalysisClaim {
  statement: string;
  citations: string[];
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  analysis?: AnalysisClaim[];
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

  // Collapsible state for bot responses (keyed by message id)
  const [expandedAnalysis, setExpandedAnalysis] = useState<Set<string>>(new Set());
  const [expandedSources, setExpandedSources] = useState<Set<string>>(new Set());

  // Sidebar – Filters
  const [filterSource, setFilterSource] = useState({ acts: true, caseLaws: true });
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

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  /* ---------------------------------------------------------------- */
  /* Handlers                                                          */
  /* ---------------------------------------------------------------- */

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: inputQuery.trim(),
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    const query = inputQuery.trim();
    setInputQuery("");
    setIsLoading(true);

    // Build optional filters
    let doc_type: string | null = null;
    if (filterSource.acts && !filterSource.caseLaws) doc_type = "Act";
    if (!filterSource.acts && filterSource.caseLaws) doc_type = "Case Law";
    let start_year: number | null = null;
    if (filterDate === "last5") start_year = new Date().getFullYear() - 5;

    try {
      const res = await fetch("http://127.0.0.1:8000/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: query, doc_type, start_year }),
      });
      const data = await res.json();

      const botMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.answer || "No response generated.",
        analysis: data.analysis || [],
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
          content: "Unable to reach the legal research backend. Please ensure the server is running and try again.",
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

  const toggleAnalysis = (id: string) => {
    setExpandedAnalysis((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSources = (id: string) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
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
          <h2 className="text-base font-semibold mb-4 text-slate-200">Filters</h2>

          {/* Source Type */}
          <div className="mb-4">
            <div
              onClick={() => toggleSection("source")}
              className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm"
            >
              <span>Source Type</span>
              {openSections.source ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
            {openSections.source && (
              <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input
                    type="checkbox"
                    checked={filterSource.acts}
                    onChange={(e) => setFilterSource({ ...filterSource, acts: e.target.checked })}
                    className="w-4 h-4 accent-[#D4AF37]"
                  />
                  <span>Acts</span>
                </label>
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input
                    type="checkbox"
                    checked={filterSource.caseLaws}
                    onChange={(e) => setFilterSource({ ...filterSource, caseLaws: e.target.checked })}
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
              {openSections.date ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
            {openSections.date && (
              <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                {[
                  { value: "all", label: "All Time" },
                  { value: "last5", label: "Last 5 Years" },
                  { value: "custom", label: "Custom" },
                ].map((opt) => (
                  <label key={opt.value} className="flex items-center space-x-3 cursor-pointer hover:text-white">
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
              {openSections.topic ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
            {openSections.topic && (
              <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                {["Contract & Commercial", "Property & Land", "Labour & Employment", "Civil Procedure"].map((t) => (
                  <label key={t} className="flex items-center space-x-3 cursor-pointer hover:text-white">
                    <input type="checkbox" className="w-4 h-4 accent-[#D4AF37]" />
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
                {openSections.court ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
              {openSections.court && (
                <div className="space-y-2 pt-2 px-2 text-sm text-slate-300">
                  {["Supreme Court (SC)", "Court of Appeal (COA)", "Commercial High Court (CHC)", "District Court (DC)"].map((c) => (
                    <label key={c} className="flex items-center space-x-3 cursor-pointer hover:text-white">
                      <input type="checkbox" className="w-4 h-4 accent-[#D4AF37]" />
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
                  <h2 className="text-xl font-serif text-white mb-2">Welcome to LankaLawBot</h2>
                  <p className="text-slate-400 text-sm max-w-md">
                    Ask any question about Sri Lankan law. The AI will search through acts
                    and case laws, then provide a cited, structured answer.
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
                        <p className="text-sm font-medium leading-relaxed">{msg.content}</p>
                      </div>
                      <p className="text-[10px] text-slate-500 text-right mt-1 mr-1">
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
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
                          <span className="text-[#D4AF37] font-semibold text-sm">LankaLawBot</span>
                          {msg.confidence && (
                            <span className={`ml-auto text-[11px] px-2 py-0.5 rounded-full border flex items-center gap-1 ${confidenceColor(msg.confidence)}`}>
                              {confidenceDots(msg.confidence)}
                              <span className="ml-1 capitalize">{msg.confidence}</span>
                            </span>
                          )}
                        </div>

                        {/* Summary / Main answer */}
                        <div className="px-5 pb-3">
                          <p className="text-slate-200 text-sm leading-relaxed whitespace-pre-wrap">
                            {msg.content}
                          </p>
                        </div>

                        {/* Analysis section (collapsible) */}
                        {msg.analysis && msg.analysis.length > 0 && (
                          <div className="border-t border-slate-700/40">
                            <button
                              onClick={() => toggleAnalysis(msg.id)}
                              className="w-full flex items-center justify-between px-5 py-2.5 text-sm text-slate-300 hover:bg-slate-800/40 transition"
                            >
                              <span className="flex items-center gap-2">
                                <BookOpen size={14} className="text-[#D4AF37]" />
                                Legal Analysis ({msg.analysis.length} points)
                              </span>
                              {expandedAnalysis.has(msg.id) ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            </button>
                            {expandedAnalysis.has(msg.id) && (
                              <div className="px-5 pb-4 space-y-3">
                                {msg.analysis.map((claim, idx) => (
                                  <div key={idx} className="bg-slate-800/40 rounded-lg p-3">
                                    <p className="text-slate-300 text-sm leading-relaxed">{claim.statement}</p>
                                    {claim.citations.length > 0 && (
                                      <div className="flex gap-1.5 mt-2">
                                        {claim.citations.map((cid) => (
                                          <span key={cid} className="text-[10px] font-bold bg-[#D4AF37]/20 text-[#D4AF37] px-1.5 py-0.5 rounded">
                                            {cid}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

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
                              {expandedSources.has(msg.id) ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            </button>
                            {expandedSources.has(msg.id) && (
                              <div className="px-5 pb-4 space-y-2">
                                {msg.sources.map((src) => (
                                  <div key={src.citation_id} className="bg-slate-800/30 rounded-lg p-3 flex items-start justify-between gap-3">
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
                                        {src.year > 0 ? `Year: ${src.year}` : ""}{src.section ? ` · ${src.section}` : ""}
                                      </p>
                                      {src.excerpt && (
                                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">{src.excerpt}</p>
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
                            <AlertTriangle size={12} className="text-amber-500 mt-0.5 shrink-0" />
                            <p className="text-[11px] text-slate-500 leading-relaxed">{msg.disclaimer}</p>
                          </div>
                        )}
                      </div>
                      <p className="text-[10px] text-slate-500 mt-1 ml-1">
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
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
                      <span className="text-[#D4AF37] text-sm font-semibold">LankaLawBot</span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-2">
                      <span className="typing-dot w-2 h-2 rounded-full bg-slate-400" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-slate-400" />
                      <span className="typing-dot w-2 h-2 rounded-full bg-slate-400" />
                      <span className="text-xs text-slate-500 ml-2">Analyzing Sri Lankan law…</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={chatEndRef} />
            </div>
          </div>

          {/* ── Input bar (bottom-pinned) ── */}
          <div className="shrink-0 border-t border-slate-700/40 bg-[#1E2636] px-6 py-4">
            <form onSubmit={handleSend} className="max-w-3xl mx-auto flex gap-3">
              <input
                type="text"
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                placeholder="Ask a legal question…"
                disabled={isLoading}
                className="flex-1 bg-[#161B28] border border-slate-600/50 text-white placeholder:text-slate-500 px-5 py-3 rounded-xl text-sm focus:outline-none focus:border-[#D4AF37]/60 focus:ring-1 focus:ring-[#D4AF37]/30 transition disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isLoading || !inputQuery.trim()}
                className="bg-[#D4AF37] hover:bg-[#C5A030] disabled:bg-slate-600 disabled:cursor-not-allowed text-[#161B28] font-bold px-5 py-3 rounded-xl flex items-center gap-2 transition text-sm"
              >
                <Send size={16} />
                <span className="hidden sm:inline">Send</span>
              </button>
            </form>
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
                No materials added yet. Expand &quot;Sources&quot; in a response and click
                &quot;+ Add&quot; to save references here for drafting.
              </p>
            ) : (
              addedMaterials.map((item) => (
                <div key={item.citation_id} className="flex justify-between items-start group bg-slate-800/30 rounded-lg p-3">
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
                      {item.year > 0 ? `Year: ${item.year}` : ""}{item.section ? ` · ${item.section}` : ""}
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
