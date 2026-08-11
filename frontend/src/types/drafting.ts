/**
 * Drafting Page — Type System
 *
 * Comprehensive types for the Tiptap-based document editing experience.
 * Covers: document model, citations, version tracking, chat editing,
 * diff highlighting, and export options.
 *
 * @module types/drafting
 */

import type { DraftEditResult, SourceRef } from "@/lib/api";

// ─── Tiptap Document Model ─────────────────────────────────────

/** Root Tiptap JSON document structure (mirrors ProseMirror Node). */
export interface TiptapDocument {
  type: "doc";
  content: TiptapNode[];
}

/** A single node in the Tiptap JSON tree. */
export interface TiptapNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: TiptapNode[];
  marks?: TiptapMark[];
  text?: string;
}

/** An inline mark applied to a text node. */
export interface TiptapMark {
  type: string;
  attrs?: Record<string, unknown>;
}

// ─── Citation System ────────────────────────────────────────────

/**
 * Attributes for the custom CitationMark Tiptap extension.
 *
 * Extends the existing {@link SourceRef} from api.ts with fields
 * needed for in-editor citation rendering and hover previews.
 */
export interface CitationMarkAttrs {
  /** Citation anchor, e.g. "[LAW-1]", "[DOC-2]" */
  citationId: string;
  sourceType: "legal_authority" | "user_document";
  title: string;
  section: string | null;
  excerpt: string;
  /** Extended fields from the feature/graph-rag branch */
  pageStart: number | null;
  pageEnd: number | null;
  sourceUri: string | null;
  court: string | null;
  reporterCitation: string | null;
  docketNumber: string | null;
  authoritative: boolean | null;
}

/** Result of resolving a unique in-document citation against source metadata. */
export interface ResolvedCitation {
  citationId: string;
  attrs: CitationMarkAttrs;
  source: SourceRef | null;
  status: "linked" | "unresolved";
  occurrenceCount: number;
  /** Index path to the first text node containing this citation mark. */
  firstDocumentPath: number[];
}

// ─── Version Tracking ───────────────────────────────────────────

/**
 * A single document version snapshot (Memento pattern).
 *
 * Each version stores a full JSON snapshot of the Tiptap document,
 * forming a linked-list via `parentVersionId`.
 */
export interface DocumentVersion {
  id: string;
  versionNumber: number;
  label: string;
  content: TiptapDocument;
  sources: SourceRef[];
  createdAt: string;
  createdBy: "ai" | "user";
  editSummary: string;
  parentVersionId: string | null;
}

/** Result of diffing two document versions. */
export interface VersionDiff {
  fromVersionId: string;
  toVersionId: string;
  changes: DiffChange[];
  summary: string;
}

/** A single change within a version diff. */
export interface DiffChange {
  type: "insert" | "delete" | "replace" | "format_change";
  /** JSON path to the changed node in the document tree. */
  path: string;
  oldContent?: string;
  newContent?: string;
  position: { from: number; to: number };
}

/** Metadata and decorations required for a non-mutating Show Edits overlay. */
export interface DiffOverlay {
  fromVersionId: string;
  toVersionId: string;
  versionNumber: number;
  timestamp: string;
  changes: DiffChange[];
}

// ─── Chat Editing ───────────────────────────────────────────────

/**
 * Represents text selected in the Tiptap editor and sent to the
 * chat panel for AI-assisted editing.
 */
export interface EditorSelection {
  text: string;
  /** ProseMirror position start. */
  from: number;
  /** ProseMirror position end. */
  to: number;
  /** Parent node type for additional context. */
  nodeContext: string;
}

/** A chat message in the drafting context. */
export interface DraftChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  /** The highlighted text this message refers to (if any). */
  selection?: EditorSelection;
  /** Whether the AI edit has been applied to the editor. */
  appliedToEditor: boolean;
  /** The structured edit operation returned by the backend. */
  editOperation?: EditOperation;
  /** Which routing path was used (only for assistant messages). */
  editPath?: "light" | "heavy";
  /** Lifecycle state for informational replies and edit suggestions. */
  status?: ChatMessageStatus;
  /** Sources cited by this individual assistant response. */
  sources?: SourceRef[];
  /** Reviewable AI edit. The document changes only after acceptance. */
  suggestion?: PendingEditSuggestion;
}

export type ChatMessageStatus =
  | "informational"
  | "pending"
  | "applied"
  | "rejected"
  | "stale"
  | "failed";

/** Immutable context captured when an edit request is sent. */
export interface PendingEditSuggestion {
  result: DraftEditResult;
  selection: EditorSelection | null;
  baseDocument: TiptapDocument;
  baseMarkdown: string;
  createdAt: string;
}

/**
 * Structured edit operation from the backend.
 *
 * Describes exactly what content to change and where.
 */
export interface EditOperation {
  type:
    | "replace"
    | "insert_before"
    | "insert_after"
    | "delete"
    | "rewrite_section"
    | "full_rewrite";
  /** Start position in the Tiptap document. */
  targetFrom: number;
  /** End position in the Tiptap document. */
  targetTo: number;
  /** Markdown/text content to insert. */
  newContent: string;
  /** Pre-parsed Tiptap nodes (optional, avoids re-parsing). */
  newContentJson?: TiptapNode[];
  /** New citation anchors introduced by this edit. */
  citationsAdded?: string[];
}

/** Chat operating mode in the drafting panel. */
export type ChatMode = "ask" | "edit";

// ─── Edit Highlighting (Show Edits) ─────────────────────────────

/** Type of edit for diff highlighting marks. */
export type EditHighlightType = "insertion" | "deletion" | "modification";

/** Attributes for the EditHighlightMark Tiptap extension. */
export interface EditHighlightAttrs {
  editId: string;
  editType: EditHighlightType;
  versionNumber: number;
  timestamp: string;
  color: string;
}

/** Color mapping for edit highlight types. */
export const EDIT_HIGHLIGHT_COLORS: Record<EditHighlightType, string> = {
  insertion: "rgba(34, 197, 94, 0.15)",
  deletion: "rgba(239, 68, 68, 0.12)",
  modification: "rgba(214, 176, 93, 0.18)",
} as const;

// ─── Export ─────────────────────────────────────────────────────

export type ExportFormat = "docx" | "pdf";

export interface ExportOptions {
  format: ExportFormat;
  includeMetadata: boolean;
  includeSources: boolean;
  includeDisclaimer: boolean;
  pageSize: "A4" | "Letter";
  margins: {
    top: number;
    bottom: number;
    left: number;
    right: number;
  };
}

/** Default export options for legal documents. */
export const DEFAULT_EXPORT_OPTIONS: ExportOptions = {
  format: "docx",
  includeMetadata: true,
  includeSources: true,
  includeDisclaimer: true,
  pageSize: "A4",
  margins: { top: 72, bottom: 72, left: 72, right: 72 },
} as const;
