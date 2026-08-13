"use client";

import { Eye } from "lucide-react";

export interface ShowEditsLegendProps {
  currentVersionNumber: number;
  changeCount: number;
}

export function ShowEditsLegend({
  currentVersionNumber,
  changeCount,
}: ShowEditsLegendProps) {
  return (
    <div
      className="flex items-center justify-between border-b border-app-accent/20 bg-app-accent/5 px-5 py-2 text-[11px] text-app-tertiary"
      role="status"
      aria-live="polite"
    >
      <span className="flex items-center gap-2">
        <Eye size={13} className="text-app-accent" />
        Comparing Version 1 with Version {currentVersionNumber}. The document is
        read-only.
      </span>
      <span className="flex items-center gap-3">
        <LegendSwatch className="bg-app-success/20 border-app-success/60" label="Inserted" />
        <LegendSwatch className="bg-app-danger/15 border-app-danger/50" label="Deleted" strike />
        <LegendSwatch className="bg-app-accent/20 border-app-accent/60" label="Modified" />
        <span className="text-app-subtle">
          {changeCount} change{changeCount === 1 ? "" : "s"}
        </span>
      </span>
    </div>
  );
}

function LegendSwatch({
  className,
  label,
  strike = false,
}: {
  className: string;
  label: string;
  strike?: boolean;
}) {
  return (
    <span className={`flex items-center gap-1 ${strike ? "line-through" : ""}`}>
      <span className={`h-2.5 w-2.5 rounded-sm border-b-2 ${className}`} />
      {label}
    </span>
  );
}
