"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

import { useThemeStore } from "@/store/themeStore";

const subscribeToHydration = () => () => {};

export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const hydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
  const displayedTheme = hydrated ? theme : "dark";
  const nextTheme = displayedTheme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`theme-toggle flex size-10 shrink-0 items-center justify-center rounded-full border border-app-border/70 bg-app-elevated text-app-secondary transition hover:bg-app-hover hover:text-app-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/70 ${className}`.trim()}
      aria-label={`Switch to ${nextTheme} theme`}
      title={`Switch to ${nextTheme} theme`}
    >
      {displayedTheme === "dark" ? (
        <Sun aria-hidden="true" size={18} />
      ) : (
        <Moon aria-hidden="true" size={18} />
      )}
    </button>
  );
}
