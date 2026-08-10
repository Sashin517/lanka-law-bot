"use client";

/**
 * DraftPage — Three-panel layout for legal document drafting.
 *
 * Layout (matching UI mockup):
 *   ┌─────────────────────────────────────────────────────────┐
 *   │ NavBar (shared with main page)                          │
 *   ├─────────────────────────────────────────────────────────┤
 *   │ DraftToolbar (sub-header)                               │
 *   ├──────────┬──────────────────────────┬───────────────────┤
 *   │ Version  │ Editor (center)          │ Chat Panel (right)│
 *   │ History  │                          │                   │
 *   │ (left)   │                          │                   │
 *   └──────────┴──────────────────────────┴───────────────────┘
 *
 * Phase 2 delivers interactive citations and source verification.
 * Version History and Chat Panel are placeholder stubs for Phase 3/4.
 *
 * @module app/draft/page
 */

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Scale,
  Search,
  PenTool,
  CheckSquare,
  BarChart2,
  User,
  LogOut,
} from "lucide-react";
import Link from "next/link";

import { DraftToolbar } from "@/components/drafting/DraftToolbar";
import { EditorToolbar } from "@/components/drafting/EditorToolbar";
import { TiptapEditor } from "@/components/drafting/TiptapEditor";
import { SourceVerificationPanel } from "@/components/drafting/SourceVerificationPanel";
import { documentBuilder } from "@/lib/drafting/documentBuilder";
import { useDraftDocumentStore } from "@/store/draftDocumentStore";
import { useVersionStore } from "@/store/versionStore";
import { useChatEditStore } from "@/store/chatEditStore";
import { useAuth } from "@/contexts/AuthProvider";
import { logOut } from "@/lib/firebase/auth";
import type { TiptapDocument, EditorSelection } from "@/types/drafting";

// ─── Component ──────────────────────────────────────────────────

export default function DraftPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  // ── Stores ──
  const {
    title,
    originalPrompt,
    documentJson,
    markdownContent,
    sources,
    isLoading,
    error,
    updateContent,
  } = useDraftDocumentStore();

  const {
    showEditsMode,
    toggleShowEdits,
    getVersionCount,
  } = useVersionStore();

  const { setSelection } = useChatEditStore();

  // ── Local UI state ──
  const [chatPanelOpen, setChatPanelOpen] = useState(true);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [sourcePanelOpen, setSourcePanelOpen] = useState(false);
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);
  // ── Editor callbacks ──
  const handleEditorUpdate = useCallback(
    (json: TiptapDocument) => {
      // Sync to Zustand store (Phase 4 will also trigger version snapshot)
      updateContent(json, documentBuilder.toMarkdown(json));
    },
    [updateContent],
  );

  const handleSelectionUpdate = useCallback(
    (selection: EditorSelection | null) => {
      setSelection(selection);
    },
    [setSelection],
  );

  // ── Toolbar callbacks ──
  const handleClose = useCallback(() => {
    router.push("/");
  }, [router]);

  const handleZoomIn = useCallback(() => {
    setZoomLevel((prev) => Math.min(prev + 10, 200));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoomLevel((prev) => Math.max(prev - 10, 50));
  }, []);

  const handleToggleFullWidth = useCallback(() => {
    setZoomLevel(100);
  }, []);

  const handleVerifySources = useCallback(() => {
    setActiveCitationId(null);
    setSourcePanelOpen(true);
  }, []);

  const handleViewCitationSource = useCallback((citationId: string) => {
    setActiveCitationId(citationId);
    setSourcePanelOpen(true);
  }, []);

  const handleCloseSourcePanel = useCallback(() => {
    setSourcePanelOpen(false);
    setActiveCitationId(null);
  }, []);

  // Placeholder callbacks for future phases
  const handleExport = useCallback(() => {
    // Phase 6: Open export modal
  }, []);

  const handleSave = useCallback(() => {
    // Phase 4: Trigger manual version snapshot
  }, []);

  const handleDownload = useCallback(() => {
    // Phase 6: Direct download
  }, []);

  // ── Render ──
  return (
    <div className="h-screen flex flex-col bg-[#2A3241] font-sans overflow-hidden">
      {/* ── NAVBAR ── */}
      <header
        className="bg-[#161B28] text-white flex items-center justify-between px-8 py-4 z-10 border-b border-slate-700/50 shrink-0"
        id="draft-navbar"
      >
        <Link
          href="/"
          className="text-2xl font-serif tracking-wide text-white flex items-center gap-2 hover:opacity-90 transition"
        >
          <Scale size={24} className="text-[#D4AF37]" />
          LankaLawBot
        </Link>

        <nav className="flex space-x-12">
          <Link
            href="/"
            className="flex items-center space-x-2 text-slate-400 hover:text-white transition"
          >
            <Search size={18} />
            <span>Research</span>
          </Link>
          <button className="flex items-center space-x-2 text-[#D4AF37] border-b-2 border-[#D4AF37] pb-1">
            <PenTool size={18} />
            <span>Draft</span>
          </button>
          <Link
            href="/"
            className="flex items-center space-x-2 text-slate-400 hover:text-white transition"
          >
            <CheckSquare size={18} />
            <span>Verify</span>
          </Link>
          <Link
            href="/"
            className="flex items-center space-x-2 text-slate-400 hover:text-white transition"
          >
            <BarChart2 size={18} />
            <span>Analyze</span>
          </Link>
        </nav>

        {/* User avatar */}
        {authLoading ? (
          <div className="h-10 w-10 rounded-full bg-[#2A3241] animate-pulse" />
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
              <div className="bg-[#2A3241] p-2 rounded-full">
                <User size={20} className="text-slate-300" />
              </div>
            )}
            <div className="text-right">
              <p className="text-sm text-white truncate max-w-[160px]">
                {user.displayName || user.email}
              </p>
              {user.displayName && user.email && (
                <p className="text-xs text-slate-400 truncate max-w-[160px]">
                  {user.email}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void logOut()}
              className="text-xs text-slate-400 hover:text-white transition cursor-pointer hover:bg-slate-600 p-2 rounded-full border border-slate-700/50"
              aria-label="Sign out"
            >
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <div className="bg-[#2A3241] p-2 rounded-full">
            <User size={20} className="text-slate-300" />
          </div>
        )}
      </header>

      {/* ── DRAFT TOOLBAR (Sub-header) ── */}
      <DraftToolbar
        title={title || "Untitled Draft"}
        versionNumber={getVersionCount() || 1}
        showEditsActive={showEditsMode}
        chatPanelOpen={chatPanelOpen}
        chatTitle={originalPrompt ? `${originalPrompt.slice(0, 40)}…` : "Edit Chat"}
        onClose={handleClose}
        onToggleShowEdits={toggleShowEdits}
        onVerifySources={handleVerifySources}
        onExport={handleExport}
        onToggleChatPanel={() => setChatPanelOpen((prev) => !prev)}
      />

      {/* ── MAIN CONTENT AREA (Three-Panel) ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── LEFT SIDEBAR: Version History (Phase 4 stub) ── */}
        <aside
          className="w-[240px] bg-[#161B28] border-r border-slate-700/50 flex flex-col shrink-0 overflow-y-auto chat-scroll"
          id="draft-version-sidebar"
        >
          {/* Prompt Display */}
          <div className="p-4 border-b border-slate-700/50">
            <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
              Prompt
            </p>
            <p className="text-xs text-slate-300 leading-relaxed">
              {originalPrompt || "No prompt provided"}
            </p>
          </div>

          {/* Placeholder for Published status */}
          <div className="px-4 py-2 border-b border-slate-700/50">
            <p className="text-[10px] text-slate-500 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
              Published to a place…
            </p>
          </div>

          {/* Version History Label */}
          <div className="px-4 py-3">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Version History
            </p>
          </div>

          {/* Version Cards (Phase 4 will populate these) */}
          <div className="flex-1 px-3 space-y-2">
            {/* Phase 4: VersionHistoryPanel renders here */}
            <div className="bg-[#D4AF37]/10 border border-[#D4AF37]/30 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-white">
                  Version 1
                </span>
                <span className="text-[9px] bg-[#D4AF37]/20 text-[#D4AF37] px-1.5 py-0.5 rounded font-medium">
                  Selected
                </span>
              </div>
              <p className="text-[10px] text-slate-400 leading-relaxed">
                {isLoading
                  ? "Generating draft…"
                  : "Original AI-generated draft."}
              </p>
            </div>
          </div>
        </aside>

        {/* ── CENTER: Document Editor ── */}
        <main className="flex-1 flex flex-col min-w-0 bg-[#2A3241]">
          {/* Editor Toolbar (zoom, page, save) */}
          <EditorToolbar
            zoomLevel={zoomLevel}
            currentPage={1}
            totalPages={1}
            onSave={handleSave}
            onZoomIn={handleZoomIn}
            onZoomOut={handleZoomOut}
            onToggleFullWidth={handleToggleFullWidth}
            onPrevPage={() => {}}
            onNextPage={() => {}}
            onDownload={handleDownload}
          />

          {/* Editor Area */}
          <div
            className="flex-1 overflow-auto p-6 flex justify-center"
            id="draft-editor-area"
          >
            {isLoading ? (
              <div className="flex flex-col items-center justify-center gap-4 text-slate-400">
                <div className="w-8 h-8 border-2 border-[#D4AF37] border-t-transparent rounded-full animate-spin" />
                <p className="text-sm">Generating your legal draft…</p>
                <p className="text-xs text-slate-500">
                  This may take 8–15 seconds
                </p>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center gap-3 text-red-400">
                <p className="text-sm font-medium">
                  Failed to generate draft
                </p>
                <p className="text-xs text-slate-500 max-w-md text-center">
                  {error}
                </p>
              </div>
            ) : (
              <div
                className="w-full max-w-[816px] shadow-2xl"
                style={{ zoom: `${zoomLevel}%` }}
              >
                <TiptapEditor
                  content={documentJson}
                  editable={!showEditsMode}
                  onUpdate={handleEditorUpdate}
                  onSelectionUpdate={handleSelectionUpdate}
                  sources={sources}
                  onViewCitationSource={handleViewCitationSource}
                />
              </div>
            )}
          </div>
        </main>

        {/* ── RIGHT SIDEBAR: Chat Panel (Phase 3 stub) ── */}
        {chatPanelOpen && (
          <aside
            className="w-[340px] bg-[#161B28] border-l border-slate-700/50 flex flex-col shrink-0 overflow-hidden"
            id="draft-chat-panel"
          >
            {/* Document Preview (read-only rendered view) */}
            <div className="flex-1 overflow-y-auto p-4 chat-scroll">
              {markdownContent ? (
                <div className="text-xs text-slate-300 leading-relaxed prose prose-invert prose-xs max-w-none">
                  {/* Phase 3: Full chat panel with messages will replace this */}
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-3">
                    Document Preview
                  </p>
                  <div className="whitespace-pre-wrap text-[11px] text-slate-400">
                    {markdownContent.slice(0, 800)}
                    {markdownContent.length > 800 && "…"}
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-slate-500 text-xs">
                  No draft content yet
                </div>
              )}
            </div>

            {/* Chat Input (Phase 3 stub) */}
            <div className="border-t border-slate-700/50 p-3">
              <div className="flex items-center gap-2 bg-[#1D2530] rounded-lg px-3 py-2.5 border border-slate-700/50">
                <input
                  type="text"
                  placeholder="Edit this document..."
                  className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 outline-none"
                  disabled
                  id="draft-chat-input"
                />
                <button
                  type="button"
                  className="text-[#D4AF37] hover:text-[#D4AF37]/80 transition"
                  disabled
                  aria-label="Send edit request"
                >
                  →
                </button>
              </div>
              {/* Ask / Edit mode toggle */}
              <div className="flex items-center gap-2 mt-2">
                <button
                  type="button"
                  className="text-[10px] px-2.5 py-1 rounded bg-slate-700/50 text-slate-400 cursor-not-allowed"
                  disabled
                >
                  Ask
                </button>
                <button
                  type="button"
                  className="text-[10px] px-2.5 py-1 rounded bg-[#D4AF37]/10 text-[#D4AF37] cursor-not-allowed"
                  disabled
                >
                  Edit
                </button>
              </div>
            </div>
          </aside>
        )}
      </div>

      <SourceVerificationPanel
        open={sourcePanelOpen}
        document={documentJson}
        sources={sources}
        activeCitationId={activeCitationId}
        onClose={handleCloseSourcePanel}
      />
    </div>
  );
}
