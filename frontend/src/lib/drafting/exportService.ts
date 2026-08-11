/**
 * Export facade and strategy factory.
 *
 * The facade accepts an immutable DocumentVersion rather than an editor. This
 * prevents pending suggestions, unsaved browser state, and Show Edits
 * decorations from leaking into generated legal documents.
 */

import type { DocumentVersion, ExportFormat, ExportOptions } from "@/types/drafting";
import { DocxExportStrategy } from "@/lib/drafting/exportStrategies/DocxExportStrategy";
import { PdfExportStrategy } from "@/lib/drafting/exportStrategies/PdfExportStrategy";
import type {
  ExportMetadata,
  IExportStrategy,
} from "@/lib/drafting/exportStrategies/types";

export interface ExportArtifact {
  blob: Blob;
  filename: string;
  format: ExportFormat;
  versionId: string;
}

export interface ExportVersionRequest {
  version: DocumentVersion;
  options: ExportOptions;
  title: string;
  author: string;
}

type StrategyFactory = (format: ExportFormat) => IExportStrategy;
type BlobDownloader = (blob: Blob, filename: string) => Promise<void>;

export class UnsupportedExportFormatError extends Error {
  constructor(format: never) {
    super(`Unsupported export format: ${String(format)}`);
    this.name = "UnsupportedExportFormatError";
  }
}

export class ExportStrategyFactory {
  static create(format: ExportFormat): IExportStrategy {
    switch (format) {
      case "docx":
        return new DocxExportStrategy();
      case "pdf":
        return new PdfExportStrategy();
      default:
        throw new UnsupportedExportFormatError(format);
    }
  }
}

export class ExportService {
  constructor(
    private readonly createStrategy: StrategyFactory =
      ExportStrategyFactory.create,
    private readonly downloadBlob: BlobDownloader = browserDownload,
  ) {}

  async createArtifact(request: ExportVersionRequest): Promise<ExportArtifact> {
    validateExportRequest(request);
    const metadata: ExportMetadata = {
      title: request.title.trim() || "Legal Document - LankaLawBot",
      author: request.author.trim() || "LankaLawBot AI",
      date: request.version.createdAt,
      versionNumber: request.version.versionNumber,
    };
    const blob = await this.createStrategy(request.options.format).export(
      request.version.content,
      request.version.sources,
      request.options,
      metadata,
    );
    if (blob.size === 0) {
      throw new Error("The export renderer produced an empty document.");
    }

    return {
      blob,
      filename: `${safeFilename(metadata.title)}-v${request.version.versionNumber}.${request.options.format}`,
      format: request.options.format,
      versionId: request.version.id,
    };
  }

  async exportDocument(request: ExportVersionRequest): Promise<ExportArtifact> {
    const artifact = await this.createArtifact(request);
    await this.downloadBlob(artifact.blob, artifact.filename);
    return artifact;
  }
}

function validateExportRequest(request: ExportVersionRequest): void {
  if (!request.version?.id || request.version.content?.type !== "doc") {
    throw new Error("An accepted document version is required for export.");
  }
  if (!Array.isArray(request.version.content.content)) {
    throw new Error("The accepted document version has invalid editor content.");
  }
  const margins = Object.values(request.options.margins);
  if (margins.some((margin) => !Number.isFinite(margin) || margin < 0 || margin > 288)) {
    throw new Error("Export margins must be between 0 and 288 points.");
  }
}

async function browserDownload(blob: Blob, filename: string): Promise<void> {
  if (!globalThis.document) {
    throw new Error("Document downloads are only available in a browser session.");
  }
  const fileSaver = await import("file-saver");
  const save = fileSaver.default ?? fileSaver.saveAs;
  save(blob, filename, { autoBom: false });
}

function safeFilename(value: string): string {
  const normalized = value
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9._ -]/g, "")
    .trim()
    .replace(/[ .]+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 100);
  return normalized || "legal-draft";
}

export const exportService = new ExportService();
