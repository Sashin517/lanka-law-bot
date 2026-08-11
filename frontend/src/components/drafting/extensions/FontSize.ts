import { Extension } from "@tiptap/core";

import {
  isAllowedFontSize,
  parsePointValue,
} from "@/lib/drafting/formatting";

/** Stores controlled point sizes on the existing TextStyle mark. */
export const FontSize = Extension.create({
  name: "fontSize",

  addGlobalAttributes() {
    return [
      {
        types: ["textStyle"],
        attributes: {
          fontSize: {
            default: null,
            parseHTML: (element) => {
              const size = parsePointValue(element.style.fontSize);
              return isAllowedFontSize(size) ? size : null;
            },
            renderHTML: (attributes) =>
              isAllowedFontSize(attributes.fontSize)
                ? {
                    "data-font-size": String(attributes.fontSize),
                    style: `font-size: ${attributes.fontSize}pt`,
                  }
                : {},
          },
        },
      },
    ];
  },
});
