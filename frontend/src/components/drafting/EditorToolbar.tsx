"use client";

/**
 * EditorToolbar — In-editor formatting toolbar above the document.
 *
 * Matches the mockup toolbar: save, zoom in/out, page size toggle,
 * page navigation, and download button. Also provides basic
 * formatting controls visible on text selection.
 *
 * @module components/drafting/EditorToolbar
 */

import {
  Save,
  ZoomIn,
  ZoomOut,
  Maximize2,
  ChevronLeft,
  ChevronRight,
  Download,
} from "lucide-react";

// ─── Props ──────────────────────────────────────────────────────

export interface EditorToolbarProps {
  /** Current zoom level (percentage, e.g. 100). */
  zoomLevel: number;
  /** Current page number (for multi-page display). */
  currentPage: number;
  /** Total page count. */
  totalPages: number;
  /** Callback to save the current document. */
  onSave: () => void;
  /** Callback to zoom in. */
  onZoomIn: () => void;
  /** Callback to zoom out. */
  onZoomOut: () => void;
  /** Callback to toggle full-width mode. */
  onToggleFullWidth: () => void;
  /** Callback to navigate to the previous page. */
  onPrevPage: () => void;
  /** Callback to navigate to the next page. */
  onNextPage: () => void;
  /** Callback to download/export. */
  onDownload: () => void;
}

// ─── Component ──────────────────────────────────────────────────

export function EditorToolbar({
  zoomLevel,
  currentPage,
  totalPages,
  onSave,
  onZoomIn,
  onZoomOut,
  onToggleFullWidth,
  onPrevPage,
  onNextPage,
  onDownload,
}: EditorToolbarProps) {
  return (
    <div
      className="flex items-center justify-between px-4 py-2 bg-[#1D2530] border-b border-slate-700/30 shrink-0 rounded-t-lg"
      id="editor-toolbar"
    >
      {/* ── Left: Save + Zoom ── */}
      <div className="flex items-center gap-1">
        <ToolbarButton
          icon={<Save size={15} />}
          onClick={onSave}
          label="Save"
          id="editor-toolbar-save"
        />

        <span className="text-slate-600 mx-1">|</span>

        <ToolbarButton
          icon={<ZoomOut size={15} />}
          onClick={onZoomOut}
          label="Zoom out"
          id="editor-toolbar-zoom-out"
        />
        <ToolbarButton
          icon={<ZoomIn size={15} />}
          onClick={onZoomIn}
          label="Zoom in"
          id="editor-toolbar-zoom-in"
        />
        <span
          className="min-w-12 text-center text-xs tabular-nums text-slate-400"
          aria-live="polite"
        >
          {zoomLevel}%
        </span>
        <ToolbarButton
          icon={<Maximize2 size={15} />}
          onClick={onToggleFullWidth}
          label="Toggle full width"
          id="editor-toolbar-full-width"
        />
      </div>

      {/* ── Center: Page Navigation ── */}
      <div className="flex items-center gap-2 text-slate-400 text-sm">
        <ToolbarButton
          icon={<ChevronLeft size={15} />}
          onClick={onPrevPage}
          label="Previous page"
          disabled={currentPage <= 1}
          id="editor-toolbar-prev-page"
        />
        <span className="min-w-[60px] text-center">
          {currentPage} / {totalPages}
        </span>
        <ToolbarButton
          icon={<ChevronRight size={15} />}
          onClick={onNextPage}
          label="Next page"
          disabled={currentPage >= totalPages}
          id="editor-toolbar-next-page"
        />
      </div>

      {/* ── Right: Download ── */}
      <ToolbarButton
        icon={<Download size={15} />}
        onClick={onDownload}
        label="Download"
        id="editor-toolbar-download"
      />
    </div>
  );
}

// ─── ToolbarButton ──────────────────────────────────────────────

interface ToolbarButtonProps {
  icon: React.ReactNode;
  onClick: () => void;
  label: string;
  disabled?: boolean;
  id: string;
}

function ToolbarButton({ icon, onClick, label, disabled, id }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-600/50 rounded transition disabled:opacity-30 disabled:cursor-not-allowed"
      aria-label={label}
      id={id}
    >
      {icon}
    </button>
  );
}
