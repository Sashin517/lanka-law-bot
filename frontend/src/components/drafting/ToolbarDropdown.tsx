"use client";

import { Check, ChevronDown } from "lucide-react";
import {
  useEffect,
  useId,
  useCallback,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

export interface ToolbarDropdownOption {
  value: string;
  label: string;
}

export interface ToolbarDropdownProps {
  label: string;
  value: string;
  options: readonly ToolbarDropdownOption[];
  disabled?: boolean;
  className?: string;
  onChange: (value: string) => void;
}

interface MenuPosition {
  left: number;
  top: number;
  width: number;
}

export function ToolbarDropdown({
  label,
  value,
  options,
  disabled = false,
  className = "",
  onChange,
}: ToolbarDropdownProps) {
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<MenuPosition | null>(null);
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const selectedOption = options[selectedIndex];

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const bounds = trigger.getBoundingClientRect();
    const width = Math.max(bounds.width, 160);
    const viewportWidth = globalThis.innerWidth;
    const viewportHeight = globalThis.innerHeight;
    const estimatedHeight = Math.min(options.length * 36 + 16, 280);
    const left = Math.max(
      8,
      Math.min(bounds.left, viewportWidth - width - 8),
    );
    const belowTop = bounds.bottom + 6;
    const top =
      belowTop + estimatedHeight <= viewportHeight - 8
        ? belowTop
        : Math.max(8, bounds.top - estimatedHeight - 6);
    setPosition({ left, top, width });
  }, [options.length]);

  const openMenu = useCallback(() => {
    if (disabled || options.length === 0) return;
    updatePosition();
    setOpen(true);
  }, [disabled, options.length, updatePosition]);

  const closeMenu = useCallback((restoreFocus = false) => {
    setOpen(false);
    setPosition(null);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        !triggerRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        closeMenu();
      }
    };
    const handleViewportChange = () => updatePosition();
    globalThis.document.addEventListener("pointerdown", handlePointerDown);
    globalThis.addEventListener("resize", handleViewportChange);
    globalThis.addEventListener("scroll", handleViewportChange, true);
    return () => {
      globalThis.document.removeEventListener("pointerdown", handlePointerDown);
      globalThis.removeEventListener("resize", handleViewportChange);
      globalThis.removeEventListener("scroll", handleViewportChange, true);
    };
  }, [closeMenu, open, updatePosition]);

  useEffect(() => {
    if (!open || !position) return;
    const selected = menuRef.current?.querySelector<HTMLElement>(
      `[data-option-index="${selectedIndex}"]`,
    );
    selected?.focus();
  }, [open, position, selectedIndex]);

  const handleTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    openMenu();
  };

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const activeIndex = Number(
      (globalThis.document.activeElement as HTMLElement | null)?.dataset
        .optionIndex ?? selectedIndex,
    );
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown") {
      nextIndex = (activeIndex + 1) % options.length;
    } else if (event.key === "ArrowUp") {
      nextIndex = (activeIndex - 1 + options.length) % options.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = options.length - 1;
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeMenu(true);
      return;
    } else if (event.key === "Tab") {
      closeMenu();
      return;
    }
    if (nextIndex == null) return;
    event.preventDefault();
    menuRef.current
      ?.querySelector<HTMLElement>(`[data-option-index="${nextIndex}"]`)
      ?.focus();
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        title={label}
        disabled={disabled}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={handleTriggerKeyDown}
        className={`flex h-8 shrink-0 items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-2.5 text-[11px] font-medium text-slate-700 shadow-sm outline-none transition hover:border-slate-300 hover:bg-slate-50 focus-visible:border-[#B58B16]/60 focus-visible:ring-2 focus-visible:ring-[#D4AF37]/18 disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
      >
        <span className="truncate">{selectedOption?.label ?? label}</span>
        <ChevronDown
          size={13}
          aria-hidden="true"
          className={`shrink-0 text-slate-400 transition-transform ${
            open ? "rotate-180 text-slate-700" : ""
          }`}
        />
      </button>

      {open && position &&
        createPortal(
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label={label}
            onKeyDown={handleMenuKeyDown}
            className="fixed z-[120] max-h-[280px] overflow-y-auto rounded-lg border border-slate-200 bg-white/98 p-1.5 shadow-[0_18px_48px_rgba(15,23,42,0.18),0_2px_8px_rgba(15,23,42,0.1)] backdrop-blur-xl chat-scroll"
            style={position}
          >
            {options.map((option, index) => {
              const selected = option.value === value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  data-option-index={index}
                  tabIndex={index === selectedIndex ? 0 : -1}
                  onClick={() => {
                    onChange(option.value);
                    closeMenu(true);
                  }}
                  className={`flex w-full items-center justify-between gap-3 rounded-md px-2.5 py-2 text-left text-xs outline-none transition focus-visible:ring-2 focus-visible:ring-[#B58B16]/30 ${
                    selected
                      ? "bg-[#D4AF37]/13 text-[#7A5B0A]"
                      : "text-slate-700 hover:bg-slate-100 hover:text-slate-950 focus:bg-slate-100"
                  }`}
                >
                  <span>{option.label}</span>
                  <Check
                    size={13}
                    aria-hidden="true"
                    className={selected ? "opacity-100" : "opacity-0"}
                  />
                </button>
              );
            })}
          </div>,
          globalThis.document.body,
        )}
    </>
  );
}
