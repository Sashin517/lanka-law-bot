import type { SourceRef } from "@/lib/api";

/** Matches single or grouped backend anchors, e.g. [LAW-1, LAW-3]. */
export const CITATION_RE =
  /\[(?:(?:LAW|DOC)-\d+)(?:\s*,\s*(?:LAW|DOC)-\d+)*\]/g;

const CITATION_TOKEN_RE = /(?:LAW|DOC)-\d+/g;

/** Convert a matched group into canonical individual IDs with brackets. */
export function citationIdsFromGroup(group: string): string[] {
  return Array.from(group.matchAll(CITATION_TOKEN_RE), (match) => `[${match[0]}]`);
}

/** Build a lookup map from citation_id (e.g. "[LAW-1]") to source metadata. */
export function buildSourcesById(
  sources: SourceRef[],
): Map<string, SourceRef> {
  return new Map(sources.map((s) => [s.citation_id, s]));
}

/** HTML-safe id for a source card in the Sources panel. */
export function sourceCardId(messageId: string, citationId: string): string {
  const slug = citationId.replace(/[[\]]/g, "");
  return `source-${messageId}-${slug}`;
}
