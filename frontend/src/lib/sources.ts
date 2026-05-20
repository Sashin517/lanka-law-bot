import type { SourceRef } from "@/lib/api";

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
