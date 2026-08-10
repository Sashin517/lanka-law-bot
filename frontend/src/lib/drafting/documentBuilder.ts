/**
 * DocumentBuilder — Adapter converting backend markdown into Tiptap JSON.
 *
 * Converts the markdown response (with [LAW-*] / [DOC-*] citation
 * anchors) from the LangGraph pipeline into a structured Tiptap JSON
 * document (`TiptapDocument`) ready for the editor.
 *
 * Design Pattern: Builder pattern with a fluent API.
 *
 * The builder also exposes `parseInline()` for chat-edit responses
 * where only a text fragment (not a full document) needs to be parsed.
 *
 * @module lib/drafting/documentBuilder
 */

import type { SourceRef } from "@/lib/api";
import {
  buildSourcesById,
  citationIdsFromGroup,
  CITATION_RE,
} from "@/lib/sources";
import type { TiptapDocument, TiptapNode, TiptapMark } from "@/types/drafting";

// ─── Inline Parsing ─────────────────────────────────────────────

/**
 * Parse inline text into an array of Tiptap text nodes,
 * converting [LAW-*]/[DOC-*] anchors into CitationMark marks.
 */
function parseInlineText(
  text: string,
  sourceMap: Map<string, SourceRef>,
  baseMarks: TiptapMark[] = [],
): TiptapNode[] {
  const nodes: TiptapNode[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(CITATION_RE)) {
    const start = match.index!;

    // Text before the citation
    if (start > lastIndex) {
      const segment = text.slice(lastIndex, start);
      if (segment) {
        nodes.push({
          type: "text",
          text: segment,
          ...(baseMarks.length > 0 ? { marks: [...baseMarks] } : {}),
        });
      }
    }

    citationIdsFromGroup(match[0]).forEach((citationId, groupIndex) => {
      if (groupIndex > 0) {
        nodes.push({ type: "text", text: ", " });
      }
      const source = sourceMap.get(citationId);
      const isDoc = citationId.startsWith("[DOC");
      const citationMark: TiptapMark = {
        type: "citationMark",
        attrs: {
          citationId,
          sourceType: isDoc ? "user_document" : "legal_authority",
          title: source?.title ?? citationId,
          section: source?.section ?? null,
          excerpt: source?.excerpt ?? "",
          pageStart: source?.page_start ?? null,
          pageEnd: source?.page_end ?? null,
          sourceUri: source?.source_uri ?? null,
          court: source?.court ?? null,
          reporterCitation: source?.reporter_citation ?? null,
          docketNumber: source?.docket_number ?? null,
          authoritative: source?.authoritative ?? null,
        },
      };

      nodes.push({
        type: "text",
        text: citationId,
        marks: [...baseMarks, citationMark],
      });
    });

    lastIndex = start + match[0].length;
  }

  // Remaining text after the last citation
  if (lastIndex < text.length) {
    const segment = text.slice(lastIndex);
    if (segment) {
      nodes.push({
        type: "text",
        text: segment,
        ...(baseMarks.length > 0 ? { marks: [...baseMarks] } : {}),
      });
    }
  }

  // If no citations found, return the full text as a single node
  if (nodes.length === 0 && text) {
    nodes.push({
      type: "text",
      text,
      ...(baseMarks.length > 0 ? { marks: [...baseMarks] } : {}),
    });
  }

  return nodes;
}

// ─── Block Parsing ──────────────────────────────────────────────

/** Detect heading level from markdown heading syntax (## etc.) */
function parseHeading(
  line: string,
): { level: number; text: string } | null {
  const match = line.match(/^(#{1,6})\s+(.+)$/);
  if (!match) return null;
  return { level: match[1].length, text: match[2] };
}

/** Detect unordered list item. */
function isUnorderedListItem(line: string): string | null {
  const match = line.match(/^[\s]*[-*+]\s+(.+)$/);
  return match ? match[1] : null;
}

/** Detect ordered list item. */
function isOrderedListItem(line: string): string | null {
  const match = line.match(/^[\s]*\d+\.\s+(.+)$/);
  return match ? match[1] : null;
}

/** Detect blockquote. */
function isBlockquote(line: string): string | null {
  const match = line.match(/^>\s?(.*)$/);
  return match ? match[1] : null;
}

/** Detect horizontal rule. */
function isHorizontalRule(line: string): boolean {
  return /^---+$|^\*\*\*+$|^___+$/.test(line.trim());
}

/**
 * Parse bold/italic inline markdown into Tiptap marks.
 * Handles **bold**, *italic*, ***bold+italic***, __bold__, _italic_.
 */
function parseInlineFormatting(
  text: string,
  sourceMap: Map<string, SourceRef>,
): TiptapNode[] {
  const parts: TiptapNode[] = [];
  const formatRe = /(\*\*\*|___)(.+?)\1|\*\*(.+?)\*\*|__(.+?)__|\*([^*]+?)\*|_([^_]+?)_/g;
  let lastIndex = 0;

  for (const match of text.matchAll(formatRe)) {
    const start = match.index ?? 0;
    if (start > lastIndex) {
      parts.push(...parseInlineText(text.slice(lastIndex, start), sourceMap));
    }

    const isBoldItalic = Boolean(match[1]);
    const segment = match[2] ?? match[3] ?? match[4] ?? match[5] ?? match[6] ?? "";
    const marks: TiptapMark[] = [];
    if (isBoldItalic || match[3] !== undefined || match[4] !== undefined) {
      marks.push({ type: "bold" });
    }
    if (isBoldItalic || match[5] !== undefined || match[6] !== undefined) {
      marks.push({ type: "italic" });
    }
    parts.push(...parseInlineText(segment, sourceMap, marks));
    lastIndex = start + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(...parseInlineText(text.slice(lastIndex), sourceMap));
  }

  return parts.length > 0 ? parts : parseInlineText(text, sourceMap);
}

function textFromNode(node: TiptapNode): string {
  if (node.type === "hardBreak") return "\n";
  if (node.type !== "text") {
    return (node.content ?? []).map(textFromNode).join("");
  }

  let text = node.text ?? "";
  const marks = node.marks ?? [];

  if (marks.some((mark) => mark.type === "citationMark")) {
    return text;
  }
  if (marks.some((mark) => mark.type === "code")) text = `\`${text}\``;
  if (marks.some((mark) => mark.type === "bold")) text = `**${text}**`;
  if (marks.some((mark) => mark.type === "italic")) text = `*${text}*`;
  if (marks.some((mark) => mark.type === "strike")) text = `~~${text}~~`;
  if (marks.some((mark) => mark.type === "underline")) text = `<u>${text}</u>`;

  return text;
}

function serializeListItem(node: TiptapNode, marker: string): string {
  const children = node.content ?? [];
  const firstBlock = children[0];
  const firstLine = firstBlock ? textFromNode(firstBlock) : "";
  const nested = children
    .slice(1)
    .map((child) => serializeBlock(child))
    .filter(Boolean)
    .map((value) => value.split("\n").map((line) => `  ${line}`).join("\n"));

  return [`${marker} ${firstLine}`, ...nested].join("\n");
}

function serializeTable(node: TiptapNode): string {
  const rows = (node.content ?? []).map((row) =>
    (row.content ?? []).map((cell) => textFromNode(cell).replace(/\|/g, "\\|").trim()),
  );
  if (rows.length === 0) return "";

  const columnCount = Math.max(...rows.map((row) => row.length), 1);
  const normalizeRow = (row: string[]) =>
    `| ${Array.from({ length: columnCount }, (_, index) => row[index] ?? "").join(" | ")} |`;
  const [header, ...body] = rows;
  return [
    normalizeRow(header),
    normalizeRow(Array.from({ length: columnCount }, () => "---")),
    ...body.map(normalizeRow),
  ].join("\n");
}

function serializeBlock(node: TiptapNode): string {
  switch (node.type) {
    case "heading": {
      const rawLevel = Number(node.attrs?.level ?? 1);
      const level = Math.min(Math.max(rawLevel, 1), 6);
      return `${"#".repeat(level)} ${textFromNode(node)}`;
    }
    case "paragraph":
      return textFromNode(node);
    case "blockquote":
      return (node.content ?? [])
        .map(serializeBlock)
        .join("\n\n")
        .split("\n")
        .map((line) => `> ${line}`)
        .join("\n");
    case "bulletList":
      return (node.content ?? [])
        .map((item) => serializeListItem(item, "-"))
        .join("\n");
    case "orderedList":
      return (node.content ?? [])
        .map((item, index) => serializeListItem(item, `${index + 1}.`))
        .join("\n");
    case "horizontalRule":
      return "---";
    case "codeBlock": {
      const language = String(node.attrs?.language ?? "");
      return `\`\`\`${language}\n${textFromNode(node)}\n\`\`\``;
    }
    case "table":
      return serializeTable(node);
    default:
      return textFromNode(node);
  }
}

// ─── DocumentBuilder Class ──────────────────────────────────────

export class DocumentBuilder {
  private doc: TiptapDocument = { type: "doc", content: [] };
  private sourceMap: Map<string, SourceRef> = new Map();

  /**
   * Convert a full markdown string into a Tiptap JSON document.
   *
   * This is the primary entry point — called when the initial draft
   * is received from the backend.
   */
  fromMarkdown(markdown: string, sources: SourceRef[]): TiptapDocument {
    this.doc = { type: "doc", content: [] };
    this.sourceMap = buildSourcesById(sources);

    if (!markdown.trim()) {
      // Return empty doc with a single empty paragraph
      this.doc.content.push({ type: "paragraph" });
      return this.doc;
    }

    const lines = markdown.split("\n");
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      // Skip empty lines
      if (!trimmed) {
        i++;
        continue;
      }

      // Horizontal rule
      if (isHorizontalRule(trimmed)) {
        this.doc.content.push({ type: "horizontalRule" });
        i++;
        continue;
      }

      // Heading
      const heading = parseHeading(trimmed);
      if (heading) {
        this.addHeading(heading.level, heading.text);
        i++;
        continue;
      }

      // Blockquote (collect consecutive lines)
      const bqText = isBlockquote(trimmed);
      if (bqText !== null) {
        const bqLines: string[] = [bqText];
        i++;
        while (i < lines.length) {
          const nextBq = isBlockquote(lines[i].trim());
          if (nextBq !== null) {
            bqLines.push(nextBq);
            i++;
          } else {
            break;
          }
        }
        this.addBlockquote(bqLines.join("\n"));
        continue;
      }

      // Unordered list (collect consecutive items)
      const ulItem = isUnorderedListItem(trimmed);
      if (ulItem !== null) {
        const items: string[] = [ulItem];
        i++;
        while (i < lines.length) {
          const nextItem = isUnorderedListItem(lines[i].trim());
          if (nextItem !== null) {
            items.push(nextItem);
            i++;
          } else {
            break;
          }
        }
        this.addBulletList(items);
        continue;
      }

      // Ordered list (collect consecutive items)
      const olItem = isOrderedListItem(trimmed);
      if (olItem !== null) {
        const items: string[] = [olItem];
        i++;
        while (i < lines.length) {
          const nextItem = isOrderedListItem(lines[i].trim());
          if (nextItem !== null) {
            items.push(nextItem);
            i++;
          } else {
            break;
          }
        }
        this.addOrderedList(items);
        continue;
      }

      // Default: paragraph
      this.addParagraph(trimmed);
      i++;
    }

    // Ensure we always have at least one node
    if (this.doc.content.length === 0) {
      this.doc.content.push({ type: "paragraph" });
    }

    return this.doc;
  }

  /**
   * Parse a text fragment into Tiptap inline content nodes.
   *
   * Used by ChatEditService for light-path edit responses where
   * only a text fragment (not a full document) needs to be parsed.
   */
  parseInline(text: string, sources: SourceRef[]): TiptapNode[] {
    const sourceMap = buildSourcesById(sources);
    return parseInlineFormatting(text, sourceMap);
  }

  /** Serialize the editable Tiptap tree back to Markdown for API requests. */
  toMarkdown(document: TiptapDocument): string {
    return document.content.map(serializeBlock).join("\n\n").trim();
  }

  // ─── Fluent Builder Methods ─────────────────────────────────

  addHeading(level: number, text: string): this {
    const content = parseInlineFormatting(text, this.sourceMap);
    this.doc.content.push({
      type: "heading",
      attrs: { level },
      content,
    });
    return this;
  }

  addParagraph(text: string): this {
    const content = parseInlineFormatting(text, this.sourceMap);
    this.doc.content.push({
      type: "paragraph",
      content,
    });
    return this;
  }

  addBlockquote(text: string): this {
    const paragraphContent = parseInlineFormatting(text, this.sourceMap);
    this.doc.content.push({
      type: "blockquote",
      content: [
        {
          type: "paragraph",
          content: paragraphContent,
        },
      ],
    });
    return this;
  }

  addBulletList(items: string[]): this {
    this.doc.content.push({
      type: "bulletList",
      content: items.map((item) => ({
        type: "listItem",
        content: [
          {
            type: "paragraph",
            content: parseInlineFormatting(item, this.sourceMap),
          },
        ],
      })),
    });
    return this;
  }

  addOrderedList(items: string[]): this {
    this.doc.content.push({
      type: "orderedList",
      content: items.map((item) => ({
        type: "listItem",
        content: [
          {
            type: "paragraph",
            content: parseInlineFormatting(item, this.sourceMap),
          },
        ],
      })),
    });
    return this;
  }

  build(): TiptapDocument {
    return this.doc;
  }
}

/**
 * Module-level singleton instance.
 *
 * Use this for direct calls without instantiation:
 *   import { documentBuilder } from "@/lib/drafting/documentBuilder";
 *   const json = documentBuilder.fromMarkdown(md, sources);
 */
export const documentBuilder = new DocumentBuilder();
