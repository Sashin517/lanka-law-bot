/**
 * Mediator for draft-chat API calls and atomic editor application.
 *
 * Network responses remain pending suggestions until `applySuggestion` is
 * called. This keeps Ask non-mutating and prevents late AI responses from
 * overwriting a document that the user edited while the request was running.
 */

import {
  editDraft,
  sendLegalQuery,
  type DraftEditPayload,
  type DraftEditResult,
  type LegalQueryPayload,
  type LegalQueryResponse,
  type SourceRef,
} from "@/lib/api";
import {
  documentBuilder,
  type DocumentBuilder,
} from "@/lib/drafting/documentBuilder";
import type { IEditorService } from "@/lib/drafting/editorService";
import type {
  EditHighlightAttrs,
  EditOperation,
  EditorSelection,
  PendingEditSuggestion,
  TiptapDocument,
  TiptapMark,
  TiptapNode,
} from "@/types/drafting";
import { EDIT_HIGHLIGHT_COLORS } from "@/types/drafting";

export interface DraftAskRequest {
  instruction: string;
  selection: EditorSelection | null;
  currentContent: string;
  documentIds: string[];
}

export interface DraftAskResponse {
  content: string;
  sources: SourceRef[];
}

export interface DraftEditRequestContext {
  draftId: string;
  instruction: string;
  selection: EditorSelection | null;
  currentDocument: TiptapDocument;
  currentMarkdown: string;
  documentIds: string[];
}

export interface AppliedDraftEdit {
  document: TiptapDocument;
  markdown: string;
  sources: SourceRef[];
  summary: string;
  editPath: "light" | "heavy";
}

interface ChatEditApi {
  edit(payload: DraftEditPayload): Promise<DraftEditResult>;
  ask(payload: LegalQueryPayload): Promise<LegalQueryResponse>;
}

const defaultApi: ChatEditApi = {
  edit: editDraft,
  ask: sendLegalQuery,
};

export class StaleDraftEditError extends Error {
  constructor() {
    super(
      "This suggestion is stale because the draft changed after the request was sent.",
    );
    this.name = "StaleDraftEditError";
  }
}

export class ChatEditService {
  constructor(
    private readonly api: ChatEditApi = defaultApi,
    private readonly builder: DocumentBuilder = documentBuilder,
  ) {}

  async ask(request: DraftAskRequest): Promise<DraftAskResponse> {
    const response = await this.api.ask({
      question: buildAskQuestion(request),
      mode: "reasoning",
      document_ids:
        request.documentIds.length > 0 ? request.documentIds : undefined,
    });
    const content = response.markdown_content ?? response.answer ?? "";
    if (!content.trim()) {
      throw new Error("The drafting assistant returned an empty answer.");
    }
    return { content, sources: response.sources ?? [] };
  }

  async requestEdit(
    request: DraftEditRequestContext,
  ): Promise<PendingEditSuggestion> {
    const result = await this.api.edit({
      draft_id: request.draftId,
      instruction: request.instruction,
      selected_text: request.selection?.text ?? null,
      selection_start: request.selection?.from ?? null,
      selection_end: request.selection?.to ?? null,
      current_content: request.currentMarkdown,
      document_ids: request.documentIds,
    });

    return {
      result,
      selection: request.selection ? { ...request.selection } : null,
      baseDocument: cloneDocument(request.currentDocument),
      baseMarkdown: request.currentMarkdown,
      createdAt: new Date().toISOString(),
    };
  }

  applySuggestion(
    suggestion: PendingEditSuggestion,
    editor: IEditorService,
    currentSources: SourceRef[],
    versionNumber: number,
  ): AppliedDraftEdit {
    const currentDocument = editor.getDocument();
    if (this.builder.toMarkdown(currentDocument) !== suggestion.baseMarkdown) {
      throw new StaleDraftEditError();
    }

    const sources = mergeSources(currentSources, suggestion.result.sources);
    const highlight = createHighlight(versionNumber);
    const { result, selection } = suggestion;

    if (result.edit_path === "heavy" && result.edit_type === "full_rewrite") {
      const revised = decorateDocument(
        this.builder.fromMarkdown(result.markdown_content, sources),
        highlight,
      );
      editor.setDocument(revised);
    } else if (selection) {
      const replacement = decorateNodes(
        this.builder.parseInline(result.edited_text, sources),
        highlight,
      );
      editor.replaceSelection(selection, replacement);
    } else {
      // The light backend appends insertions when no range is supplied. Replace
      // from its canonical full Markdown and highlight only newly appended blocks.
      const updated = this.builder.fromMarkdown(result.markdown_content, sources);
      const originalBlockCount = suggestion.baseDocument.content.length;
      updated.content = updated.content.map((node, index) =>
        index >= originalBlockCount ? decorateNode(node, highlight) : node,
      );
      editor.setDocument(updated);
    }

    const document = editor.getDocument();
    return {
      document,
      markdown: this.builder.toMarkdown(document),
      sources,
      summary: result.edit_summary,
      editPath: result.edit_path,
    };
  }

  buildOperation(suggestion: PendingEditSuggestion): EditOperation {
    const { result, selection } = suggestion;
    return {
      type:
        result.edit_type === "full_rewrite"
          ? "full_rewrite"
          : result.edit_type === "insert"
            ? "insert_after"
            : "replace",
      targetFrom: selection?.from ?? 0,
      targetTo: selection?.to ?? 0,
      newContent: result.edited_text,
      newContentJson: this.builder.parseInline(
        result.edited_text,
        result.sources,
      ),
      citationsAdded: result.sources.map((source) => source.citation_id),
    };
  }
}

function buildAskQuestion(request: DraftAskRequest): string {
  const selectionContext = request.selection
    ? `## Selected text\n${request.selection.text}\n\n`
    : "";
  const draftExcerpt = request.currentContent.slice(0, 8_000);
  return (
    "DRAFT QUESTION: Answer the user's question without editing the document. " +
    "Ground legal claims with available citations.\n\n" +
    selectionContext +
    `## Current draft context\n${draftExcerpt}\n\n` +
    `## Question\n${request.instruction}`
  );
}

function createHighlight(versionNumber: number): EditHighlightAttrs {
  return {
    editId: crypto.randomUUID(),
    editType: "modification",
    versionNumber,
    timestamp: new Date().toISOString(),
    color: EDIT_HIGHLIGHT_COLORS.modification,
  };
}

function highlightMark(attrs: EditHighlightAttrs): TiptapMark {
  return { type: "editHighlight", attrs: { ...attrs } };
}

export function decorateNode(
  node: TiptapNode,
  attrs: EditHighlightAttrs,
): TiptapNode {
  const next: TiptapNode = {
    ...node,
    attrs: node.attrs ? { ...node.attrs } : undefined,
    marks: node.marks?.map((mark) => ({
      ...mark,
      attrs: mark.attrs ? { ...mark.attrs } : undefined,
    })),
  };
  if (node.type === "text" && node.text) {
    next.marks = [
      ...(next.marks ?? []).filter((mark) => mark.type !== "editHighlight"),
      highlightMark(attrs),
    ];
  }
  if (node.content) {
    next.content = node.content.map((child) => decorateNode(child, attrs));
  }
  return next;
}

export function decorateNodes(
  nodes: TiptapNode[],
  attrs: EditHighlightAttrs,
): TiptapNode[] {
  return nodes.map((node) => decorateNode(node, attrs));
}

export function decorateDocument(
  document: TiptapDocument,
  attrs: EditHighlightAttrs,
): TiptapDocument {
  return {
    type: "doc",
    content: decorateNodes(document.content, attrs),
  };
}

export function mergeSources(
  existing: SourceRef[],
  incoming: SourceRef[],
): SourceRef[] {
  const merged = new Map(existing.map((source) => [source.citation_id, source]));
  incoming.forEach((source) => merged.set(source.citation_id, source));
  return Array.from(merged.values());
}

function cloneDocument(document: TiptapDocument): TiptapDocument {
  return JSON.parse(JSON.stringify(document)) as TiptapDocument;
}

export const chatEditService = new ChatEditService();
