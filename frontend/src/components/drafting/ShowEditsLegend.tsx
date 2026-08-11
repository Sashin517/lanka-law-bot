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
      className="flex items-center justify-between border-b border-[#D4AF37]/20 bg-[#D4AF37]/5 px-5 py-2 text-[11px] text-slate-300"
      role="status"
      aria-live="polite"
    >
      <span className="flex items-center gap-2">
        <Eye size={13} className="text-[#D4AF37]" />
        Comparing Version 1 with Version {currentVersionNumber}. The document is
        read-only.
      </span>
      <span className="flex items-center gap-3">
        <LegendSwatch className="bg-emerald-500/20 border-emerald-500/60" label="Inserted" />
        <LegendSwatch className="bg-red-500/15 border-red-500/50" label="Deleted" strike />
        <LegendSwatch className="bg-[#D4AF37]/20 border-[#D4AF37]/60" label="Modified" />
        <span className="text-slate-500">
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
