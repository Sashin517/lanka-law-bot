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
import type { TiptapDocument, TiptapNode, TiptapMark } from "@/types/drafting";

// ─── Citation Regex (mirrors MarkdownRenderer.tsx) ──────────────

/** Matches [LAW-1], [DOC-2], etc. — same regex used by MarkdownRenderer. */
const CITATION_RE = /\[(?:LAW|DOC)-\d+\]/g;

// ─── Source Lookup Helper ───────────────────────────────────────

function buildSourceMap(sources: SourceRef[]): Map<string, SourceRef> {
  return new Map(sources.map((s) => [s.citation_id, s]));
}

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

    // The citation itself
    const citationId = match[0];
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
      },
    };

    nodes.push({
      type: "text",
      text: citationId,
      marks: [...baseMarks, citationMark],
    });

    lastIndex = start + citationId.length;
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
  // Handle bold (**text** or __text__)
  const boldRe = /\*\*(.+?)\*\*|__(.+?)__/g;
  const parts: TiptapNode[] = [];
  let remaining = text;
  let match: RegExpExecArray | null;

  // Simple two-pass approach: bold first, then italic
  const segments: Array<{ text: string; bold: boolean; italic: boolean }> = [];
  let lastIdx = 0;

  // Extract bold segments
  const boldMatches = [...remaining.matchAll(boldRe)];
  if (boldMatches.length === 0) {
    // No bold — check for italic
    const italicRe = /\*(.+?)\*|_(.+?)_/g;
    const italicMatches = [...remaining.matchAll(italicRe)];
    if (italicMatches.length === 0) {
      return parseInlineText(text, sourceMap);
    }

    for (const im of italicMatches) {
      const start = im.index!;
      if (start > lastIdx) {
        segments.push({ text: remaining.slice(lastIdx, start), bold: false, italic: false });
      }
      segments.push({ text: im[1] ?? im[2], bold: false, italic: true });
      lastIdx = start + im[0].length;
    }
    if (lastIdx < remaining.length) {
      segments.push({ text: remaining.slice(lastIdx), bold: false, italic: false });
    }
  } else {
    for (const bm of boldMatches) {
      const start = bm.index!;
      if (start > lastIdx) {
        segments.push({ text: remaining.slice(lastIdx, start), bold: false, italic: false });
      }
      segments.push({ text: bm[1] ?? bm[2], bold: true, italic: false });
      lastIdx = start + bm[0].length;
    }
    if (lastIdx < remaining.length) {
      segments.push({ text: remaining.slice(lastIdx), bold: false, italic: false });
    }
  }

  // Convert segments to Tiptap nodes
  for (const seg of segments) {
    const marks: TiptapMark[] = [];
    if (seg.bold) marks.push({ type: "bold" });
    if (seg.italic) marks.push({ type: "italic" });
    parts.push(...parseInlineText(seg.text, sourceMap, marks));
  }

  return parts;
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
    this.sourceMap = buildSourceMap(sources);

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
    const sourceMap = buildSourceMap(sources);
    return parseInlineFormatting(text, sourceMap);
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
