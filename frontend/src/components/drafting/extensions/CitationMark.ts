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
        pageStart?: number | null;
        pageEnd?: number | null;
        sourceUri?: string | null;
        court?: string | null;
        reporterCitation?: string | null;
        docketNumber?: string | null;
        authoritative?: boolean | null;
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
  spanning: false,

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
      pageStart: {
        default: null,
        parseHTML: (el) => {
          const value = el.getAttribute("data-page-start");
          return value === null ? null : Number(value);
        },
        renderHTML: (attrs) =>
          attrs.pageStart === null
            ? {}
            : { "data-page-start": String(attrs.pageStart) },
      },
      pageEnd: {
        default: null,
        parseHTML: (el) => {
          const value = el.getAttribute("data-page-end");
          return value === null ? null : Number(value);
        },
        renderHTML: (attrs) =>
          attrs.pageEnd === null
            ? {}
            : { "data-page-end": String(attrs.pageEnd) },
      },
      sourceUri: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-source-uri"),
        renderHTML: (attrs) =>
          attrs.sourceUri ? { "data-source-uri": String(attrs.sourceUri) } : {},
      },
      court: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-court"),
        renderHTML: (attrs) =>
          attrs.court ? { "data-court": String(attrs.court) } : {},
      },
      reporterCitation: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-reporter-citation"),
        renderHTML: (attrs) =>
          attrs.reporterCitation
            ? { "data-reporter-citation": String(attrs.reporterCitation) }
            : {},
      },
      docketNumber: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-docket-number"),
        renderHTML: (attrs) =>
          attrs.docketNumber
            ? { "data-docket-number": String(attrs.docketNumber) }
            : {},
      },
      authoritative: {
        default: null,
        parseHTML: (el) => {
          const value = el.getAttribute("data-authoritative");
          return value === null ? null : value === "true";
        },
        renderHTML: (attrs) =>
          attrs.authoritative === null
            ? {}
            : { "data-authoritative": String(attrs.authoritative) },
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
    const citationId = String(HTMLAttributes["data-citation-id"] ?? "");
    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        class: "citation-mark",
        role: "button",
        tabindex: "0",
        "aria-expanded": "false",
        "aria-label": `Citation ${citationId}, show source preview`,
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
