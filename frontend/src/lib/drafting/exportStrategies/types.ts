import type { SourceRef } from "@/lib/api";
import type {
  ExportOptions,
  TiptapDocument,
  TiptapNode,
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
  return details.join(", ");
}

/** Return an export-only copy with interactive citation anchors removed. */
export function withoutCitationMarks(
  document: TiptapDocument,
): TiptapDocument {
  return {
    ...document,
    content: stripCitationNodes(document.content),
  };
}

function stripCitationNodes(nodes: TiptapNode[]): TiptapNode[] {
  return nodes.flatMap((node, index) => {
    if (isCitationNode(node)) return [];

    if (
      isCitationSeparator(node) &&
      isCitationNode(nodes[index - 1]) &&
      isCitationNode(nodes[index + 1])
    ) {
      return [];
    }

    return [
      node.content
        ? { ...node, content: stripCitationNodes(node.content) }
        : { ...node },
    ];
  });
}

function isCitationNode(node: TiptapNode | undefined): boolean {
  return Boolean(
    node?.type === "text" &&
      node.marks?.some((mark) => mark.type === "citationMark"),
  );
}

function isCitationSeparator(node: TiptapNode): boolean {
  return node.type === "text" && /^\s*,\s*$/.test(node.text ?? "");
}

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
