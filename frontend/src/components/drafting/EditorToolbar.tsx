"use client";

/** Document-formatting and workspace controls for the Tiptap editor. */

import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold as BoldIcon,
  ChevronLeft,
  ChevronRight,
  Download,
  Italic as ItalicIcon,
  ListIndentDecrease,
  ListIndentIncrease,
  Maximize2,
  Redo2,
  Save,
  Strikethrough,
  Underline as UnderlineIcon,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { ToolbarDropdown } from "@/components/drafting/ToolbarDropdown";
import type { IEditorService } from "@/lib/drafting/editorService";
import {
  DEFAULT_FONT_SIZE,
  DEFAULT_LINE_SPACING,
  DEFAULT_PARAGRAPH_SPACING,
  FONT_SIZES,
  LINE_SPACINGS,
  MAX_INDENT_LEVEL,
  lineSpacingLabel,
  type BlockType,
  type EditorFormattingState,
  type TextAlignment,
} from "@/lib/drafting/formatting";

const BLOCK_OPTIONS = [
  { value: "paragraph", label: "Paragraph" },
  { value: "heading-1", label: "Heading 1" },
  { value: "heading-2", label: "Heading 2" },
  { value: "heading-3", label: "Heading 3" },
  { value: "heading-4", label: "Heading 4" },
] as const;
const FONT_SIZE_OPTIONS = FONT_SIZES.map((size) => ({
  value: String(size),
  label: `${size} pt`,
}));
const LINE_SPACING_OPTIONS = LINE_SPACINGS.map((spacing) => ({
  value: String(spacing),
  label: lineSpacingLabel(spacing),
}));

export interface EditorToolbarProps {
  editor: IEditorService | null;
  editable?: boolean;
  zoomLevel: number;
  currentPage: number;
  totalPages: number;
  onSave: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onToggleFullWidth: () => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  onDownload: () => void;
}

const DEFAULT_STATE: EditorFormattingState = {
  blockType: "paragraph",
  fontSize: DEFAULT_FONT_SIZE,
  alignment: "left",
  indentLevel: 0,
  lineSpacing: DEFAULT_LINE_SPACING,
  spacingBefore: DEFAULT_PARAGRAPH_SPACING,
  spacingAfter: DEFAULT_PARAGRAPH_SPACING,
  bold: false,
  italic: false,
  underline: false,
  strike: false,
  canUndo: false,
  canRedo: false,
};

export function EditorToolbar({
  editor,
  editable = true,
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
  const [formatting, setFormatting] =
    useState<EditorFormattingState>(DEFAULT_STATE);

  useEffect(() => {
    if (!editor) return;
    return editor.subscribeToFormatting(setFormatting);
  }, [editor]);

  const formattingDisabled = !editor || !editable;

  return (
    <div
      className="shrink-0 overflow-hidden rounded-t-xl border-b border-slate-200 bg-gradient-to-b from-white to-slate-50 shadow-[0_2px_12px_rgba(15,23,42,0.08)]"
      id="editor-toolbar"
    >
      <div
        className="flex min-w-0 items-center gap-2 overflow-x-auto border-b border-slate-200 px-3 py-2.5 [scrollbar-width:thin]"
        aria-label="Document formatting"
      >
        <ToolbarGroup label="History">
          <FormatButton
            icon={<Undo2 size={16} />}
            label="Undo"
            disabled={formattingDisabled || !formatting.canUndo}
            onClick={() => editor?.undo()}
          />
          <FormatButton
            icon={<Redo2 size={16} />}
            label="Redo"
            disabled={formattingDisabled || !formatting.canRedo}
            onClick={() => editor?.redo()}
          />
        </ToolbarGroup>

        <ToolbarGroup label="Text style">
          <ToolbarDropdown
            label="Paragraph style"
            value={formatting.blockType}
            options={BLOCK_OPTIONS}
            disabled={formattingDisabled}
            onChange={(value) => editor?.setBlockType(value as BlockType)}
            className="w-32"
          />

          <ToolbarDropdown
            label="Font size"
            value={String(formatting.fontSize)}
            options={FONT_SIZE_OPTIONS}
            disabled={formattingDisabled}
            onChange={(value) =>
              editor?.setFontSize(
                Number(value) as EditorFormattingState["fontSize"],
              )
            }
            className="w-[82px]"
          />
        </ToolbarGroup>

        <ToolbarGroup label="Inline formatting">
          <FormatButton
            icon={<BoldIcon size={16} />}
            label="Bold"
            active={formatting.bold}
            disabled={formattingDisabled}
            onClick={() => editor?.toggleInlineFormat("bold")}
          />
          <FormatButton
            icon={<ItalicIcon size={16} />}
            label="Italic"
            active={formatting.italic}
            disabled={formattingDisabled}
            onClick={() => editor?.toggleInlineFormat("italic")}
          />
          <FormatButton
            icon={<UnderlineIcon size={16} />}
            label="Underline"
            active={formatting.underline}
            disabled={formattingDisabled}
            onClick={() => editor?.toggleInlineFormat("underline")}
          />
          <FormatButton
            icon={<Strikethrough size={16} />}
            label="Strikethrough"
            active={formatting.strike}
            disabled={formattingDisabled}
            onClick={() => editor?.toggleInlineFormat("strike")}
          />
        </ToolbarGroup>

        <ToolbarGroup label="Alignment">
          <AlignmentButton
            alignment="left"
            current={formatting.alignment}
            disabled={formattingDisabled}
            editor={editor}
            icon={<AlignLeft size={16} />}
          />
          <AlignmentButton
            alignment="center"
            current={formatting.alignment}
            disabled={formattingDisabled}
            editor={editor}
            icon={<AlignCenter size={16} />}
          />
          <AlignmentButton
            alignment="right"
            current={formatting.alignment}
            disabled={formattingDisabled}
            editor={editor}
            icon={<AlignRight size={16} />}
          />
          <AlignmentButton
            alignment="justify"
            current={formatting.alignment}
            disabled={formattingDisabled}
            editor={editor}
            icon={<AlignJustify size={16} />}
          />
        </ToolbarGroup>

        <ToolbarGroup label="Paragraph layout">
          <FormatButton
            icon={<ListIndentDecrease size={16} />}
            label="Decrease indentation"
            disabled={formattingDisabled || formatting.indentLevel === 0}
            onClick={() => editor?.setIndentLevel(formatting.indentLevel - 1)}
          />
          <FormatButton
            icon={<ListIndentIncrease size={16} />}
            label="Increase indentation"
            disabled={
              formattingDisabled || formatting.indentLevel >= MAX_INDENT_LEVEL
            }
            onClick={() => editor?.setIndentLevel(formatting.indentLevel + 1)}
          />
          <ToolbarDropdown
            label="Line spacing"
            value={String(formatting.lineSpacing)}
            options={LINE_SPACING_OPTIONS}
            disabled={formattingDisabled}
            onChange={(value) =>
              editor?.setLineSpacing(
                Number(value) as EditorFormattingState["lineSpacing"],
              )
            }
            className="w-[94px]"
          />
        </ToolbarGroup>
      </div>

      <div className="flex items-center justify-between bg-slate-50/85 px-3 py-1.5">
        <div className="flex items-center gap-1">
          <ToolbarButton
            icon={<Save size={15} />}
            onClick={onSave}
            label="Save"
            id="editor-toolbar-save"
          />
          <ToolbarDivider />
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
            className="min-w-12 text-center text-xs tabular-nums text-slate-600"
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

        <div className="flex items-center gap-2 text-sm text-slate-600">
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

        <ToolbarButton
          icon={<Download size={15} />}
          onClick={onDownload}
          label="Download"
          id="editor-toolbar-download"
        />
      </div>
    </div>
  );
}

function AlignmentButton({
  alignment,
  current,
  disabled,
  editor,
  icon,
}: {
  alignment: TextAlignment;
  current: TextAlignment;
  disabled: boolean;
  editor: IEditorService | null;
  icon: ReactNode;
}) {
  return (
    <FormatButton
      icon={icon}
      label={`Align ${alignment}`}
      active={current === alignment}
      disabled={disabled}
      onClick={() => editor?.setTextAlignment(alignment)}
    />
  );
}

function FormatButton({
  icon,
  onClick,
  label,
  active,
  disabled = false,
}: {
  icon: ReactNode;
  onClick: () => void;
  label: string;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
      disabled={disabled}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-transparent transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B58B16]/35 disabled:cursor-not-allowed disabled:opacity-30 ${
        active
          ? "border-[#B58B16]/30 bg-[#D4AF37]/14 text-[#7A5B0A] shadow-sm"
          : "text-slate-600 hover:border-slate-200 hover:bg-slate-100 hover:text-slate-950"
      }`}
      aria-label={label}
      aria-pressed={active === undefined ? undefined : active}
      title={label}
    >
      {icon}
    </button>
  );
}

function ToolbarGroup({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="flex shrink-0 items-center gap-0.5 rounded-lg border border-slate-200 bg-white p-1 shadow-[0_1px_2px_rgba(15,23,42,0.06)]"
    >
      {children}
    </div>
  );
}

function ToolbarDivider() {
  return (
    <span
      aria-hidden="true"
      className="mx-1 h-5 w-px shrink-0 bg-slate-200"
    />
  );
}

function ToolbarButton({
  icon,
  onClick,
  label,
  disabled,
  id,
}: {
  icon: ReactNode;
  onClick: () => void;
  label: string;
  disabled?: boolean;
  id: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex h-8 w-8 items-center justify-center rounded-md border border-transparent text-slate-600 transition-all hover:border-slate-200 hover:bg-white hover:text-slate-950 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B58B16]/35 disabled:cursor-not-allowed disabled:opacity-30"
      aria-label={label}
      id={id}
    >
      {icon}
    </button>
  );
}
