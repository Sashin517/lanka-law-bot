"use client";

import {
  AlertTriangle,
  Download,
  FileText,
  Loader2,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { ExportArtifact } from "@/lib/drafting/exportService";
import type {
  DocumentVersion,
  ExportFormat,
  ExportOptions,
} from "@/types/drafting";
import { DEFAULT_EXPORT_OPTIONS } from "@/types/drafting";

export interface ExportModalProps {
  open: boolean;
  version: DocumentVersion | null;
  title: string;
  author: string;
  onClose: () => void;
  onExported?: (artifact: ExportArtifact) => void;
}

export function ExportModal({
  open,
  version,
  title,
  author,
  onClose,
  onExported,
}: ExportModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [options, setOptions] = useState<ExportOptions>(() => defaultOptions());
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setOptions(defaultOptions());
    setError(null);
    closeButtonRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isExporting) onClose();
      if (event.key !== "Tab") return;
      const dialog = closeButtonRef.current?.closest<HTMLElement>(
        '[role="dialog"]',
      );
      const focusable = dialog?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && globalThis.document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && globalThis.document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    globalThis.document.addEventListener("keydown", handleKeyDown);
    return () => globalThis.document.removeEventListener("keydown", handleKeyDown);
  }, [isExporting, onClose, open]);

  if (!open) return null;

  const handleDownload = async () => {
    if (!version || isExporting) return;
    setIsExporting(true);
    setError(null);
    try {
      const { exportService } = await import("@/lib/drafting/exportService");
      const artifact = await exportService.exportDocument({
        version,
        options,
        title,
        author,
      });
      onExported?.(artifact);
      onClose();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The document could not be exported.",
      );
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isExporting) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="w-full max-w-lg overflow-hidden rounded-xl border border-app-border bg-app-panel shadow-2xl"
      >
        <header className="flex items-start justify-between border-b border-app-border/70 px-5 py-4">
          <div>
            <h2 id={titleId} className="flex items-center gap-2 text-base font-semibold text-app-strong">
              <Download size={17} className="text-app-accent" />
              Export accepted draft
            </h2>
            <p id={descriptionId} className="mt-1 text-xs text-app-muted">
              Version {version?.versionNumber ?? "—"} will be exported without
              pending AI suggestions or Show Edits overlays.
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            disabled={isExporting}
            className="rounded p-1 text-app-muted transition hover:bg-app-hover hover:text-app-strong disabled:opacity-40"
            aria-label="Close export dialog"
          >
            <X size={18} />
          </button>
        </header>

        <div className="space-y-5 p-5">
          <fieldset>
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-app-muted">
              Format
            </legend>
            <div className="grid grid-cols-2 gap-3">
              <FormatOption
                format="docx"
                selected={options.format === "docx"}
                description="Editable Microsoft Word document"
                onSelect={(format) => setOptions((state) => ({ ...state, format }))}
              />
              <FormatOption
                format="pdf"
                selected={options.format === "pdf"}
                description="Print-ready browser-rendered document"
                onSelect={(format) => setOptions((state) => ({ ...state, format }))}
              />
            </div>
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-app-muted">
              Include
            </legend>
            <div className="space-y-2 rounded-lg border border-app-border/60 bg-app-panel-muted/60 p-3">
              <OptionCheckbox
                label="Document metadata"
                checked={options.includeMetadata}
                onChange={(checked) =>
                  setOptions((state) => ({ ...state, includeMetadata: checked }))
                }
              />
              <OptionCheckbox
                label="Sources and citation footnotes"
                checked={options.includeSources}
                onChange={(checked) =>
                  setOptions((state) => ({ ...state, includeSources: checked }))
                }
              />
              <OptionCheckbox
                label="Legal disclaimer"
                checked={options.includeDisclaimer}
                onChange={(checked) =>
                  setOptions((state) => ({ ...state, includeDisclaimer: checked }))
                }
              />
            </div>
          </fieldset>

          <label className="block text-xs font-semibold uppercase tracking-wider text-app-muted">
            Page size
            <select
              value={options.pageSize}
              onChange={(event) =>
                setOptions((state) => ({
                  ...state,
                  pageSize: event.target.value as ExportOptions["pageSize"],
                }))
              }
              className="mt-2 w-full rounded-lg border border-app-border bg-app-panel-muted px-3 py-2.5 text-sm font-normal normal-case tracking-normal text-app-strong outline-none focus:border-app-accent"
            >
              <option value="A4">A4</option>
              <option value="Letter">Letter</option>
            </select>
          </label>

          <div className="flex items-start gap-2 rounded-lg bg-app-success/8 p-3 text-[11px] leading-relaxed text-app-success">
            <ShieldCheck size={14} className="mt-0.5 shrink-0" />
            Export uses the latest immutable accepted version and its matching
            source snapshot.
          </div>

          {error && (
            <p className="flex items-start gap-2 rounded-lg bg-app-danger/10 p-3 text-xs text-app-danger" role="alert">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              {error}
            </p>
          )}
        </div>

        <footer className="flex justify-end gap-3 border-t border-app-border/70 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            disabled={isExporting}
            className="rounded-lg px-4 py-2 text-sm text-app-tertiary transition hover:bg-app-hover disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleDownload()}
            disabled={!version || isExporting}
            className="flex items-center gap-2 rounded-lg bg-app-accent px-4 py-2 text-sm font-semibold text-app-accent-contrast transition hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isExporting ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Download size={15} />
            )}
            {isExporting ? "Generating…" : "Download"}
          </button>
        </footer>
      </section>
    </div>
  );
}

function FormatOption({
  format,
  selected,
  description,
  onSelect,
}: {
  format: ExportFormat;
  selected: boolean;
  description: string;
  onSelect: (format: ExportFormat) => void;
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
        selected
          ? "border-app-accent/60 bg-app-accent/10"
          : "border-app-border bg-app-panel-muted/60 hover:border-app-border"
      }`}
    >
      <input
        type="radio"
        name="export-format"
        value={format}
        checked={selected}
        onChange={() => onSelect(format)}
        className="mt-1 accent-app-accent"
      />
      <span>
        <span className="flex items-center gap-1.5 text-sm font-semibold uppercase text-app-strong">
          <FileText size={14} className="text-app-accent" />
          {format}
        </span>
        <span className="mt-0.5 block text-[10px] text-app-subtle">
          {description}
        </span>
      </span>
    </label>
  );
}

function OptionCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 text-sm text-app-tertiary">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-app-accent"
      />
      {label}
    </label>
  );
}

function defaultOptions(): ExportOptions {
  return {
    ...DEFAULT_EXPORT_OPTIONS,
    margins: { ...DEFAULT_EXPORT_OPTIONS.margins },
  };
}
