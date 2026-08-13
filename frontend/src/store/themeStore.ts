/** Persisted application color-theme preference. */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export const THEME_STORAGE_KEY = "lankalawbot-theme";

export type Theme = "dark" | "light";

interface ThemeState {
  theme: Theme;
}

interface ThemeActions {
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

export type ThemeStore = ThemeState & ThemeActions;

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      theme: "dark",
      setTheme: (theme) => set({ theme }),
      toggleTheme: () =>
        set((state) => ({ theme: state.theme === "dark" ? "light" : "dark" })),
    }),
    {
      name: THEME_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: ({ theme }) => ({ theme }),
      version: 1,
    },
  ),
);
