/**
 * Strategy-based document diffing for the read-only Show Edits experience.
 *
 * TextDiffStrategy produces ProseMirror positions against the current
 * document. StructuralDiffStrategy exposes RFC 6902 changes for callers that
 * need node/attribute-level review. DiffService depends only on the strategy
 * interface, so either algorithm can be replaced independently.
 */

import DiffMatchPatch from "diff-match-patch";
import { compare, type Operation } from "fast-json-patch";

import type {
  DiffChange,
  TiptapDocument,
  TiptapNode,
} from "@/types/drafting";

export interface IDiffStrategy {
  computeDiff(
    original: TiptapDocument,
    current: TiptapDocument,
  ): DiffChange[];
}

interface TextSpan {
  fromOffset: number;
  toOffset: number;
  fromPosition: number;
  toPosition: number;
  path: string;
}

interface FlattenedDocument {
  text: string;
  positions: number[];
  spans: TextSpan[];
  endPosition: number;
}

const TEXT_BLOCK_TYPES = new Set(["paragraph", "heading", "codeBlock"]);

export class TextDiffStrategy implements IDiffStrategy {
  private readonly engine: DiffMatchPatch;

  constructor(engine = new DiffMatchPatch()) {
    this.engine = engine;
  }

  computeDiff(
    original: TiptapDocument,
    current: TiptapDocument,
  ): DiffChange[] {
    const originalFlat = flattenDocument(original);
    const currentFlat = flattenDocument(current);
    const diffs = this.engine.diff_main(
      originalFlat.text,
      currentFlat.text,
      true,
    );
    this.engine.diff_cleanupSemantic(diffs);

    const changes: DiffChange[] = [];
    let currentOffset = 0;

    for (let index = 0; index < diffs.length; index += 1) {
      const [operation, value] = diffs[index];
      if (operation === DiffMatchPatch.DIFF_EQUAL) {
        currentOffset += value.length;
        continue;
      }

      const next = diffs[index + 1];
      if (
        operation === DiffMatchPatch.DIFF_DELETE &&
        next?.[0] === DiffMatchPatch.DIFF_INSERT
      ) {
        const replacement = next[1];
        changes.push(
          createTextChange(
            "replace",
            currentFlat,
            currentOffset,
            currentOffset + replacement.length,
            value,
            replacement,
          ),
        );
        currentOffset += replacement.length;
        index += 1;
        continue;
      }

      if (
        operation === DiffMatchPatch.DIFF_INSERT &&
        next?.[0] === DiffMatchPatch.DIFF_DELETE
      ) {
        const removed = next[1];
        changes.push(
          createTextChange(
            "replace",
            currentFlat,
            currentOffset,
            currentOffset + value.length,
            removed,
            value,
          ),
        );
        currentOffset += value.length;
        index += 1;
        continue;
      }

      if (operation === DiffMatchPatch.DIFF_DELETE) {
        changes.push(
          createTextChange(
            "delete",
            currentFlat,
            currentOffset,
            currentOffset,
            value,
            undefined,
          ),
        );
        continue;
      }

      changes.push(
        createTextChange(
          "insert",
          currentFlat,
          currentOffset,
          currentOffset + value.length,
          undefined,
          value,
        ),
      );
      currentOffset += value.length;
    }

    return changes;
  }
}

export class StructuralDiffStrategy implements IDiffStrategy {
  computeDiff(
    original: TiptapDocument,
    current: TiptapDocument,
  ): DiffChange[] {
    const currentFlat = flattenDocument(current);
    return compare(original, current, false).map((operation) =>
      structuralChange(operation, currentFlat),
    );
  }
}

export class DiffService {
  constructor(private strategy: IDiffStrategy = new TextDiffStrategy()) {}

  setStrategy(strategy: IDiffStrategy): void {
    this.strategy = strategy;
  }

  computeDiff(
    original: TiptapDocument,
    current: TiptapDocument,
  ): DiffChange[] {
    return this.strategy.computeDiff(original, current);
  }
}

function createTextChange(
  type: "insert" | "delete" | "replace",
  document: FlattenedDocument,
  fromOffset: number,
  toOffset: number,
  oldContent?: string,
  newContent?: string,
): DiffChange {
  return {
    type,
    path: pathAtOffset(document, fromOffset),
    oldContent,
    newContent,
    position: {
      from: positionAtOffset(document, fromOffset),
      to: positionAtOffset(document, toOffset),
    },
  };
}

function structuralChange(
  operation: Operation,
  current: FlattenedDocument,
): DiffChange {
  const span = current.spans.find((candidate) =>
    operation.path.startsWith(`/${candidate.path.replaceAll(".", "/")}`),
  );
  const value = "value" in operation ? stringifyValue(operation.value) : undefined;
  return {
    type: "format_change",
    path: operation.path,
    oldContent: operation.op === "remove" ? "Removed structure" : undefined,
    newContent: value,
    position: span
      ? { from: span.fromPosition, to: span.toPosition }
      : { from: 1, to: Math.max(1, current.endPosition) },
  };
}

function flattenDocument(document: TiptapDocument): FlattenedDocument {
  const chunks: string[] = [];
  const positions: number[] = [];
  const spans: TextSpan[] = [];
  let offset = 0;
  let sawTextBlock = false;

  const appendText = (text: string, position: number, path: string) => {
    if (positions[offset] === undefined) positions[offset] = position;
    const start = offset;
    chunks.push(text);
    for (let index = 0; index < text.length; index += 1) {
      positions[offset] = position + index;
      offset += 1;
      positions[offset] = position + index + 1;
    }
    if (text.length > 0) {
      spans.push({
        fromOffset: start,
        toOffset: offset,
        fromPosition: position,
        toPosition: position + text.length,
        path,
      });
    }
  };

  const appendBlockSeparator = (position: number) => {
    if (!sawTextBlock) {
      sawTextBlock = true;
      if (positions[offset] === undefined) positions[offset] = position;
      return;
    }
    chunks.push("\n");
    offset += 1;
    positions[offset] = position;
  };

  const visit = (node: TiptapNode, position: number, path: string): number => {
    if (node.type === "text") {
      const text = node.text ?? "";
      appendText(text, position, path);
      return text.length;
    }

    if (node.type === "hardBreak") {
      appendText("\n", position, path);
      return 1;
    }

    const isTextBlock = TEXT_BLOCK_TYPES.has(node.type);
    const contentStart = position + 1;
    if (isTextBlock) appendBlockSeparator(contentStart);

    let childPosition = contentStart;
    for (let index = 0; index < (node.content ?? []).length; index += 1) {
      const child = node.content![index];
      childPosition += visit(child, childPosition, `${path}.content.${index}`);
    }
    return childPosition - position + 1;
  };

  let topLevelPosition = 0;
  document.content.forEach((node, index) => {
    topLevelPosition += visit(node, topLevelPosition, `content.${index}`);
  });
  if (positions[offset] === undefined) {
    positions[offset] = Math.max(1, topLevelPosition);
  }

  return {
    text: chunks.join(""),
    positions,
    spans,
    endPosition: topLevelPosition,
  };
}

function positionAtOffset(document: FlattenedDocument, offset: number): number {
  const safeOffset = Math.max(0, Math.min(offset, document.text.length));
  if (document.positions[safeOffset] !== undefined) {
    return document.positions[safeOffset];
  }
  return document.endPosition;
}

function pathAtOffset(document: FlattenedDocument, offset: number): string {
  return (
    document.spans.find(
      (span) => offset >= span.fromOffset && offset <= span.toOffset,
    )?.path ??
    document.spans.at(-1)?.path ??
    "content"
  );
}

function stringifyValue(value: unknown): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export const diffService = new DiffService();
