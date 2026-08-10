/**
 * Focused facade over the Tiptap editor API.
 *
 * Components depend on this small contract instead of reaching into
 * ProseMirror state and transactions directly.
 */

import type { Editor } from "@tiptap/core";

import type { EditorSelection, TiptapDocument } from "@/types/drafting";

export interface IEditorService {
  getDocument(): TiptapDocument;
  getHtml(): string;
  getSelection(): EditorSelection | null;
  setDocument(document: TiptapDocument, emitUpdate?: boolean): void;
  setEditable(editable: boolean): void;
  focus(): void;
  getEditor(): Editor;
}

export class EditorService implements IEditorService {
  constructor(private readonly editor: Editor) {}

  getDocument(): TiptapDocument {
    return this.editor.getJSON() as TiptapDocument;
  }

  getHtml(): string {
    return this.editor.getHTML();
  }

  getSelection(): EditorSelection | null {
    const { from, to, empty } = this.editor.state.selection;
    if (empty) return null;

    return {
      from,
      to,
      text: this.editor.state.doc.textBetween(from, to, " "),
      nodeContext: this.editor.state.doc.resolve(from).parent.type.name,
    };
  }

  setDocument(document: TiptapDocument, emitUpdate = false): void {
    this.editor.commands.setContent(document, emitUpdate);
  }

  setEditable(editable: boolean): void {
    this.editor.setEditable(editable);
  }

  focus(): void {
    this.editor.commands.focus();
  }

  getEditor(): Editor {
    return this.editor;
  }
}
