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
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

import type { DiffChange, DiffOverlay } from "@/types/drafting";

export type EditHighlightOverlayMeta =
  | { action: "show"; overlay: DiffOverlay }
  | { action: "clear" };

export const editHighlightOverlayKey = new PluginKey<DecorationSet>(
  "editHighlightOverlay",
);

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
      /** Render a non-mutating read-only comparison overlay. */
      showDiffOverlay: (overlay: DiffOverlay) => ReturnType;
      /** Remove the comparison overlay without changing document JSON. */
      clearDiffOverlay: () => ReturnType;
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
      showDiffOverlay:
        (overlay) =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            const meta: EditHighlightOverlayMeta = { action: "show", overlay };
            dispatch(tr.setMeta(editHighlightOverlayKey, meta));
          }
          return true;
        },
      clearDiffOverlay:
        () =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            const meta: EditHighlightOverlayMeta = { action: "clear" };
            dispatch(tr.setMeta(editHighlightOverlayKey, meta));
          }
          return true;
        },
    };
  },

  addProseMirrorPlugins() {
    return [
      new Plugin<DecorationSet>({
        key: editHighlightOverlayKey,
        state: {
          init: () => DecorationSet.empty,
          apply: (transaction, previous) => {
            const meta = transaction.getMeta(
              editHighlightOverlayKey,
            ) as EditHighlightOverlayMeta | undefined;
            if (meta?.action === "clear") return DecorationSet.empty;
            if (meta?.action === "show") {
              return createOverlayDecorations(transaction.doc, meta.overlay);
            }
            if (transaction.docChanged) return DecorationSet.empty;
            return previous.map(transaction.mapping, transaction.doc);
          },
        },
        props: {
          decorations: (state) =>
            editHighlightOverlayKey.getState(state) ?? DecorationSet.empty,
        },
      }),
    ];
  },
});

function createOverlayDecorations(
  documentNode: ProseMirrorNode,
  overlay: DiffOverlay,
): DecorationSet {
  const decorations: Decoration[] = [];
  overlay.changes.forEach((change, index) => {
    const editId = `${overlay.fromVersionId}:${overlay.toVersionId}:${index}`;
    const attributes = decorationAttributes(change, editId, overlay);
    const from = clampPosition(change.position.from, documentNode);
    const to = clampPosition(change.position.to, documentNode);

    if (change.type === "delete" || change.type === "replace") {
      if (change.oldContent) {
        decorations.push(
          Decoration.widget(
            from,
            () => deletionWidget(change.oldContent!, attributes),
            { key: `${editId}:deletion`, side: -1 },
          ),
        );
      }
    }

    if (change.type !== "delete") {
      if (to > from) {
        decorations.push(
          Decoration.inline(from, to, {
            ...attributes,
            class: `edit-highlight ${highlightClass(change.type)}`,
          }),
        );
      } else if (change.newContent) {
        decorations.push(
          Decoration.widget(
            from,
            () => insertionWidget(change.newContent!, attributes, change.type),
            { key: `${editId}:insertion`, side: 1 },
          ),
        );
      }
    }
  });
  return DecorationSet.create(documentNode, decorations);
}

function decorationAttributes(
  change: DiffChange,
  editId: string,
  overlay: DiffOverlay,
): Record<string, string> {
  const editType =
    change.type === "insert"
      ? "insertion"
      : change.type === "delete"
        ? "deletion"
        : "modification";
  return {
    "data-diff-overlay": "true",
    "data-edit-id": editId,
    "data-edit-type": editType,
    "data-version-number": String(overlay.versionNumber),
    "data-timestamp": overlay.timestamp,
    title: overlayTitle(change, overlay.versionNumber),
  };
}

function deletionWidget(
  content: string,
  attributes: Record<string, string>,
): HTMLElement {
  const element = globalThis.document.createElement("span");
  applyAttributes(element, attributes);
  element.className =
    "edit-highlight edit-highlight--deletion edit-highlight--deletion-widget";
  element.textContent = visibleWidgetText(content, "Deleted paragraph break");
  element.setAttribute("role", "note");
  element.setAttribute("aria-label", `Deleted text: ${content}`);
  return element;
}

function insertionWidget(
  content: string,
  attributes: Record<string, string>,
  changeType: DiffChange["type"],
): HTMLElement {
  const element = globalThis.document.createElement("span");
  applyAttributes(element, attributes);
  element.className = `edit-highlight ${highlightClass(changeType)}`;
  element.textContent = visibleWidgetText(content, "Inserted paragraph break");
  element.setAttribute("role", "note");
  return element;
}

function applyAttributes(
  element: HTMLElement,
  attributes: Record<string, string>,
): void {
  Object.entries(attributes).forEach(([name, value]) => {
    element.setAttribute(name, value);
  });
}

function visibleWidgetText(content: string, whitespaceLabel: string): string {
  return content.trim().length > 0 ? content : `[${whitespaceLabel}]`;
}

function highlightClass(changeType: DiffChange["type"]): string {
  switch (changeType) {
    case "insert":
      return "edit-highlight--insertion";
    case "delete":
      return "edit-highlight--deletion";
    default:
      return "edit-highlight--modification";
  }
}

function overlayTitle(change: DiffChange, versionNumber: number): string {
  const label =
    change.type === "insert"
      ? "Inserted"
      : change.type === "delete"
        ? "Deleted"
        : "Modified";
  return `${label} since Version 1 (current Version ${versionNumber})`;
}

function clampPosition(position: number, documentNode: ProseMirrorNode): number {
  return Math.max(0, Math.min(position, documentNode.content.size));
}
