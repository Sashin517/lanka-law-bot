import { Extension } from "@tiptap/core";

import {
  INDENT_POINTS_PER_LEVEL,
  isAllowedLineSpacing,
  isAllowedParagraphSpacing,
  normalizeIndentLevel,
  parsePointValue,
} from "@/lib/drafting/formatting";

/**
 * Persists block-level legal formatting on paragraphs and headings.
 * Values are validated against the shared allowlists before rendering.
 */
export const ParagraphFormatting = Extension.create({
  name: "paragraphFormatting",

  addGlobalAttributes() {
    return [
      {
        types: ["paragraph", "heading"],
        attributes: {
          indentLevel: {
            default: 0,
            parseHTML: (element) =>
              normalizeIndentLevel(element.getAttribute("data-indent-level")),
            renderHTML: (attributes) => {
              const level = normalizeIndentLevel(attributes.indentLevel);
              return level > 0
                ? {
                    "data-indent-level": String(level),
                    style: `margin-left: ${level * INDENT_POINTS_PER_LEVEL}pt`,
                  }
                : {};
            },
          },
          lineSpacing: {
            default: null,
            parseHTML: (element) => {
              const value = Number(element.style.lineHeight);
              return isAllowedLineSpacing(value) ? value : null;
            },
            renderHTML: (attributes) =>
              isAllowedLineSpacing(attributes.lineSpacing)
                ? {
                    "data-line-spacing": String(attributes.lineSpacing),
                    style: `line-height: ${attributes.lineSpacing}`,
                  }
                : {},
          },
          spacingBefore: {
            default: null,
            parseHTML: (element) => {
              const value = parsePointValue(element.style.marginTop);
              return isAllowedParagraphSpacing(value) ? value : null;
            },
            renderHTML: (attributes) =>
              isAllowedParagraphSpacing(attributes.spacingBefore)
                ? {
                    "data-spacing-before": String(attributes.spacingBefore),
                    style: `margin-top: ${attributes.spacingBefore}pt`,
                  }
                : {},
          },
          spacingAfter: {
            default: null,
            parseHTML: (element) => {
              const value = parsePointValue(element.style.marginBottom);
              return isAllowedParagraphSpacing(value) ? value : null;
            },
            renderHTML: (attributes) =>
              isAllowedParagraphSpacing(attributes.spacingAfter)
                ? {
                    "data-spacing-after": String(attributes.spacingAfter),
                    style: `margin-bottom: ${attributes.spacingAfter}pt`,
                  }
                : {},
          },
        },
      },
    ];
  },
});
