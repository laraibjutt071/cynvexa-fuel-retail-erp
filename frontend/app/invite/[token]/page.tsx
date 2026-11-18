"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { Fuel, Lock, Eye, EyeOff, CircleCheck, CircleX } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { apiJson, ApiError } from "@/lib/api";
import type { InvitationPreview } from "@/lib/types";

export default function AcceptInvitationPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { acceptInvitation } = useAuth();

  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(true);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setPreview(await apiJson<InvitationPreview>(`/invitations/${token}/preview`));
      } catch {
        setPreview({ valid: false, reason: "This invitation link is invalid.", organization_name: "", email: "", full_name: "", role_name: "", station_name: null });
      } finally {
        setLoadingPreview(false);
      }
    })();
  }, [token]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await acceptInvitation(token, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#070b14] px-4 py-10">
      <div className="w-full max-w-sm animate-fade-slide-up">
        <div className="mb-6 flex flex-col items-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-lg shadow-brand-500/30">
            <Fuel className="h-6 w-6 text-white" />
          </div>
          <h1 className="mt-4 text-2xl font-bold text-ink">CYNVEXA</h1>
        </div>

        <div className="rounded-[26px] bg-gradient-to-br from-brand-400/40 via-accent/25 to-brand-700/40 p-[1px] shadow-2xl shadow-black/50">
          <div className="rounded-[25px] bg-surface/85 p-7 backdrop-blur-xl">
            {loadingPreview ? (
              <p className="py-6 text-center text-sm text-ink-soft">Checking your invitation…</p>
            ) : !preview?.valid ? (
              <div className="flex flex-col items-center gap-3 py-4 text-center">
                <CircleX className="h-8 w-8 text-danger-600" aria-hidden />
                <h2 className="text-lg font-semibold text-ink">Invitation not available</h2>
                <p className="text-sm text-ink-soft">{preview?.reason ?? "This invitation link is invalid."}</p>
              </div>
            ) : (
              <>
                <div className="mb-5 flex items-start gap-3">
                  <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-success-600" aria-hidden />
                  <div>
                    <h2 className="text-lg font-semibold text-ink">Join {preview.organization_name}</h2>
                    <p className="mt-1 text-sm text-ink-soft">
                      {preview.full_name} ({preview.email}) is invited as{" "}
                      <span className="font-medium text-ink">{preview.role_name}</span>
                      {preview.station_name ? <> at {preview.station_name}</> : null}.
                    </p>
                  </div>
                </div>

                <form className="space-y-4" onSubmit={handleSubmit}>
                  <div>
                    <label htmlFor="password" className="block text-sm font-medium text-ink">
                      Choose a password
                    </label>
                    <div className="relative mt-1.5 flex items-center rounded-lg border border-border bg-surface-muted shadow-sm">
                      <Lock className="ml-3 h-4 w-4 shrink-0 text-ink-faint" aria-hidden />
                      <input
                        id="password"
                        type={showPassword ? "text" : "password"}
                        required
                        minLength={10}
                        autoComplete="new-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="block w-full border-0 bg-transparent px-2.5 py-2.5 pr-10 text-sm text-ink placeholder:text-ink-faint focus:outline-none"
                        placeholder="At least 10 characters"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        tabIndex={-1}
                        className="absolute inset-y-0 right-0 flex items-center px-3 text-ink-faint transition-colors hover:text-ink-soft"
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                      </button>
                    </div>
                  </div>

                  {error && (
                    <p role="alert" className="rounded-lg bg-danger-50 px-3 py-2.5 text-sm text-danger-600">
                      {error}
                    </p>
                  )}

                  <button
                    type="submit"
                    disabled={submitting}
                    className="btn-shine w-full rounded-lg bg-gradient-to-r from-brand-500 to-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:shadow-brand-500/40 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none"
                  >
                    {submitting ? "Setting up your account…" : "Accept & sign in"}
                  </button>
                </form>
              </>
            )}
          </div>
        </div>

        <footer className="mt-8 text-center text-xs text-ink-faint">CYNVEXA Fuel Retail ERP</footer>
      </div>
    </main>
  );
}
