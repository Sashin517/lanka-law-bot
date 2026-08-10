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

import { useCallback, useEffect } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import Placeholder from "@tiptap/extension-placeholder";
import Highlight from "@tiptap/extension-highlight";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";

import { CitationMark } from "./extensions/CitationMark";
import { EditHighlightMark } from "./extensions/EditHighlightMark";
import type { TiptapDocument } from "@/types/drafting";
import type { EditorSelection } from "@/types/drafting";

// ─── Props ──────────────────────────────────────────────────────

export interface TiptapEditorProps {
  /** Initial content as Tiptap JSON (from DocumentBuilder). */
  content?: TiptapDocument | null;
  /** Whether the editor allows editing. */
  editable?: boolean;
  /** Called on every content change (debounced internally by Tiptap). */
  onUpdate?: (json: TiptapDocument, html: string) => void;
  /** Called when the user's text selection changes. */
  onSelectionUpdate?: (selection: EditorSelection | null) => void;
  /** Optional CSS class override for the outer container. */
  className?: string;
}

// ─── Component ──────────────────────────────────────────────────

export function TiptapEditor({
  content,
  editable = true,
  onUpdate,
  onSelectionUpdate,
  className = "",
}: TiptapEditorProps) {
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
          "prose prose-invert prose-sm sm:prose-base max-w-none " +
          "focus:outline-none min-h-full px-12 py-8 " +
          "prose-headings:text-white prose-p:text-slate-200 " +
          "prose-strong:text-white prose-em:text-slate-300 " +
          "prose-blockquote:border-l-[#D4AF37] prose-blockquote:text-slate-300 " +
          "prose-a:text-[#D4AF37] prose-code:text-[#D4AF37] " +
          "prose-li:text-slate-200",
      },
    },
    onUpdate: ({ editor: ed }) => {
      if (onUpdate) {
        const json = ed.getJSON() as TiptapDocument;
        const html = ed.getHTML();
        onUpdate(json, html);
      }
    },
    onSelectionUpdate: ({ editor: ed }) => {
      if (!onSelectionUpdate) return;

      const { from, to, empty } = ed.state.selection;

      if (empty) {
        onSelectionUpdate(null);
        return;
      }

      const text = ed.state.doc.textBetween(from, to, " ");
      // Resolve the parent node type for context
      const $from = ed.state.doc.resolve(from);
      const nodeContext = $from.parent.type.name;

      onSelectionUpdate({ text, from, to, nodeContext });
    },
    // Prevent SSR hydration mismatch
    immediatelyRender: false,
  });

  // Sync external content changes into the editor
  useEffect(() => {
    if (editor && content && !editor.isDestroyed) {
      // Only update if the content is substantially different
      // (prevents cursor jumping on minor store syncs)
      const currentJSON = JSON.stringify(editor.getJSON());
      const newJSON = JSON.stringify(content);
      if (currentJSON !== newJSON) {
        editor.commands.setContent(content);
      }
    }
  }, [editor, content]);

  // Sync editable state
  useEffect(() => {
    if (editor && !editor.isDestroyed) {
      editor.setEditable(editable);
    }
  }, [editor, editable]);

  return (
    <div
      className={`tiptap-editor-wrapper relative h-full overflow-auto bg-white rounded-lg ${className}`}
      id="tiptap-editor-container"
    >
      <EditorContent
        editor={editor}
        className="h-full"
      />
    </div>
  );
}

/**
 * Re-export the editor instance type for consumers that need
 * programmatic access (e.g. ChatEditService).
 */
export type { Editor } from "@tiptap/react";
