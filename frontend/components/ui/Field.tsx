import { type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, useId } from "react";

/** Label + control + helper/error text, wired together with a stable id
 * for accessibility. Every data-entry field in the app should go through
 * this (or Select below) rather than a bare labelless input. */
export function Field({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {required && <span className="ml-0.5 text-danger-600">*</span>}
      </label>
      {children(id)}
      {hint && !error && <p className="text-xs text-ink-faint">{hint}</p>}
      {error && (
        <p role="alert" className="text-xs font-medium text-danger-600">
          {error}
        </p>
      )}
    </div>
  );
}

const inputClasses =
  "w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:bg-surface-muted disabled:text-ink-faint";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  const { invalid, className = "", ...rest } = props;
  return <input className={`${inputClasses} ${invalid ? "border-danger-600" : ""} ${className}`} {...rest} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  const { className = "", ...rest } = props;
  return <select className={`${inputClasses} ${className}`} {...rest} />;
}
