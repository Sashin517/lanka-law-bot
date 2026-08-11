import type { SourceRef } from "@/lib/api";
import {
  INDENT_POINTS_PER_LEVEL,
  isAllowedFontSize,
  isAllowedLineSpacing,
  isAllowedParagraphSpacing,
  isTextAlignment,
  normalizeIndentLevel,
} from "@/lib/drafting/formatting";
import type {
  ExportOptions,
  TiptapDocument,
  TiptapMark,
  TiptapNode,
} from "@/types/drafting";
import {
  escapeHtml,
  formatSource,
  LEGAL_DISCLAIMER,
  type ExportMetadata,
  type IExportStrategy,
} from "@/lib/drafting/exportStrategies/types";

export class PdfExportStrategy implements IExportStrategy {
  async export(
    document: TiptapDocument,
    sources: SourceRef[],
    options: ExportOptions,
    metadata: ExportMetadata,
  ): Promise<Blob> {
    if (!globalThis.document) {
      throw new Error("PDF export is only available in a browser session.");
    }

    const html2pdf = (await import("html2pdf.js")).default;
    const container = globalThis.document.createElement("div");
    container.setAttribute("aria-hidden", "true");
    container.style.cssText =
      "position:fixed;left:-100000px;top:0;width:816px;background:#fff;color:#111;";
    container.innerHTML = renderPdfHtml(document, sources, options, metadata);
    globalThis.document.body.appendChild(container);

    try {
      const blob = await html2pdf()
        .set({
          margin: [0, 0, 0, 0],
          image: { type: "jpeg", quality: 0.98 },
          enableLinks: true,
          html2canvas: {
            scale: 2,
            useCORS: true,
            backgroundColor: "#ffffff",
            logging: false,
          },
          jsPDF: {
            unit: "pt",
            format: options.pageSize.toLowerCase(),
            orientation: "portrait",
          },
        })
        .from(container)
        .toPdf()
        .outputPdf("blob");
      if (!(blob instanceof Blob)) {
        throw new Error("The PDF renderer returned an invalid document.");
      }
      return blob;
    } finally {
      container.remove();
    }
  }
}

export function renderPdfHtml(
  document: TiptapDocument,
  sources: SourceRef[],
  options: ExportOptions,
  metadata: ExportMetadata,
): string {
  const margin = options.margins;
  const metadataHtml = options.includeMetadata
    ? `<header class="document-metadata"><h1>${escapeHtml(metadata.title)}</h1><p>Prepared by ${escapeHtml(metadata.author)} · ${escapeHtml(formatDate(metadata.date))} · Version ${metadata.versionNumber}</p></header>`
    : "";
  const sourcesHtml =
    options.includeSources && sources.length > 0
      ? `<section class="export-sources"><h2>Sources</h2><ol>${sources
          .map(
            (source) =>
              `<li><strong>${escapeHtml(source.citation_id)}</strong> ${escapeHtml(formatSource(source).replace(`${source.citation_id} `, ""))}${
                source.excerpt
                  ? `<blockquote>${escapeHtml(source.excerpt)}</blockquote>`
                  : ""
              }</li>`,
          )
          .join("")}</ol></section>`
      : "";
  const disclaimerHtml = options.includeDisclaimer
    ? `<section class="export-disclaimer"><h2>Legal Disclaimer</h2><p>${escapeHtml(LEGAL_DISCLAIMER)}</p></section>`
    : "";

  return `<article class="legal-export" data-page-size="${options.pageSize}">
    <style>
      @page { size: ${options.pageSize}; margin: 0; }
      .legal-export { box-sizing: border-box; background: #fff; color: #111; font-family: Georgia, "Times New Roman", serif; font-size: 11pt; line-height: 1.55; min-height: 100%; padding: ${margin.top}pt ${margin.right}pt ${margin.bottom}pt ${margin.left}pt; }
      .legal-export h1 { font-size: 20pt; margin: 0 0 16pt; text-align: center; }
      .legal-export h2 { font-size: 15pt; margin: 18pt 0 8pt; }
      .legal-export h3 { font-size: 13pt; margin: 14pt 0 6pt; }
      .legal-export h4 { font-size: 11pt; margin: 12pt 0 4pt; }
      .legal-export p { margin: 0 0 8pt; text-align: justify; }
      .legal-export blockquote { border-left: 2pt solid #b58b16; margin: 10pt 0; padding-left: 12pt; }
      .legal-export table { border-collapse: collapse; margin: 10pt 0; width: 100%; }
      .legal-export th, .legal-export td { border: 0.5pt solid #777; padding: 5pt; vertical-align: top; }
      .legal-export th { background: #eee9dc; font-weight: 700; }
      .legal-export code, .legal-export pre { background: #f3f4f6; font-family: "Courier New", monospace; }
      .legal-export pre { padding: 8pt; white-space: pre-wrap; }
      .legal-export .citation { color: #8a6910; font-size: 0.78em; font-weight: 700; }
      .document-metadata { border-bottom: 0.75pt solid #b58b16; margin-bottom: 22pt; padding-bottom: 10pt; }
      .document-metadata p { color: #555; font-size: 9pt; text-align: center; }
      .export-sources { break-before: page; }
      .export-sources li { margin-bottom: 7pt; }
      .export-sources blockquote { color: #444; font-size: 9pt; font-style: italic; }
      .export-disclaimer { border-top: 0.75pt solid #aaa; color: #555; font-size: 9pt; margin-top: 24pt; padding-top: 10pt; }
      .export-disclaimer h2 { font-size: 11pt; }
    </style>
    ${metadataHtml}
    <main>${renderBlockNodes(document.content)}</main>
    ${sourcesHtml}
    ${disclaimerHtml}
  </article>`;
}

function renderBlockNodes(nodes: TiptapNode[]): string {
  return nodes.map(renderBlockNode).join("");
}

function renderBlockNode(node: TiptapNode): string {
  switch (node.type) {
    case "heading": {
      const level = Math.max(1, Math.min(4, Number(node.attrs?.level) || 2));
      return `<h${level}${blockStyle(node)}>${renderInlineNodes(node.content ?? [])}</h${level}>`;
    }
    case "paragraph":
      return `<p${blockStyle(node)}>${renderInlineNodes(node.content ?? []) || "&nbsp;"}</p>`;
    case "bulletList":
      return `<ul>${(node.content ?? []).map(renderListItem).join("")}</ul>`;
    case "orderedList":
      return `<ol>${(node.content ?? []).map(renderListItem).join("")}</ol>`;
    case "blockquote":
      return `<blockquote>${renderBlockNodes(node.content ?? [])}</blockquote>`;
    case "codeBlock":
      return `<pre><code>${escapeHtml(textContent(node))}</code></pre>`;
    case "table":
      return `<table>${(node.content ?? []).map(renderTableRow).join("")}</table>`;
    case "horizontalRule":
      return "<hr>";
    default:
      return node.content ? renderBlockNodes(node.content) : "";
  }
}

function renderListItem(node: TiptapNode): string {
  return `<li>${renderBlockNodes(node.content ?? [])}</li>`;
}

function renderTableRow(node: TiptapNode): string {
  return `<tr>${(node.content ?? [])
    .map((cell) => {
      const tag = cell.type === "tableHeader" ? "th" : "td";
      return `<${tag}>${renderBlockNodes(cell.content ?? [])}</${tag}>`;
    })
    .join("")}</tr>`;
}

function renderInlineNodes(nodes: TiptapNode[]): string {
  return nodes
    .map((node) => {
      if (node.type === "hardBreak") return "<br>";
      if (node.type !== "text") return renderInlineNodes(node.content ?? []);
      return applyInlineMarks(escapeHtml(node.text ?? ""), node.marks ?? []);
    })
    .join("");
}

function applyInlineMarks(content: string, marks: TiptapMark[]): string {
  let result = content;
  const textStyle = marks.find((mark) => mark.type === "textStyle");
  if (isAllowedFontSize(textStyle?.attrs?.fontSize)) {
    result = `<span data-font-size="${textStyle.attrs.fontSize}" style="font-size:${textStyle.attrs.fontSize}pt">${result}</span>`;
  }
  if (hasMark(marks, "code")) result = `<code>${result}</code>`;
  if (hasMark(marks, "bold")) result = `<strong>${result}</strong>`;
  if (hasMark(marks, "italic")) result = `<em>${result}</em>`;
  if (hasMark(marks, "underline")) result = `<u>${result}</u>`;
  if (hasMark(marks, "strike")) result = `<s>${result}</s>`;
  if (hasMark(marks, "citationMark")) {
    result = `<sup class="citation">${result}</sup>`;
  }
  return result;
}

function hasMark(marks: TiptapMark[], type: string): boolean {
  return marks.some((mark) => mark.type === type);
}

function textContent(node: TiptapNode): string {
  if (node.type === "text") return node.text ?? "";
  return (node.content ?? []).map(textContent).join("");
}

function blockStyle(node: TiptapNode): string {
  const declarations: string[] = [];
  if (isTextAlignment(node.attrs?.textAlign)) {
    declarations.push(`text-align:${node.attrs.textAlign}`);
  }
  const indent = normalizeIndentLevel(node.attrs?.indentLevel);
  if (indent > 0) {
    declarations.push(`margin-left:${indent * INDENT_POINTS_PER_LEVEL}pt`);
  }
  if (isAllowedLineSpacing(node.attrs?.lineSpacing)) {
    declarations.push(`line-height:${node.attrs.lineSpacing}`);
  }
  if (isAllowedParagraphSpacing(node.attrs?.spacingBefore)) {
    declarations.push(`margin-top:${node.attrs.spacingBefore}pt`);
  }
  if (isAllowedParagraphSpacing(node.attrs?.spacingAfter)) {
    declarations.push(`margin-bottom:${node.attrs.spacingAfter}pt`);
  }
  return declarations.length > 0 ? ` style="${declarations.join(";")}"` : "";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en-GB", { dateStyle: "long" }).format(date);
}
