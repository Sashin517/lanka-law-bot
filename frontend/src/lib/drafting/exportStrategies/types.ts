import type { SourceRef } from "@/lib/api";
import type {
  ExportOptions,
  TiptapDocument,
} from "@/types/drafting";

export interface ExportMetadata {
  title: string;
  author: string;
  date: string;
  versionNumber: number;
}

export interface IExportStrategy {
  export(
    document: TiptapDocument,
    sources: SourceRef[],
    options: ExportOptions,
    metadata: ExportMetadata,
  ): Promise<Blob>;
}

export const LEGAL_DISCLAIMER =
  "This AI-assisted draft is provided for informational purposes and must be reviewed by a qualified legal professional before use. Verify all authorities, citations, facts, deadlines, and procedural requirements against current official sources.";

export function formatSource(source: SourceRef): string {
  const details = [
    source.title,
    source.section,
    source.year ? String(source.year) : null,
    source.reporter_citation,
    source.court,
    source.page_start
      ? `p. ${source.page_start}${
          source.page_end && source.page_end !== source.page_start
            ? `-${source.page_end}`
            : ""
        }`
      : null,
  ].filter(Boolean);
  return `${source.citation_id} ${details.join(", ")}`;
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
