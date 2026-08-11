/**
 * Immutable document-version aggregate (Memento pattern).
 *
 * Zustand persists the aggregate; this service owns chain validation,
 * snapshot creation, restoration semantics, and read-only history access.
 */

import type { SourceRef } from "@/lib/api";
import type { IEditorService } from "@/lib/drafting/editorService";
import type {
  DocumentVersion,
  TiptapDocument,
} from "@/types/drafting";

export class VersionChainError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "VersionChainError";
  }
}

export interface RestoreVersionResult {
  restoredFrom: DocumentVersion;
  newVersion: DocumentVersion;
}

type SnapshotSource = IEditorService | TiptapDocument;

export class VersionControlService {
  private versions = new Map<string, DocumentVersion>();
  private currentVersionId: string | null = null;

  hydrate(
    versions: DocumentVersion[],
    currentVersionId: string | null,
  ): void {
    const ordered = [...versions].sort(
      (left, right) => left.versionNumber - right.versionNumber,
    );
    validateVersionChain(ordered);
    if (
      currentVersionId &&
      !ordered.some((version) => version.id === currentVersionId)
    ) {
      throw new VersionChainError(
        `Current version '${currentVersionId}' is not present in the chain.`,
      );
    }

    this.versions = new Map(
      ordered.map((version) => [version.id, cloneVersion(version)]),
    );
    this.currentVersionId =
      currentVersionId ?? ordered.at(-1)?.id ?? null;
  }

  createSnapshot(
    source: SnapshotSource,
    sources: SourceRef[],
    editSummary: string,
    createdBy: "ai" | "user",
  ): DocumentVersion | null {
    const content = isEditorService(source)
      ? source.getDocument()
      : cloneDocument(source);
    const current = this.getCurrentVersion();
    if (current && documentsEqual(current.content, content)) {
      return null;
    }

    const nextNumber = this.getVersionHistory().reduce(
      (maximum, version) => Math.max(maximum, version.versionNumber),
      0,
    ) + 1;
    const version: DocumentVersion = {
      id: crypto.randomUUID(),
      versionNumber: nextNumber,
      label: `Version ${nextNumber}`,
      content: cloneDocument(content),
      sources: cloneSources(sources),
      createdAt: new Date().toISOString(),
      createdBy,
      editSummary: editSummary.trim() || "Document updated.",
      parentVersionId: this.currentVersionId,
    };
    this.versions.set(version.id, cloneVersion(version));
    this.currentVersionId = version.id;
    return cloneVersion(version);
  }

  appendSnapshot(version: DocumentVersion): void {
    if (this.versions.has(version.id)) {
      const existing = this.versions.get(version.id)!;
      if (JSON.stringify(existing) === JSON.stringify(version)) return;
      throw new VersionChainError(
        `Version ID '${version.id}' already contains another snapshot.`,
      );
    }

    const history = this.getVersionHistory();
    const expectedNumber = (history.at(-1)?.versionNumber ?? 0) + 1;
    if (version.versionNumber !== expectedNumber) {
      throw new VersionChainError(
        `Expected version number ${expectedNumber}, received ${version.versionNumber}.`,
      );
    }
    if (version.parentVersionId !== this.currentVersionId) {
      throw new VersionChainError(
        "A new snapshot must reference the current version as its parent.",
      );
    }
    this.versions.set(version.id, cloneVersion(version));
    this.currentVersionId = version.id;
  }

  restoreVersion(
    versionId: string,
    editor: IEditorService,
  ): RestoreVersionResult | null {
    const target = this.versions.get(versionId);
    if (!target) {
      throw new VersionChainError(`Version '${versionId}' was not found.`);
    }
    if (versionId === this.currentVersionId) return null;

    const restoredDocument = cloneDocument(target.content);
    editor.setDocument(restoredDocument);
    const newVersion = this.createSnapshot(
      restoredDocument,
      target.sources,
      `Restored from Version ${target.versionNumber}.`,
      "user",
    );
    if (!newVersion) return null;
    return {
      restoredFrom: cloneVersion(target),
      newVersion,
    };
  }

  getVersionHistory(): DocumentVersion[] {
    return Array.from(this.versions.values())
      .sort((left, right) => left.versionNumber - right.versionNumber)
      .map(cloneVersion);
  }

  getVersion(versionId: string): DocumentVersion | undefined {
    const version = this.versions.get(versionId);
    return version ? cloneVersion(version) : undefined;
  }

  getCurrentVersion(): DocumentVersion | undefined {
    return this.currentVersionId
      ? this.getVersion(this.currentVersionId)
      : undefined;
  }

  getCurrentVersionId(): string | null {
    return this.currentVersionId;
  }

}

export function validateVersionChain(versions: DocumentVersion[]): void {
  const ids = new Set<string>();
  let previous: DocumentVersion | undefined;
  versions.forEach((version, index) => {
    if (!isDocumentVersion(version)) {
      throw new VersionChainError(
        `Version at position ${index + 1} has an invalid snapshot shape.`,
      );
    }
    if (ids.has(version.id)) {
      throw new VersionChainError(`Duplicate version ID '${version.id}'.`);
    }
    if (version.versionNumber !== index + 1) {
      throw new VersionChainError(
        `Version numbers must be contiguous; expected ${index + 1}.`,
      );
    }
    const expectedParent = previous?.id ?? null;
    if (version.parentVersionId !== expectedParent) {
      throw new VersionChainError(
        `Version ${version.versionNumber} has an invalid parent.`,
      );
    }
    ids.add(version.id);
    previous = version;
  });
}

function isDocumentVersion(value: unknown): value is DocumentVersion {
  if (!value || typeof value !== "object") return false;
  const version = value as Partial<DocumentVersion>;
  return (
    typeof version.id === "string" &&
    version.id.length > 0 &&
    Number.isInteger(version.versionNumber) &&
    typeof version.label === "string" &&
    version.content?.type === "doc" &&
    Array.isArray(version.content.content) &&
    Array.isArray(version.sources) &&
    typeof version.createdAt === "string" &&
    !Number.isNaN(Date.parse(version.createdAt)) &&
    (version.createdBy === "ai" || version.createdBy === "user") &&
    typeof version.editSummary === "string" &&
    (version.parentVersionId === null ||
      typeof version.parentVersionId === "string")
  );
}

function isEditorService(source: SnapshotSource): source is IEditorService {
  return "getDocument" in source && typeof source.getDocument === "function";
}

function documentsEqual(
  left: TiptapDocument,
  right: TiptapDocument,
): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function cloneDocument(document: TiptapDocument): TiptapDocument {
  return JSON.parse(JSON.stringify(document)) as TiptapDocument;
}

function cloneSources(sources: SourceRef[]): SourceRef[] {
  return JSON.parse(JSON.stringify(sources)) as SourceRef[];
}

function cloneVersion(version: DocumentVersion): DocumentVersion {
  return {
    ...version,
    content: cloneDocument(version.content),
    sources: cloneSources(version.sources),
  };
}

export const versionControlService = new VersionControlService();
