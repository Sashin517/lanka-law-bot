/**
 * CitationMark — Custom Tiptap mark for inline legal citation rendering.
 *
 * Renders as a styled <span> with a gold superscript citation anchor
 * (e.g. [LAW-1], [DOC-2]). On hover, downstream components can use
 * the `data-citation-id` attribute to show the CitationPreviewPopover.
 *
 * @module components/drafting/extensions/CitationMark
 */

import { Mark, mergeAttributes } from "@tiptap/core";

export interface CitationMarkOptions {
  /** HTML tag to render the citation as. */
  HTMLAttributes: Record<string, string>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    citationMark: {
      /**
       * Set a citation mark on the current selection.
       */
      setCitation: (attrs: {
        citationId: string;
        sourceType: string;
        title: string;
        section?: string | null;
        excerpt?: string;
      }) => ReturnType;
      /**
       * Remove citation mark from the current selection.
       */
      unsetCitation: () => ReturnType;
    };
  }
}

export const CitationMark = Mark.create<CitationMarkOptions>({
  name: "citationMark",

  // Citations should not overlap with each other
  excludes: "citationMark",

  // Allow citations inside other inline marks (bold, italic, etc.)
  inclusive: false,

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      citationId: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-citation-id"),
        renderHTML: (attrs) => ({
          "data-citation-id": attrs.citationId as string,
        }),
      },
      sourceType: {
        default: "legal_authority",
        parseHTML: (el) => el.getAttribute("data-source-type"),
        renderHTML: (attrs) => ({
          "data-source-type": attrs.sourceType as string,
        }),
      },
      title: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-title"),
        renderHTML: (attrs) => ({
          "data-title": attrs.title as string,
        }),
      },
      section: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-section"),
        renderHTML: (attrs) => ({
          "data-section": (attrs.section as string) ?? "",
        }),
      },
      excerpt: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-excerpt"),
        renderHTML: (attrs) => ({
          "data-excerpt": attrs.excerpt as string,
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: "span[data-citation-id]",
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        class: "citation-mark",
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setCitation:
        (attrs) =>
        ({ commands }) => {
          return commands.setMark(this.name, attrs);
        },
      unsetCitation:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
    };
  },
});
