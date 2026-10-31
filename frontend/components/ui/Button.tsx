import { type ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-brand-500 text-white hover:bg-brand-600 focus-visible:ring-brand-500",
  secondary: "bg-surface text-ink border border-border hover:bg-surface-elevated focus-visible:ring-brand-500",
  danger: "bg-danger-600 text-white hover:bg-red-700 focus-visible:ring-danger-600",
  ghost: "bg-transparent text-ink-soft hover:bg-surface-elevated focus-visible:ring-brand-500",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2.5 text-sm",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; busy?: boolean }
>(function Button({ variant = "primary", size = "md", busy, disabled, className = "", children, ...rest }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {busy && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />
      )}
      {children}
    </button>
  );
});
