"use client";

/**
 * DraftToolbar — Sub-header toolbar for the drafting page.
 *
 * Matches the UI mockup: Shows the draft title, version indicator,
 * and action buttons (Show Edits, Verify Sources, Export, Chat toggle).
 *
 * @module components/drafting/DraftToolbar
 */

import {
  X,
  ChevronLeft,
  Pencil,
  Link2,
  Download,
  ArrowLeft,
  History,
} from "lucide-react";

// ─── Props ──────────────────────────────────────────────────────

export interface DraftToolbarProps {
  /** Draft document title (e.g. "Memo on Causes of Action"). */
  title: string;
  /** Current version number. */
  versionNumber: number;
  /** Whether "Show Edits" mode is active. */
  showEditsActive: boolean;
  /** Whether the chat panel is visible. */
  chatPanelOpen: boolean;
  /** Chat panel title (e.g. "Event Chronology Creation Chat"). */
  chatTitle: string;

  // ── Callbacks ──
  onClose: () => void;
  onToggleShowEdits: () => void;
  onVerifySources: () => void;
  onExport: () => void;
  onToggleChatPanel: () => void;
}

// ─── Component ──────────────────────────────────────────────────

export function DraftToolbar({
  title,
  versionNumber,
  showEditsActive,
  chatPanelOpen,
  chatTitle,
  onClose,
  onToggleShowEdits,
  onVerifySources,
  onExport,
  onToggleChatPanel,
}: DraftToolbarProps) {
  return (
    <div
      className="flex items-center justify-between px-6 py-2.5 bg-[#161B28] border-b border-slate-700/50 text-sm shrink-0"
      id="draft-toolbar"
    >
      {/* ── Left: Close + Title ── */}
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-white transition p-1 rounded hover:bg-slate-700/50"
          aria-label="Close draft"
          id="draft-toolbar-close"
        >
          <X size={18} />
        </button>

        <span className="text-slate-500">|</span>

        <div className="flex items-center gap-2 text-white">
          <ChevronLeft size={16} className="text-slate-400" />
          <span className="font-medium truncate max-w-[300px]">
            {title || "Untitled Draft"}
          </span>
        </div>
      </div>

      {/* ── Center: Action Buttons ── */}
      <div className="flex items-center gap-1">
        {/* Version Indicator */}
        <button
          type="button"
          className="flex items-center gap-1.5 px-3 py-1.5 text-slate-300 hover:text-white hover:bg-slate-700/50 rounded transition"
          aria-label={`Version ${versionNumber}`}
          id="draft-toolbar-version"
        >
          <History size={14} />
          <span>Version {versionNumber}</span>
        </button>

        <span className="text-slate-600 mx-1">|</span>

        {/* Show Edits Toggle */}
        <button
          type="button"
          onClick={onToggleShowEdits}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition ${
            showEditsActive
              ? "text-[#D4AF37] bg-[#D4AF37]/10"
              : "text-slate-300 hover:text-white hover:bg-slate-700/50"
          }`}
          aria-label="Toggle show edits"
          aria-pressed={showEditsActive}
          id="draft-toolbar-show-edits"
        >
          <Pencil size={14} />
          <span>Show Edits</span>
        </button>

        {/* Verify Sources */}
        <button
          type="button"
          onClick={onVerifySources}
          className="flex items-center gap-1.5 px-3 py-1.5 text-slate-300 hover:text-white hover:bg-slate-700/50 rounded transition"
          aria-label="Verify sources"
          id="draft-toolbar-verify-sources"
        >
          <Link2 size={14} />
          <span>Verify Sources</span>
        </button>

        {/* Export */}
        <button
          type="button"
          onClick={onExport}
          className="flex items-center gap-1.5 px-3 py-1.5 text-slate-300 hover:text-white hover:bg-slate-700/50 rounded transition"
          aria-label="Export draft"
          id="draft-toolbar-export"
        >
          <Download size={14} />
          <span>Export</span>
        </button>
      </div>

      {/* ── Right: Chat Panel Toggle ── */}
      <button
        type="button"
        onClick={onToggleChatPanel}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition ${
          chatPanelOpen
            ? "text-[#D4AF37] bg-[#D4AF37]/10"
            : "text-slate-300 hover:text-white hover:bg-slate-700/50"
        }`}
        aria-label="Toggle chat panel"
        aria-pressed={chatPanelOpen}
        id="draft-toolbar-chat-toggle"
      >
        <ArrowLeft size={14} />
        <span className="truncate max-w-[200px]">
          {chatTitle || "Edit Chat"}
        </span>
      </button>
    </div>
  );
}
