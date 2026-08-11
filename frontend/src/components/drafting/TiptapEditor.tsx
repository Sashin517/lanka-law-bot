"use client";

/**
 * TiptapEditor — Rich text editor for legal document drafting.
 *
 * Initializes a Tiptap (ProseMirror-based) editor with:
 * - All standard editing extensions (bold, italic, headings, lists, tables)
 * - Custom CitationMark extension for inline legal citations
 * - Custom EditHighlightMark for diff highlighting
 * - Dark theme styling matching the LankaLawBot design system
 * - onUpdate callback syncing content to the Zustand store
 * - onSelectionUpdate callback for chat integration
 *
 * @module components/drafting/TiptapEditor
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Color from "@tiptap/extension-color";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import Placeholder from "@tiptap/extension-placeholder";
import Highlight from "@tiptap/extension-highlight";
import TextStyle from "@tiptap/extension-text-style";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";

import { CitationMark } from "./extensions/CitationMark";
import { EditHighlightMark } from "./extensions/EditHighlightMark";
import { FontSize } from "./extensions/FontSize";
import { ParagraphFormatting } from "./extensions/ParagraphFormatting";
import { CitationNodeView } from "./extensions/CitationNodeView";
import { SelectionToolbar } from "./SelectionToolbar";
import type { SourceRef } from "@/lib/api";
import { EditorService, type IEditorService } from "@/lib/drafting/editorService";
import type {
  ChatMode,
  EditorSelection,
  TiptapDocument,
} from "@/types/drafting";

// ─── Props ──────────────────────────────────────────────────────

export interface TiptapEditorProps {
  /** Initial content as Tiptap JSON (from DocumentBuilder). */
  content?: TiptapDocument | null;
  /** Whether the editor allows editing. */
  editable?: boolean;
  /** Called after each document-changing editor transaction. */
  onUpdate?: (json: TiptapDocument, html: string) => void;
  /** Called when the user's text selection changes. */
  onSelectionUpdate?: (selection: EditorSelection | null) => void;
  /** Flushes the pending manual-edit batch when focus leaves the editor. */
  onBlur?: () => void;
  /** Exposes the editor facade when the instance is ready. */
  onEditorReady?: (editor: IEditorService | null) => void;
  /** Sends the selected range to the drafting chat composer. */
  onSelectionAction?: (mode: ChatMode, selection: EditorSelection) => void;
  /** Source metadata used by interactive citation previews. */
  sources?: SourceRef[];
  /** Opens the source verification panel at a selected citation. */
  onViewCitationSource?: (citationId: string) => void;
  /** Optional CSS class override for the outer container. */
  className?: string;
}

// ─── Component ──────────────────────────────────────────────────

export function TiptapEditor({
  content,
  editable = true,
  onUpdate,
  onSelectionUpdate,
  onBlur,
  onEditorReady,
  onSelectionAction,
  sources = [],
  onViewCitationSource,
  className = "",
}: TiptapEditorProps) {
  const onUpdateRef = useRef(onUpdate);
  const onSelectionUpdateRef = useRef(onSelectionUpdate);
  const onBlurRef = useRef(onBlur);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [selectionToolbar, setSelectionToolbar] = useState<{
    selection: EditorSelection;
    position: { left: number; top: number };
  } | null>(null);

  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  useEffect(() => {
    onSelectionUpdateRef.current = onSelectionUpdate;
  }, [onSelectionUpdate]);

  useEffect(() => {
    onBlurRef.current = onBlur;
  }, [onBlur]);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        // StarterKit includes: bold, italic, strike, code, heading,
        // bulletList, orderedList, listItem, blockquote, codeBlock,
        // horizontalRule, paragraph, text, hardBreak, history
        heading: {
          levels: [1, 2, 3, 4],
        },
      }),
      Underline,
      TextAlign.configure({
        types: ["heading", "paragraph"],
      }),
      Placeholder.configure({
        placeholder: "Your legal draft will appear here…",
        emptyEditorClass: "is-editor-empty",
      }),
      Highlight.configure({
        multicolor: true,
      }),
      TextStyle,
      FontSize,
      Color,
      ParagraphFormatting,
      // Table support for legal document tables
      Table.configure({
        resizable: true,
        HTMLAttributes: {
          class: "tiptap-table",
        },
      }),
      TableRow,
      TableCell,
      TableHeader,
      // Custom extensions
      CitationMark,
      EditHighlightMark,
    ],
    content: content ?? { type: "doc", content: [{ type: "paragraph" }] },
    editable,
    editorProps: {
      attributes: {
        class:
          "prose prose-slate prose-sm sm:prose-base max-w-none " +
          "focus:outline-none min-h-full px-12 py-8 " +
          "prose-headings:text-slate-950 prose-p:text-slate-800 " +
          "prose-strong:text-slate-950 prose-em:text-slate-700 " +
          "prose-blockquote:border-l-[#B58B16] prose-blockquote:text-slate-600 " +
          "prose-a:text-[#8A6910] prose-code:text-[#7A5B0A] " +
          "prose-li:text-slate-800",
      },
    },
    onUpdate: ({ editor: ed }) => {
      if (onUpdateRef.current) {
        onUpdateRef.current(
          ed.getJSON() as TiptapDocument,
          ed.getHTML(),
        );
      }
    },
    onSelectionUpdate: ({ editor: ed }) => {
      const { from, to, empty } = ed.state.selection;

      if (empty) {
        setSelectionToolbar(null);
        onSelectionUpdateRef.current?.(null);
        return;
      }

      const text = ed.state.doc.textBetween(from, to, " ");
      // Resolve the parent node type for context
      const $from = ed.state.doc.resolve(from);
      const nodeContext = $from.parent.type.name;

      const selection = { text, from, to, nodeContext };
      onSelectionUpdateRef.current?.(selection);

      const wrapper = wrapperRef.current;
      if (wrapper && text.trim()) {
        const start = ed.view.coordsAtPos(from);
        const end = ed.view.coordsAtPos(to);
        const bounds = wrapper.getBoundingClientRect();
        setSelectionToolbar({
          selection,
          position: {
            left:
              (start.left + end.right) / 2 -
              bounds.left +
              wrapper.scrollLeft,
            top:
              Math.min(start.top, end.top) -
              bounds.top +
              wrapper.scrollTop -
              8,
          },
        });
      } else {
        setSelectionToolbar(null);
      }
    },
    onBlur: () => {
      setSelectionToolbar(null);
      onBlurRef.current?.();
    },
    // Prevent SSR hydration mismatch
    immediatelyRender: false,
  });

  const editorService = useMemo(
    () => (editor ? new EditorService(editor) : null),
    [editor],
  );

  useEffect(() => {
    onEditorReady?.(editorService);
    return () => onEditorReady?.(null);
  }, [editorService, onEditorReady]);

  // Sync external content changes into the editor
  useEffect(() => {
    if (editorService && content && !editorService.getEditor().isDestroyed) {
      // Only update if the content is substantially different
      // (prevents cursor jumping on minor store syncs)
      const currentJSON = JSON.stringify(editorService.getDocument());
      const newJSON = JSON.stringify(content);
      if (currentJSON !== newJSON) {
        editorService.setDocument(content);
      }
    }
  }, [editorService, content]);

  // Sync editable state
  useEffect(() => {
    if (editorService && !editorService.getEditor().isDestroyed) {
      editorService.setEditable(editable);
    }
  }, [editorService, editable]);

  return (
    <div
      ref={wrapperRef}
      className={`tiptap-editor-wrapper relative h-full overflow-auto rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}
      id="tiptap-editor-container"
    >
      <EditorContent
        editor={editor}
        className="h-full"
      />
      {editor && (
        <CitationNodeView
          editor={editor}
          sources={sources}
          onViewInSources={onViewCitationSource}
        />
      )}
      {editable && selectionToolbar && onSelectionAction && (
        <SelectionToolbar
          selection={selectionToolbar.selection}
          position={selectionToolbar.position}
          onAction={onSelectionAction}
        />
      )}
    </div>
  );
}

/**
 * Re-export the editor instance type for consumers that need
 * programmatic access (e.g. ChatEditService).
 */
export type { Editor } from "@tiptap/react";
