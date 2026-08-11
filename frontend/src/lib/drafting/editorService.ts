/**
 * Focused facade over the Tiptap editor API.
 *
 * Components depend on this small contract instead of reaching into
 * ProseMirror state and transactions directly.
 */

import type { Editor } from "@tiptap/core";

import type {
  DiffOverlay,
  EditorSelection,
  TiptapDocument,
  TiptapNode,
} from "@/types/drafting";
import {
  DEFAULT_FONT_SIZE,
  DEFAULT_LINE_SPACING,
  DEFAULT_PARAGRAPH_SPACING,
  HEADING_LEVELS,
  isAllowedFontSize,
  isAllowedLineSpacing,
  isAllowedParagraphSpacing,
  isTextAlignment,
  normalizeAlignment,
  normalizeFontSize,
  normalizeIndentLevel,
  normalizeLineSpacing,
  normalizeParagraphSpacing,
  type BlockType,
  type EditorFormattingState,
  type FontSize,
  type InlineFormat,
  type LineSpacing,
  type ParagraphSpacing,
  type TextAlignment,
} from "@/lib/drafting/formatting";

export class StaleEditorSelectionError extends Error {
  constructor(message = "The selected text has changed since this edit was requested.") {
    super(message);
    this.name = "StaleEditorSelectionError";
  }
}

export interface IEditorService {
  getDocument(): TiptapDocument;
  getHtml(): string;
  getSelection(): EditorSelection | null;
  setDocument(document: TiptapDocument, emitUpdate?: boolean): void;
  replaceSelection(selection: EditorSelection, content: TiptapNode[]): void;
  showDiffOverlay(overlay: DiffOverlay): void;
  clearDiffOverlay(): void;
  setEditable(editable: boolean): void;
  getFormattingState(): EditorFormattingState;
  subscribeToFormatting(listener: (state: EditorFormattingState) => void): () => void;
  setBlockType(blockType: BlockType): boolean;
  toggleInlineFormat(format: InlineFormat): boolean;
  setFontSize(size: FontSize): boolean;
  setTextAlignment(alignment: TextAlignment): boolean;
  setIndentLevel(level: number): boolean;
  setLineSpacing(spacing: LineSpacing): boolean;
  setParagraphSpacingBefore(spacing: ParagraphSpacing): boolean;
  setParagraphSpacingAfter(spacing: ParagraphSpacing): boolean;
  undo(): boolean;
  redo(): boolean;
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

  replaceSelection(selection: EditorSelection, content: TiptapNode[]): void {
    const { from, to, text } = selection;
    const currentText = this.editor.state.doc.textBetween(from, to, " ");
    if (currentText !== text) {
      throw new StaleEditorSelectionError();
    }

    const applied = this.editor
      .chain()
      .focus()
      .insertContentAt({ from, to }, content)
      .run();
    if (!applied) {
      throw new Error("The editor rejected the requested replacement.");
    }
  }

  showDiffOverlay(overlay: DiffOverlay): void {
    this.editor.commands.showDiffOverlay(overlay);
  }

  clearDiffOverlay(): void {
    this.editor.commands.clearDiffOverlay();
  }

  setEditable(editable: boolean): void {
    this.editor.setEditable(editable);
  }

  getFormattingState(): EditorFormattingState {
    const headingLevel = HEADING_LEVELS.find((level) =>
      this.editor.isActive("heading", { level }),
    );
    const blockName = headingLevel ? "heading" : "paragraph";
    const blockAttributes = this.editor.getAttributes(blockName);
    const textStyleAttributes = this.editor.getAttributes("textStyle");

    return {
      blockType: headingLevel ? `heading-${headingLevel}` : "paragraph",
      fontSize: normalizeFontSize(
        textStyleAttributes.fontSize ?? DEFAULT_FONT_SIZE,
      ),
      alignment: normalizeAlignment(blockAttributes.textAlign),
      indentLevel: normalizeIndentLevel(blockAttributes.indentLevel),
      lineSpacing: normalizeLineSpacing(
        blockAttributes.lineSpacing ?? DEFAULT_LINE_SPACING,
      ),
      spacingBefore: normalizeParagraphSpacing(
        blockAttributes.spacingBefore ?? DEFAULT_PARAGRAPH_SPACING,
      ),
      spacingAfter: normalizeParagraphSpacing(
        blockAttributes.spacingAfter ?? DEFAULT_PARAGRAPH_SPACING,
      ),
      bold: this.editor.isActive("bold"),
      italic: this.editor.isActive("italic"),
      underline: this.editor.isActive("underline"),
      strike: this.editor.isActive("strike"),
      canUndo: this.editor.can().undo(),
      canRedo: this.editor.can().redo(),
    };
  }

  subscribeToFormatting(
    listener: (state: EditorFormattingState) => void,
  ): () => void {
    const notify = () => listener(this.getFormattingState());
    this.editor.on("transaction", notify);
    notify();
    return () => {
      this.editor.off("transaction", notify);
    };
  }

  setBlockType(blockType: BlockType): boolean {
    const chain = this.editor.chain().focus();
    if (blockType === "paragraph") return chain.setParagraph().run();

    const level = Number(blockType.replace("heading-", ""));
    if (!HEADING_LEVELS.includes(level as (typeof HEADING_LEVELS)[number])) {
      throw new RangeError(`Unsupported heading level: ${blockType}`);
    }
    return chain
      .setHeading({ level: level as (typeof HEADING_LEVELS)[number] })
      .run();
  }

  toggleInlineFormat(format: InlineFormat): boolean {
    const chain = this.editor.chain().focus();
    switch (format) {
      case "bold":
        return chain.toggleBold().run();
      case "italic":
        return chain.toggleItalic().run();
      case "underline":
        return chain.toggleUnderline().run();
      case "strike":
        return chain.toggleStrike().run();
    }
  }

  setFontSize(size: FontSize): boolean {
    if (!isAllowedFontSize(size)) throw new RangeError("Unsupported font size.");
    return this.editor
      .chain()
      .focus()
      .setMark("textStyle", { fontSize: size })
      .run();
  }

  setTextAlignment(alignment: TextAlignment): boolean {
    if (!isTextAlignment(alignment)) {
      throw new RangeError("Unsupported text alignment.");
    }
    return this.editor.chain().focus().setTextAlign(alignment).run();
  }

  setIndentLevel(level: number): boolean {
    return this.updateBlockAttributes({ indentLevel: normalizeIndentLevel(level) });
  }

  setLineSpacing(spacing: LineSpacing): boolean {
    if (!isAllowedLineSpacing(spacing)) {
      throw new RangeError("Unsupported line spacing.");
    }
    return this.updateBlockAttributes({ lineSpacing: spacing });
  }

  setParagraphSpacingBefore(spacing: ParagraphSpacing): boolean {
    if (!isAllowedParagraphSpacing(spacing)) {
      throw new RangeError("Unsupported paragraph spacing.");
    }
    return this.updateBlockAttributes({ spacingBefore: spacing });
  }

  setParagraphSpacingAfter(spacing: ParagraphSpacing): boolean {
    if (!isAllowedParagraphSpacing(spacing)) {
      throw new RangeError("Unsupported paragraph spacing.");
    }
    return this.updateBlockAttributes({ spacingAfter: spacing });
  }

  undo(): boolean {
    return this.editor.chain().focus().undo().run();
  }

  redo(): boolean {
    return this.editor.chain().focus().redo().run();
  }

  focus(): void {
    this.editor.commands.focus();
  }

  getEditor(): Editor {
    return this.editor;
  }

  private updateBlockAttributes(attributes: Record<string, unknown>): boolean {
    return this.editor
      .chain()
      .focus()
      .updateAttributes("paragraph", attributes)
      .updateAttributes("heading", attributes)
      .run();
  }
}
