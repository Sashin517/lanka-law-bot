/**
 * EditHighlightMark — Custom Tiptap mark for diff highlighting.
 *
 * Used by the "Show Edits" toggle to visually indicate insertions,
 * deletions, and modifications relative to a previous document version.
 *
 * Renders using CSS classes defined in globals.css (@layer base):
 *   - `.edit-highlight--insertion`    → green background
 *   - `.edit-highlight--deletion`     → red + strikethrough
 *   - `.edit-highlight--modification` → gold background
 *
 * @module components/drafting/extensions/EditHighlightMark
 */

import { Mark, mergeAttributes } from "@tiptap/core";

export interface EditHighlightMarkOptions {
  HTMLAttributes: Record<string, string>;
}

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    editHighlightMark: {
      /**
       * Apply an edit highlight mark to the current selection.
       */
      setEditHighlight: (attrs: {
        editId: string;
        editType: "insertion" | "deletion" | "modification";
        versionNumber: number;
        timestamp?: string;
        color?: string;
      }) => ReturnType;
      /**
       * Remove all edit highlight marks from the current selection.
       */
      unsetEditHighlight: () => ReturnType;
      /**
       * Remove ALL edit highlight marks from the entire document.
       * Used when toggling "Show Edits" off.
       */
      clearAllEditHighlights: () => ReturnType;
    };
  }
}

/**
 * Map editType → CSS class for styling via globals.css.
 *
 * ProseMirror marks render as DOM elements, not React components,
 * so Tailwind utility classes can't be applied — we use plain CSS.
 */
function editTypeToClass(
  editType: string,
): string {
  switch (editType) {
    case "insertion":
      return "edit-highlight--insertion";
    case "deletion":
      return "edit-highlight--deletion";
    case "modification":
      return "edit-highlight--modification";
    default:
      return "edit-highlight--modification";
  }
}

export const EditHighlightMark = Mark.create<EditHighlightMarkOptions>({
  name: "editHighlight",

  // Allow multiple edit highlights to coexist with other marks
  inclusive: false,

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      editId: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-edit-id"),
        renderHTML: (attrs) => ({
          "data-edit-id": attrs.editId as string,
        }),
      },
      editType: {
        default: "modification",
        parseHTML: (el) => el.getAttribute("data-edit-type"),
        renderHTML: (attrs) => ({
          "data-edit-type": attrs.editType as string,
        }),
      },
      versionNumber: {
        default: 0,
        parseHTML: (el) =>
          parseInt(el.getAttribute("data-version-number") ?? "0", 10),
        renderHTML: (attrs) => ({
          "data-version-number": String(attrs.versionNumber),
        }),
      },
      timestamp: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-timestamp"),
        renderHTML: (attrs) => ({
          "data-timestamp": (attrs.timestamp as string) ?? "",
        }),
      },
      color: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-edit-color"),
        renderHTML: (attrs) =>
          attrs.color ? { "data-edit-color": String(attrs.color) } : {},
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: "span[data-edit-id]",
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const editType = (HTMLAttributes["data-edit-type"] as string) ?? "modification";
    const cssClass = editTypeToClass(editType);

    return [
      "span",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        class: `edit-highlight ${cssClass}`,
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setEditHighlight:
        (attrs) =>
        ({ commands }) => {
          return commands.setMark(this.name, {
            ...attrs,
            timestamp: attrs.timestamp ?? new Date().toISOString(),
          });
        },
      unsetEditHighlight:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name);
        },
      clearAllEditHighlights:
        () =>
        ({ tr, dispatch }) => {
          if (!dispatch) return true;

          const { doc } = tr;
          const markType = this.type;

          doc.descendants((node, pos) => {
            if (!node.isText) return;
            const marks = node.marks.filter((m) => m.type === markType);
            for (const mark of marks) {
              tr.removeMark(pos, pos + node.nodeSize, mark);
            }
          });

          dispatch(tr);
          return true;
        },
    };
  },
});
