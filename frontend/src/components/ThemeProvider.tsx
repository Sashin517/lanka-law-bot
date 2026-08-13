"use client";

import { useEffect } from "react";

import { useThemeStore } from "@/store/themeStore";

/** Keeps the DOM theme and native browser controls in sync with Zustand. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useThemeStore((state) => state.theme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  return children;
}
