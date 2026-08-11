"use client";

import { MessageCircleQuestion, PencilLine } from "lucide-react";

import type { ChatMode, EditorSelection } from "@/types/drafting";

export interface SelectionToolbarProps {
  selection: EditorSelection;
  position: { left: number; top: number };
  onAction: (mode: ChatMode, selection: EditorSelection) => void;
}

export function SelectionToolbar({
  selection,
  position,
  onAction,
}: SelectionToolbarProps) {
  const preserveEditorSelection = (event: React.MouseEvent) => {
    event.preventDefault();
  };

  return (
    <div
      className="absolute z-30 flex -translate-x-1/2 -translate-y-full items-center gap-1 rounded-lg border border-slate-600 bg-[#161B28] p-1 shadow-xl"
      style={{ left: position.left, top: position.top }}
      role="toolbar"
      aria-label="Actions for selected text"
      data-testid="selection-toolbar"
    >
      <button
        type="button"
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-slate-200 transition hover:bg-slate-700"
        onMouseDown={preserveEditorSelection}
        onClick={() => onAction("ask", selection)}
      >
        <MessageCircleQuestion size={13} />
        Ask about this
      </button>
      <span className="h-5 w-px bg-slate-600" aria-hidden="true" />
      <button
        type="button"
        className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-[#D4AF37] transition hover:bg-[#D4AF37]/10"
        onMouseDown={preserveEditorSelection}
        onClick={() => onAction("edit", selection)}
      >
        <PencilLine size={13} />
        Edit this
      </button>
    </div>
  );
}
