"use client";

import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "./Button";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  /** Footer actions — if omitted, only the close button in the header is shown. */
  footer?: ReactNode;
  /** Max width class. Defaults to "max-w-md". */
  size?: "sm" | "md" | "lg" | "xl";
}

const SIZE_MAP: Record<string, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
};

export function Dialog({ open, onClose, title, description, children, footer, size = "md" }: DialogProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        className={`relative w-full ${SIZE_MAP[size]} animate-fade-slide-up rounded-xl border border-border bg-surface shadow-2xl`}
      >
        <div className="flex items-start justify-between border-b border-border px-5 py-4">
          <div>
            <h2 id="dialog-title" className="text-base font-semibold text-ink">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-sm text-ink-soft">{description}</p>}
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-ink-soft transition-colors hover:bg-surface-elevated hover:text-ink"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  confirmVariant?: "primary" | "danger";
  busy?: boolean;
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  confirmVariant = "danger",
  busy,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant={confirmVariant} size="sm" onClick={onConfirm} busy={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm text-ink-soft">{description}</p>
    </Dialog>
  );
}

interface ReasonDialogProps {
  open: boolean;
  onClose: () => void;
  /** Receives the trimmed, non-empty reason text the user entered. */
  onSubmit: (reason: string) => void;
  title: string;
  description?: string;
  label?: string;
  placeholder?: string;
  confirmLabel?: string;
  confirmVariant?: "primary" | "danger";
  busy?: boolean;
  /** Server-side validation error from the last submit attempt, if any. */
  error?: string | null;
}

/**
 * Replaces window.prompt() for financial/audit-relevant actions that need
 * a short, required explanation (reject an expense, reject a reading
 * correction, etc.) - a native prompt() gives no room for a label,
 * placeholder, validation, or loading state, and some mobile browsers
 * block it outright.
 */
export function ReasonDialog({
  open,
  onClose,
  onSubmit,
  title,
  description,
  label = "Reason",
  placeholder = "Explain why...",
  confirmLabel = "Submit",
  confirmVariant = "danger",
  busy,
  error,
}: ReasonDialogProps) {
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (open) setReason("");
  }, [open]);

  const trimmed = reason.trim();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant={confirmVariant}
            size="sm"
            onClick={() => trimmed && onSubmit(trimmed)}
            disabled={!trimmed}
            busy={busy}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <label className="block text-sm font-medium text-ink">
        {label}
        <textarea
          autoFocus
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={placeholder}
          rows={3}
          className="mt-1.5 block w-full rounded-lg border border-border bg-surface-muted px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
        />
      </label>
      {error && <p className="mt-2 text-sm text-danger-600">{error}</p>}
    </Dialog>
  );
}
