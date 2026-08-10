/**
 * CitationService — extracts and resolves citation marks in a Tiptap tree.
 *
 * A single depth-first traversal visits every node once. Source metadata is
 * indexed once in a Map, producing O(N + S) time and O(C + S) auxiliary
 * space for N document nodes, S sources, and C unique citations.
 */

import type { SourceRef } from "@/lib/api";
import type {
  CitationMarkAttrs,
  ResolvedCitation,
  TiptapDocument,
  TiptapMark,
  TiptapNode,
} from "@/types/drafting";

const CITATION_MARK_NAME = "citationMark";
const CANONICAL_CITATION_RE = /^\[(?:LAW|DOC)-\d+\]$/;

export interface ICitationService {
  resolveCitations(
    document: TiptapDocument | null,
    sources: SourceRef[],
  ): ResolvedCitation[];
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function optionalBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

function inferSourceType(
  citationId: string,
  configuredType: unknown,
): CitationMarkAttrs["sourceType"] {
  if (configuredType === "user_document") return "user_document";
  if (configuredType === "legal_authority") return "legal_authority";
  return citationId.startsWith("[DOC-")
    ? "user_document"
    : "legal_authority";
}

function citationIdFrom(mark: TiptapMark, node: TiptapNode): string | null {
  const configuredId = optionalString(mark.attrs?.citationId);
  if (configuredId && CANONICAL_CITATION_RE.test(configuredId)) {
    return configuredId;
  }

  const text = node.text?.trim() ?? "";
  return CANONICAL_CITATION_RE.test(text) ? text : null;
}

function normalizeAttrs(
  mark: TiptapMark,
  node: TiptapNode,
): CitationMarkAttrs | null {
  const citationId = citationIdFrom(mark, node);
  if (!citationId) return null;
  const attrs = mark.attrs ?? {};

  return {
    citationId,
    sourceType: inferSourceType(citationId, attrs.sourceType),
    title: optionalString(attrs.title) ?? citationId,
    section: optionalString(attrs.section),
    excerpt: optionalString(attrs.excerpt) ?? "",
    pageStart: optionalNumber(attrs.pageStart),
    pageEnd: optionalNumber(attrs.pageEnd),
    sourceUri: optionalString(attrs.sourceUri),
    court: optionalString(attrs.court),
    reporterCitation: optionalString(attrs.reporterCitation),
    docketNumber: optionalString(attrs.docketNumber),
    authoritative: optionalBoolean(attrs.authoritative),
  };
}

interface CitationAccumulator {
  attrs: CitationMarkAttrs;
  occurrenceCount: number;
  firstDocumentPath: number[];
}

export class CitationService implements ICitationService {
  resolveCitations(
    document: TiptapDocument | null,
    sources: SourceRef[],
  ): ResolvedCitation[] {
    if (!document) return [];

    const sourceIndex = new Map(
      sources.map((source) => [source.citation_id, source]),
    );
    const citationIndex = new Map<string, CitationAccumulator>();

    this.visit(document.content, [], citationIndex);

    return Array.from(citationIndex.entries()).map(
      ([citationId, citation]) => {
        const source = sourceIndex.get(citationId) ?? null;
        return {
          citationId,
          attrs: citation.attrs,
          source,
          status: source ? "linked" : "unresolved",
          occurrenceCount: citation.occurrenceCount,
          firstDocumentPath: citation.firstDocumentPath,
        };
      },
    );
  }

  private visit(
    nodes: TiptapNode[],
    parentPath: number[],
    citations: Map<string, CitationAccumulator>,
  ): void {
    nodes.forEach((node, index) => {
      const path = [...parentPath, index];

      for (const mark of node.marks ?? []) {
        if (mark.type !== CITATION_MARK_NAME) continue;
        const attrs = normalizeAttrs(mark, node);
        if (!attrs) continue;

        const existing = citations.get(attrs.citationId);
        if (existing) {
          existing.occurrenceCount += 1;
        } else {
          citations.set(attrs.citationId, {
            attrs,
            occurrenceCount: 1,
            firstDocumentPath: path,
          });
        }
      }

      if (node.content?.length) {
        this.visit(node.content, path, citations);
      }
    });
  }
}

export const citationService = new CitationService();
