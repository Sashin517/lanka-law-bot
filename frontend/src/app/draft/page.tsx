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
 * Phase 6 exports immutable accepted versions through DOCX/PDF strategies;
 * pending suggestions and presentation-only diff overlays are excluded.
 *
 * @module app/draft/page
 */

import { useState, useCallback, useEffect, useRef } from "react";
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
import { ExecutionActivityDisclosure } from "@/components/ExecutionActivityDisclosure";
import { EditorToolbar } from "@/components/drafting/EditorToolbar";
import { TiptapEditor } from "@/components/drafting/TiptapEditor";
import { DraftChatPanel } from "@/components/drafting/DraftChatPanel";
import {
  DraftSidebar,
  type DraftSidebarView,
} from "@/components/drafting/DraftSidebar";
import { ShowEditsLegend } from "@/components/drafting/ShowEditsLegend";
import { ExportModal } from "@/components/drafting/ExportModal";
import { documentBuilder } from "@/lib/drafting/documentBuilder";
import { diffService } from "@/lib/drafting/diffService";
import type { SourceRef } from "@/lib/api";
import type { IEditorService } from "@/lib/drafting/editorService";
import { useDraftDocumentStore } from "@/store/draftDocumentStore";
import { useVersionStore } from "@/store/versionStore";
import { useChatEditStore } from "@/store/chatEditStore";
import { useActivityStreamStore } from "@/store/activityStreamStore";
import { useAuth } from "@/contexts/AuthProvider";
import { logOut } from "@/lib/firebase/auth";
import type {
  ChatMode,
  DocumentVersion,
  EditorSelection,
  TiptapDocument,
} from "@/types/drafting";

const MANUAL_SNAPSHOT_IDLE_MS = 5_000;

// ─── Component ──────────────────────────────────────────────────

export default function DraftPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  // ── Stores ──
  const {
    draftId,
    title,
    originalPrompt,
    documentJson,
    sources,
    isLoading,
    error,
    updateContent,
    loadFromSnapshot,
  } = useDraftDocumentStore();

  const {
    activeDraftId,
    versions,
    currentVersionId,
    showEditsMode,
    initializeDraft,
  } = useVersionStore();

  const { setSelection, setChatMode } = useChatEditStore();
  const activitySteps = useActivityStreamStore((state) => state.steps);
  const activityStreaming = useActivityStreamStore(
    (state) => state.isStreaming,
  );
  const activityError = useActivityStreamStore((state) => state.error);
  const activitySessionId = useActivityStreamStore((state) => state.sessionId);

  // ── Local UI state ──
  const [chatPanelOpen, setChatPanelOpen] = useState(true);
  const [zoomLevel, setZoomLevel] = useState(100);
  const [leftSidebarView, setLeftSidebarView] =
    useState<DraftSidebarView>("versions");
  const [activeCitationId, setActiveCitationId] = useState<string | null>(null);
  const [editorService, setEditorService] = useState<IEditorService | null>(
    null,
  );
  const [visibleDiffCount, setVisibleDiffCount] = useState(0);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const manualSnapshotTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const pendingManualSnapshotRef = useRef<{
    content: TiptapDocument;
    sources: SourceRef[];
  } | null>(null);

  const flushManualSnapshot = useCallback(() => {
    if (manualSnapshotTimerRef.current) {
      clearTimeout(manualSnapshotTimerRef.current);
      manualSnapshotTimerRef.current = null;
    }

    const pending = pendingManualSnapshotRef.current;
    pendingManualSnapshotRef.current = null;
    if (!pending) return;

    useVersionStore
      .getState()
      .createVersion(pending.content, pending.sources, "Manual edit", "user");
  }, []);

  useEffect(() => {
    if (!draftId || !documentJson || isLoading) return;

    initializeDraft(draftId);
    const versionState = useVersionStore.getState();
    if (versionState.getVersionCount() === 0) {
      versionState.createVersion(
        documentJson,
        sources,
        "Original AI-generated draft",
        "ai",
      );
    }
  }, [documentJson, draftId, initializeDraft, isLoading, sources]);

  useEffect(
    () => () => {
      flushManualSnapshot();
      useVersionStore.getState().setShowEditsMode(false);
    },
    [flushManualSnapshot],
  );
  // ── Editor callbacks ──
  const handleEditorUpdate = useCallback(
    (json: TiptapDocument) => {
      updateContent(json, documentBuilder.toMarkdown(json));
      pendingManualSnapshotRef.current = {
        content: json,
        sources: useDraftDocumentStore.getState().sources,
      };
      if (manualSnapshotTimerRef.current) {
        clearTimeout(manualSnapshotTimerRef.current);
      }
      manualSnapshotTimerRef.current = setTimeout(
        flushManualSnapshot,
        MANUAL_SNAPSHOT_IDLE_MS,
      );
    },
    [flushManualSnapshot, updateContent],
  );

  const handleSelectionUpdate = useCallback(
    (selection: EditorSelection | null) => {
      setSelection(selection);
    },
    [setSelection],
  );

  const handleSelectionAction = useCallback(
    (mode: ChatMode, selection: EditorSelection) => {
      setSelection({ ...selection });
      setChatMode(mode);
      setChatPanelOpen(true);
    },
    [setChatMode, setSelection],
  );

  const exitShowEditsMode = useCallback(() => {
    editorService?.clearDiffOverlay();
    useVersionStore.getState().setShowEditsMode(false);
    setVisibleDiffCount(0);
  }, [editorService]);

  const handleToggleShowEdits = useCallback(() => {
    const versionState = useVersionStore.getState();
    if (versionState.showEditsMode) {
      exitShowEditsMode();
      return;
    }

    flushManualSnapshot();
    const refreshedState = useVersionStore.getState();
    const original = refreshedState.getOriginalVersion();
    const current = refreshedState.getCurrentVersion();
    if (!editorService || !original || !current) return;

    const changes = diffService.computeDiff(original.content, current.content);
    editorService.showDiffOverlay({
      fromVersionId: original.id,
      toVersionId: current.id,
      versionNumber: current.versionNumber,
      timestamp: current.createdAt,
      changes,
    });
    refreshedState.setShowEditsMode(true);
    setVisibleDiffCount(changes.length);
    setSelection(null);
  }, [editorService, exitShowEditsMode, flushManualSnapshot, setSelection]);

  const handleBeforeChatRequest = useCallback(() => {
    if (useVersionStore.getState().showEditsMode) exitShowEditsMode();
    flushManualSnapshot();
  }, [exitShowEditsMode, flushManualSnapshot]);

  const handleBeforeRestore = useCallback(() => {
    if (useVersionStore.getState().showEditsMode) exitShowEditsMode();
    flushManualSnapshot();
  }, [exitShowEditsMode, flushManualSnapshot]);

  // ── Toolbar callbacks ──
  const handleClose = useCallback(() => {
    flushManualSnapshot();
    router.push("/");
  }, [flushManualSnapshot, router]);

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
    setLeftSidebarView("sources");
  }, []);

  const handleViewCitationSource = useCallback((citationId: string) => {
    setActiveCitationId(citationId);
    setLeftSidebarView("sources");
  }, []);

  const handleShowVersions = useCallback(() => {
    setActiveCitationId(null);
    setLeftSidebarView("versions");
  }, []);

  const handleExport = useCallback(() => {
    flushManualSnapshot();
    if (useVersionStore.getState().getCurrentVersion()) {
      setExportModalOpen(true);
    }
  }, [flushManualSnapshot]);

  const handleSave = useCallback(() => {
    flushManualSnapshot();
  }, [flushManualSnapshot]);

  const handleDownload = useCallback(() => {
    flushManualSnapshot();
    if (useVersionStore.getState().getCurrentVersion()) {
      setExportModalOpen(true);
    }
  }, [flushManualSnapshot]);

  const handleVersionRestored = useCallback(
    (version: DocumentVersion) => {
      loadFromSnapshot(
        version.content,
        documentBuilder.toMarkdown(version.content),
        version.sources,
      );
      setSelection(null);
    },
    [loadFromSnapshot, setSelection],
  );

  const visibleVersionCount = activeDraftId === draftId ? versions.length : 0;
  const acceptedVersion =
    activeDraftId === draftId
      ? (versions.find((version) => version.id === currentVersionId) ?? null)
      : null;

  // ── Render ──
  return (
    <div className="flex h-dvh max-h-dvh min-h-0 flex-col overflow-hidden bg-[#2A3241] font-sans">
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
        versionNumber={visibleVersionCount || 1}
        versionsActive={leftSidebarView === "versions"}
        verifySourcesActive={leftSidebarView === "sources"}
        showEditsActive={showEditsMode}
        showEditsDisabled={!editorService || visibleVersionCount === 0}
        exportDisabled={!acceptedVersion}
        chatPanelOpen={chatPanelOpen}
        chatTitle={
          originalPrompt ? `${originalPrompt.slice(0, 40)}…` : "Edit Chat"
        }
        onClose={handleClose}
        onShowVersions={handleShowVersions}
        onToggleShowEdits={handleToggleShowEdits}
        onVerifySources={handleVerifySources}
        onExport={handleExport}
        onToggleChatPanel={() => setChatPanelOpen((prev) => !prev)}
      />

      {/* ── MAIN CONTENT AREA (Three-Panel) ── */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* ── LEFT SIDEBAR: Version History ── */}
        <DraftSidebar
          activeView={leftSidebarView}
          draftId={draftId}
          originalPrompt={originalPrompt}
          editor={editorService}
          document={documentJson}
          sources={sources}
          activeCitationId={activeCitationId}
          onBeforeRestore={handleBeforeRestore}
          onVersionRestored={handleVersionRestored}
        />

        {/* ── CENTER: Document Editor ── */}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-white">
          {showEditsMode && (
            <ShowEditsLegend
              currentVersionNumber={visibleVersionCount || 1}
              changeCount={visibleDiffCount}
            />
          )}
          {/* Editor Toolbar (zoom, page, save) */}
          <EditorToolbar
            editor={editorService}
            editable={!showEditsMode}
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
            className="flex min-h-0 flex-1 justify-center overflow-auto overscroll-contain bg-white p-6"
            id="draft-editor-area"
          >
            {isLoading ? (
              <div className="flex w-full max-w-md flex-col items-center justify-center gap-4">
                <div className="w-full rounded-xl border border-slate-700/50 bg-[#161B28] p-5 shadow-xl">
                  <div className="mb-4 flex items-center gap-3">
                    <div
                      className="h-6 w-6 rounded-full border-2 border-[#D4AF37] border-t-transparent animate-spin"
                      aria-hidden="true"
                    />
                    <p className="text-sm font-medium text-slate-200">
                      Generating your legal draft…
                    </p>
                  </div>
                  <ExecutionActivityDisclosure
                    key={activitySessionId ?? "draft-generation-activity"}
                    steps={activitySteps}
                    isStreaming={activityStreaming}
                    error={activityError}
                    compact
                    streamClassName="max-h-72 pr-1 chat-scroll"
                  />
                </div>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center gap-3 text-red-400">
                <p className="text-sm font-medium">Failed to generate draft</p>
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
                  onBlur={flushManualSnapshot}
                  onSelectionUpdate={handleSelectionUpdate}
                  onSelectionAction={handleSelectionAction}
                  onEditorReady={setEditorService}
                  sources={sources}
                  onViewCitationSource={handleViewCitationSource}
                />
              </div>
            )}
          </div>
        </main>

        {/* ── RIGHT SIDEBAR: Chat-driven editing ── */}
        {chatPanelOpen && (
          <DraftChatPanel
            editor={editorService}
            onBeforeRequest={handleBeforeChatRequest}
            onViewCitationSource={handleViewCitationSource}
          />
        )}
      </div>

      <ExportModal
        open={exportModalOpen}
        version={acceptedVersion}
        title={title || "Legal Document - LankaLawBot"}
        author={user?.displayName || "LankaLawBot AI"}
        onClose={() => setExportModalOpen(false)}
      />
    </div>
  );
}
