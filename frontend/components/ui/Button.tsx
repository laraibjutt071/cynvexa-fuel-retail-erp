import { type ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

const VARIANT_CLASSES: Record<Variant, string> = {
  // Subtle gradient + brand-tinted shadow gives the primary action real
  // weight instead of a flat fill - same visual language as the login/
  // register submit buttons (app/login/page.tsx's btn-shine treatment),
  // now shared by every primary button in the app.
  primary:
    "bg-gradient-to-b from-brand-400 to-brand-600 text-white shadow-md shadow-brand-500/20 hover:shadow-lg hover:shadow-brand-500/30 hover:from-brand-400 hover:to-brand-500 focus-visible:ring-brand-500",
  secondary: "bg-surface text-ink border border-border hover:bg-surface-elevated focus-visible:ring-brand-500",
  // danger-700 doesn't exist as a token (see app/globals.css) - darken via
  // opacity instead of a hardcoded Tailwind red so it still tracks the
  // danger token if that palette ever changes.
  danger: "bg-danger-600 text-white shadow-md shadow-danger-600/20 hover:bg-danger-600/85 focus-visible:ring-danger-600",
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
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 disabled:shadow-none ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {busy && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />
      )}
      {children}
    </button>
  );
});
