/**
 * Explicit query modes matching the backend QueryMode enum.
 *
 * The user selects a mode via buttons in the ChatInputBar.
 * If no button is active, the default is "quick_qa".
 */

export type QueryMode =
  | "quick_qa"
  | "deep_research"
  | "drafting"
  | "review"
  | "reasoning";

export interface ModeOption {
  value: QueryMode;
  label: string;
  /** Lucide icon component name — resolved in the ChatInputBar. */
  icon: string;
}

/**
 * Mode button definitions for the ChatInputBar.
 *
 * "quick_qa" is the implicit default when no button is active,
 * so it is NOT included here as a toggleable button.
 */
export const QUERY_MODES: ModeOption[] = [
  { value: "deep_research", label: "Deep Research", icon: "Telescope" },
  { value: "drafting", label: "Draft", icon: "PenTool" },
  { value: "review", label: "Review", icon: "FileSearch" },
  { value: "reasoning", label: "Reasoning", icon: "Scale" },
];
