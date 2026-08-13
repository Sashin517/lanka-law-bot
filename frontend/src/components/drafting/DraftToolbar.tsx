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
  /** Whether the left sidebar is showing versions. */
  versionsActive?: boolean;
  /** Whether the left sidebar is showing source verification. */
  verifySourcesActive?: boolean;
  /** Whether "Show Edits" mode is active. */
  showEditsActive: boolean;
  /** Whether an editor and original version are available for comparison. */
  showEditsDisabled?: boolean;
  /** Whether the chat panel is visible. */
  chatPanelOpen: boolean;
  /** Whether no accepted snapshot is available for export. */
  exportDisabled?: boolean;
  /** Chat panel title (e.g. "Event Chronology Creation Chat"). */
  chatTitle: string;

  // ── Callbacks ──
  onClose: () => void;
  onShowVersions: () => void;
  onToggleShowEdits: () => void;
  onVerifySources: () => void;
  onExport: () => void;
  onToggleChatPanel: () => void;
}

// ─── Component ──────────────────────────────────────────────────

export function DraftToolbar({
  title,
  versionNumber,
  versionsActive = false,
  verifySourcesActive = false,
  showEditsActive,
  showEditsDisabled = false,
  chatPanelOpen,
  exportDisabled = false,
  chatTitle,
  onClose,
  onShowVersions,
  onToggleShowEdits,
  onVerifySources,
  onExport,
  onToggleChatPanel,
}: DraftToolbarProps) {
  return (
    <div
      className="flex items-center justify-between px-6 py-2.5 bg-app-panel border-b border-app-border/50 text-sm shrink-0"
      id="draft-toolbar"
    >
      {/* ── Left: Close + Title ── */}
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onClose}
          className="text-app-muted hover:text-app-strong transition p-1 rounded hover:bg-app-hover/50"
          aria-label="Close draft"
          id="draft-toolbar-close"
        >
          <X size={18} />
        </button>

        <span className="text-app-subtle">|</span>

        <div className="flex items-center gap-2 text-app-strong">
          <ChevronLeft size={16} className="text-app-muted" />
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
          onClick={onShowVersions}
          className={`flex items-center gap-1.5 rounded px-3 py-1.5 transition ${
            versionsActive
              ? "bg-app-accent/10 text-app-accent"
              : "text-app-tertiary hover:bg-app-hover/50 hover:text-app-strong"
          }`}
          aria-label={`Version ${versionNumber}`}
          aria-pressed={versionsActive}
          id="draft-toolbar-version"
        >
          <History size={14} />
          <span>Version {versionNumber}</span>
        </button>

        <span className="text-app-faint mx-1">|</span>

        {/* Show Edits Toggle */}
        <button
          type="button"
          onClick={onToggleShowEdits}
          disabled={showEditsDisabled}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition ${
            showEditsActive
              ? "text-app-accent bg-app-accent/10"
              : "text-app-tertiary hover:text-app-strong hover:bg-app-hover/50"
          } disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent`}
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
          className={`flex items-center gap-1.5 rounded px-3 py-1.5 transition ${
            verifySourcesActive
              ? "bg-app-accent/10 text-app-accent"
              : "text-app-tertiary hover:bg-app-hover/50 hover:text-app-strong"
          }`}
          aria-label="Verify sources"
          aria-pressed={verifySourcesActive}
          id="draft-toolbar-verify-sources"
        >
          <Link2 size={14} />
          <span>Verify Sources</span>
        </button>

        {/* Export */}
        <button
          type="button"
          onClick={onExport}
          disabled={exportDisabled}
          className="flex items-center gap-1.5 px-3 py-1.5 text-app-tertiary hover:text-app-strong hover:bg-app-hover/50 rounded transition disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
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
            ? "text-app-accent bg-app-accent/10"
            : "text-app-tertiary hover:text-app-strong hover:bg-app-hover/50"
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
