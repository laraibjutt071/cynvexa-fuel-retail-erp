import { Check } from "lucide-react";

export interface Step {
  label: string;
  description?: string;
}

interface ProgressStepsProps {
  steps: Step[];
  currentStep: number;
  /** Indices of steps that are genuinely finished (backed by real data -
   * e.g. a shift actually closed, a reconciliation actually recorded),
   * not just "the user has clicked this tab before". When provided, a
   * step is only shown with a checkmark if its index is in this set -
   * `currentStep` then only controls which step is highlighted as
   * active, never which ones read as done. Omit this prop to keep the
   * older "every step before the active one is complete" behavior for
   * callers that don't have a real completion signal to give. */
  completedSteps?: Set<number>;
}

export function ProgressSteps({ steps, currentStep, completedSteps }: ProgressStepsProps) {
  return (
    <nav aria-label="Progress" className="flex items-center gap-2">
      {steps.map((step, i) => {
        const isComplete = completedSteps ? completedSteps.has(i) : i < currentStep;
        const isCurrent = i === currentStep;
        return (
          <div key={i} className="flex items-center gap-2">
            {i > 0 && (
              <div
                className={`h-px w-6 sm:w-10 ${isComplete ? "bg-brand-500" : "bg-border"}`}
              />
            )}
            <div className="flex items-center gap-2">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition-colors ${
                  isComplete
                    ? "bg-brand-500 text-white"
                    : isCurrent
                      ? "border-2 border-brand-500 bg-brand-50 text-brand-400"
                      : "border border-border bg-surface-muted text-ink-faint"
                }`}
              >
                {isComplete ? <Check className="h-3.5 w-3.5" /> : i + 1}
              </div>
              <div className="hidden sm:block">
                <p
                  className={`text-xs font-medium ${
                    isCurrent ? "text-ink" : isComplete ? "text-ink-soft" : "text-ink-faint"
                  }`}
                >
                  {step.label}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </nav>
  );
}
