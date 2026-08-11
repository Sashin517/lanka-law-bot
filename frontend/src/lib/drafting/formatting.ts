/**
 * Controlled legal-document formatting values.
 *
 * Keeping these values centralized prevents arbitrary inline CSS from entering
 * canonical Tiptap JSON and gives the editor and both exporters one contract.
 */

export const FONT_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 24] as const;
export const LINE_SPACINGS = [1, 1.15, 1.5, 2] as const;
export const PARAGRAPH_SPACINGS = [0, 6, 8, 12, 18, 24] as const;
export const TEXT_ALIGNMENTS = ["left", "center", "right", "justify"] as const;
export const HEADING_LEVELS = [1, 2, 3, 4] as const;

export const DEFAULT_FONT_SIZE: FontSize = 12;
export const DEFAULT_LINE_SPACING: LineSpacing = 1.5;
export const DEFAULT_PARAGRAPH_SPACING: ParagraphSpacing = 8;
export const MAX_INDENT_LEVEL = 6;
export const INDENT_POINTS_PER_LEVEL = 36;

export type FontSize = (typeof FONT_SIZES)[number];
export type LineSpacing = (typeof LINE_SPACINGS)[number];
export type ParagraphSpacing = (typeof PARAGRAPH_SPACINGS)[number];
export type TextAlignment = (typeof TEXT_ALIGNMENTS)[number];
export type HeadingLevel = (typeof HEADING_LEVELS)[number];
export type BlockType = "paragraph" | `heading-${HeadingLevel}`;
export type InlineFormat = "bold" | "italic" | "underline" | "strike";

export interface EditorFormattingState {
  blockType: BlockType;
  fontSize: FontSize;
  alignment: TextAlignment;
  indentLevel: number;
  lineSpacing: LineSpacing;
  spacingBefore: ParagraphSpacing;
  spacingAfter: ParagraphSpacing;
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strike: boolean;
  canUndo: boolean;
  canRedo: boolean;
}

export function isAllowedFontSize(value: unknown): value is FontSize {
  return includesNumber(FONT_SIZES, value);
}

export function isAllowedLineSpacing(value: unknown): value is LineSpacing {
  return includesNumber(LINE_SPACINGS, value);
}

export function isAllowedParagraphSpacing(
  value: unknown,
): value is ParagraphSpacing {
  return includesNumber(PARAGRAPH_SPACINGS, value);
}

export function isTextAlignment(value: unknown): value is TextAlignment {
  return typeof value === "string" &&
    (TEXT_ALIGNMENTS as readonly string[]).includes(value);
}

export function normalizeFontSize(value: unknown): FontSize {
  return isAllowedFontSize(value) ? value : DEFAULT_FONT_SIZE;
}

export function normalizeLineSpacing(value: unknown): LineSpacing {
  return isAllowedLineSpacing(value) ? value : DEFAULT_LINE_SPACING;
}

export function normalizeParagraphSpacing(value: unknown): ParagraphSpacing {
  return isAllowedParagraphSpacing(value)
    ? value
    : DEFAULT_PARAGRAPH_SPACING;
}

export function normalizeAlignment(value: unknown): TextAlignment {
  return isTextAlignment(value) ? value : "left";
}

export function normalizeIndentLevel(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.min(MAX_INDENT_LEVEL, Math.max(0, Math.round(parsed)));
}

export function parsePointValue(value: string | null | undefined): number {
  if (!value) return Number.NaN;
  const match = /^\s*(-?\d+(?:\.\d+)?)pt\s*$/i.exec(value);
  return match ? Number(match[1]) : Number.NaN;
}

export function lineSpacingLabel(value: LineSpacing): string {
  return value === 1 ? "Single" : value === 2 ? "Double" : String(value);
}

function includesNumber<const T extends readonly number[]>(
  values: T,
  value: unknown,
): value is T[number] {
  return typeof value === "number" && Number.isFinite(value) &&
    (values as readonly number[]).includes(value);
}
