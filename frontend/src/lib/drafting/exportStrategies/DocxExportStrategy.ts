import {
  AlignmentType,
  BorderStyle,
  Document,
  FileChild,
  FootnoteReferenceRun,
  HeadingLevel,
  LevelFormat,
  Packer,
  Paragraph,
  type ParagraphChild,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  UnderlineType,
  WidthType,
} from "docx";

import type { SourceRef } from "@/lib/api";
import {
  INDENT_POINTS_PER_LEVEL,
  isAllowedFontSize,
  isAllowedLineSpacing,
  isAllowedParagraphSpacing,
  normalizeIndentLevel,
} from "@/lib/drafting/formatting";
import type {
  ExportOptions,
  TiptapDocument,
  TiptapMark,
  TiptapNode,
} from "@/types/drafting";
import {
  formatSource,
  LEGAL_DISCLAIMER,
  type ExportMetadata,
  type IExportStrategy,
} from "@/lib/drafting/exportStrategies/types";

const NUMBERING_REFERENCE = "legal-numbering";
const GOLD = "B58B16";
const PAGE_SIZE = {
  A4: { width: 11_906, height: 16_838 },
  Letter: { width: 12_240, height: 15_840 },
} as const;

export class DocxExportStrategy implements IExportStrategy {
  async export(
    document: TiptapDocument,
    sources: SourceRef[],
    options: ExportOptions,
    metadata: ExportMetadata,
  ): Promise<Blob> {
    return Packer.toBlob(buildDocxDocument(document, sources, options, metadata));
  }
}

export function buildDocxDocument(
  document: TiptapDocument,
  sources: SourceRef[],
  options: ExportOptions,
  metadata: ExportMetadata,
): Document {
  return new DocxDocumentMapper(sources, options, metadata).map(document);
}

class DocxDocumentMapper {
  private readonly sourcesById: Map<string, SourceRef>;
  private readonly footnoteNumbers = new Map<string, number>();
  private readonly footnotes: Record<string, { children: Paragraph[] }> = {};

  constructor(
    private readonly sources: SourceRef[],
    private readonly options: ExportOptions,
    private readonly metadata: ExportMetadata,
  ) {
    this.sourcesById = new Map(
      sources.map((source) => [source.citation_id, source]),
    );
  }

  map(document: TiptapDocument): Document {
    const children: FileChild[] = [];
    if (this.options.includeMetadata) {
      children.push(...this.metadataParagraphs());
    }
    children.push(...this.mapBlockNodes(document.content));
    if (this.options.includeSources && this.sources.length > 0) {
      children.push(...this.sourceParagraphs());
    }
    if (this.options.includeDisclaimer) {
      children.push(...this.disclaimerParagraphs());
    }

    const size = PAGE_SIZE[this.options.pageSize];
    return new Document({
      title: this.options.includeMetadata ? this.metadata.title : undefined,
      creator: this.options.includeMetadata ? this.metadata.author : undefined,
      subject: "AI-assisted legal draft",
      footnotes: this.footnotes,
      numbering: {
        config: [
          {
            reference: NUMBERING_REFERENCE,
            levels: Array.from({ length: 6 }, (_, level) => ({
              level,
              format: LevelFormat.DECIMAL,
              text: `%${level + 1}.`,
              alignment: AlignmentType.START,
              style: {
                paragraph: {
                  indent: {
                    left: 720 + level * 360,
                    hanging: 360,
                  },
                },
              },
            })),
          },
        ],
      },
      styles: {
        default: {
          document: {
            run: { font: "Times New Roman", size: 24 },
            paragraph: { spacing: { after: 120, line: 360 } },
          },
        },
      },
      sections: [
        {
          properties: {
            page: {
              size,
              margin: {
                top: pointsToTwips(this.options.margins.top),
                right: pointsToTwips(this.options.margins.right),
                bottom: pointsToTwips(this.options.margins.bottom),
                left: pointsToTwips(this.options.margins.left),
              },
            },
          },
          children,
        },
      ],
    });
  }

  private metadataParagraphs(): Paragraph[] {
    return [
      new Paragraph({
        children: [new TextRun({ text: this.metadata.title, bold: true, size: 32 })],
        heading: HeadingLevel.TITLE,
        spacing: { after: 180 },
      }),
      new Paragraph({
        children: [
          new TextRun({
            text: `Prepared by ${this.metadata.author} · ${formatDate(this.metadata.date)} · Version ${this.metadata.versionNumber}`,
            italics: true,
            color: "666666",
            size: 18,
          }),
        ],
        spacing: { after: 320 },
      }),
    ];
  }

  private mapBlockNodes(nodes: TiptapNode[], listDepth = 0): FileChild[] {
    return nodes.flatMap((node) => this.mapBlockNode(node, listDepth));
  }

  private mapBlockNode(node: TiptapNode, listDepth: number): FileChild[] {
    switch (node.type) {
      case "heading":
        return [
          new Paragraph({
            heading: headingLevel(node.attrs?.level),
            children: this.mapInlineNodes(node.content ?? []),
            alignment: paragraphAlignment(node.attrs?.textAlign),
            indent: blockIndent(node),
            spacing: blockSpacing(node, { before: 240, after: 120 }),
          }),
        ];
      case "paragraph":
        return [
          new Paragraph({
            children: this.mapInlineNodes(node.content ?? []),
            alignment: paragraphAlignment(node.attrs?.textAlign),
            indent: blockIndent(node),
            spacing: blockSpacing(node),
          }),
        ];
      case "bulletList":
        return this.mapList(node, false, listDepth);
      case "orderedList":
        return this.mapList(node, true, listDepth);
      case "blockquote":
        return [
          new Paragraph({
            children: this.mapInlineNodes(node.content ?? []),
            indent: { left: 720 },
            border: {
              left: {
                style: BorderStyle.SINGLE,
                color: GOLD,
                size: 12,
                space: 8,
              },
            },
          }),
        ];
      case "codeBlock":
        return [
          new Paragraph({
            children: [
              new TextRun({
                text: textContent(node),
                font: "Courier New",
                size: 20,
              }),
            ],
            shading: { type: ShadingType.CLEAR, fill: "F3F4F6" },
          }),
        ];
      case "table":
        return [this.mapTable(node)];
      case "horizontalRule":
        return [
          new Paragraph({
            border: {
              bottom: {
                style: BorderStyle.SINGLE,
                color: "999999",
                size: 6,
                space: 1,
              },
            },
          }),
        ];
      default:
        return node.content ? this.mapBlockNodes(node.content, listDepth) : [];
    }
  }

  private mapList(
    list: TiptapNode,
    ordered: boolean,
    depth: number,
  ): FileChild[] {
    const result: FileChild[] = [];
    for (const item of list.content ?? []) {
      const blocks = item.content ?? [];
      let emittedPrimaryParagraph = false;
      for (const block of blocks) {
        if (block.type === "bulletList" || block.type === "orderedList") {
          result.push(
            ...this.mapList(block, block.type === "orderedList", depth + 1),
          );
          continue;
        }
        if (block.type !== "paragraph") {
          result.push(...this.mapBlockNode(block, depth));
          continue;
        }
        result.push(
          new Paragraph({
            children: this.mapInlineNodes(block.content ?? []),
            alignment: paragraphAlignment(block.attrs?.textAlign),
            spacing: blockSpacing(block),
            ...(emittedPrimaryParagraph
              ? { indent: { left: 720 + depth * 360 } }
              : ordered
                ? {
                    numbering: {
                      reference: NUMBERING_REFERENCE,
                      level: Math.min(depth, 5),
                    },
                  }
                : { bullet: { level: Math.min(depth, 5) } }),
          }),
        );
        emittedPrimaryParagraph = true;
      }
    }
    return result;
  }

  private mapTable(node: TiptapNode): Table {
    const rows = (node.content ?? [])
      .filter((row) => row.type === "tableRow")
      .map(
        (row) =>
          new TableRow({
            children: (row.content ?? []).map((cell) => {
              const children = this.mapBlockNodes(cell.content ?? []).filter(
                (child): child is Paragraph | Table =>
                  child instanceof Paragraph || child instanceof Table,
              );
              return new TableCell({
                children: children.length > 0 ? children : [new Paragraph("")],
                margins: { top: 80, right: 100, bottom: 80, left: 100 },
                ...(cell.type === "tableHeader"
                  ? {
                      shading: {
                        type: ShadingType.CLEAR,
                        fill: "E8E1CC",
                      },
                    }
                  : {}),
              });
            }),
          }),
      );
    return new Table({
      rows:
        rows.length > 0
          ? rows
          : [
              new TableRow({
                children: [
                  new TableCell({ children: [new Paragraph("")] }),
                ],
              }),
            ],
      width: { size: 100, type: WidthType.PERCENTAGE },
    });
  }

  private mapInlineNodes(nodes: TiptapNode[]): ParagraphChild[] {
    return nodes.flatMap((node) => {
      if (node.type === "text") return this.mapTextNode(node);
      if (node.type === "hardBreak") return [new TextRun({ break: 1 })];
      return this.mapInlineNodes(node.content ?? []);
    });
  }

  private mapTextNode(node: TiptapNode): ParagraphChild[] {
    const marks = node.marks ?? [];
    const citation = marks.find((mark) => mark.type === "citationMark");
    const textStyle = marks.find((mark) => mark.type === "textStyle");
    const children: ParagraphChild[] = [
      new TextRun({
        text: node.text ?? "",
        bold: hasMark(marks, "bold"),
        italics: hasMark(marks, "italic"),
        strike: hasMark(marks, "strike"),
        underline: hasMark(marks, "underline")
          ? { type: UnderlineType.SINGLE }
          : undefined,
        font: hasMark(marks, "code") ? "Courier New" : undefined,
        shading: hasMark(marks, "code")
          ? { type: ShadingType.CLEAR, fill: "F3F4F6" }
          : undefined,
        superScript: Boolean(citation),
        color: citation ? GOLD : undefined,
        size: isAllowedFontSize(textStyle?.attrs?.fontSize)
          ? textStyle.attrs.fontSize * 2
          : undefined,
      }),
    ];

    if (citation && this.options.includeSources) {
      const citationId = String(citation.attrs?.citationId ?? node.text ?? "");
      const source = this.sourcesById.get(citationId);
      if (source) children.push(new FootnoteReferenceRun(this.footnoteFor(source)));
    }
    return children;
  }

  private footnoteFor(source: SourceRef): number {
    const existing = this.footnoteNumbers.get(source.citation_id);
    if (existing) return existing;
    const number = this.footnoteNumbers.size + 1;
    this.footnoteNumbers.set(source.citation_id, number);
    this.footnotes[String(number)] = {
      children: [
        new Paragraph({
          children: [
            new TextRun({ text: formatSource(source), size: 18 }),
            ...(source.excerpt
              ? [
                  new TextRun({
                    text: ` — ${source.excerpt}`,
                    italics: true,
                    size: 18,
                  }),
                ]
              : []),
          ],
        }),
      ],
    };
    return number;
  }

  private sourceParagraphs(): Paragraph[] {
    return [
      new Paragraph({
        text: "Sources",
        heading: HeadingLevel.HEADING_2,
        pageBreakBefore: true,
      }),
      ...this.sources.map(
        (source) =>
          new Paragraph({
            children: [new TextRun(formatSource(source))],
            bullet: { level: 0 },
          }),
      ),
    ];
  }

  private disclaimerParagraphs(): Paragraph[] {
    return [
      new Paragraph({
        text: "Legal Disclaimer",
        heading: HeadingLevel.HEADING_2,
        spacing: { before: 360, after: 120 },
      }),
      new Paragraph({
        children: [
          new TextRun({
            text: LEGAL_DISCLAIMER,
            italics: true,
            color: "666666",
            size: 18,
          }),
        ],
      }),
    ];
  }
}

function hasMark(marks: TiptapMark[], type: string): boolean {
  return marks.some((mark) => mark.type === type);
}

function textContent(node: TiptapNode): string {
  if (node.type === "text") return node.text ?? "";
  return (node.content ?? []).map(textContent).join("");
}

function headingLevel(value: unknown): (typeof HeadingLevel)[keyof typeof HeadingLevel] {
  switch (Number(value)) {
    case 1:
      return HeadingLevel.HEADING_1;
    case 3:
      return HeadingLevel.HEADING_3;
    case 4:
      return HeadingLevel.HEADING_4;
    default:
      return HeadingLevel.HEADING_2;
  }
}

function paragraphAlignment(
  value: unknown,
): (typeof AlignmentType)[keyof typeof AlignmentType] | undefined {
  switch (value) {
    case "center":
      return AlignmentType.CENTER;
    case "right":
      return AlignmentType.RIGHT;
    case "justify":
      return AlignmentType.JUSTIFIED;
    case "left":
      return AlignmentType.LEFT;
    default:
      return undefined;
  }
}

function pointsToTwips(points: number): number {
  return Math.max(0, Math.round(points * 20));
}

function blockIndent(node: TiptapNode): { left: number } | undefined {
  const level = normalizeIndentLevel(node.attrs?.indentLevel);
  return level > 0
    ? { left: pointsToTwips(level * INDENT_POINTS_PER_LEVEL) }
    : undefined;
}

function blockSpacing(
  node: TiptapNode,
  defaults: { before?: number; after?: number } = {},
): { before?: number; after?: number; line?: number } | undefined {
  const before = isAllowedParagraphSpacing(node.attrs?.spacingBefore)
    ? pointsToTwips(node.attrs.spacingBefore)
    : defaults.before;
  const after = isAllowedParagraphSpacing(node.attrs?.spacingAfter)
    ? pointsToTwips(node.attrs.spacingAfter)
    : defaults.after;
  const line = isAllowedLineSpacing(node.attrs?.lineSpacing)
    ? Math.round(node.attrs.lineSpacing * 240)
    : undefined;

  return before === undefined && after === undefined && line === undefined
    ? undefined
    : { before, after, line };
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en-GB", { dateStyle: "long" }).format(date);
}
