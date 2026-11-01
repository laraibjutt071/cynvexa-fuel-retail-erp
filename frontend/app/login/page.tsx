"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import { ApiError } from "@/lib/api";
import { AtomBackground } from "@/components/decor/AtomBackground";
import { Particles } from "@/components/decor/Particles";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const { language, setLanguage, t } = useLanguage();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error.somethingWrong"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="relative flex flex-1 items-center justify-center overflow-hidden px-4">
      <Particles count={28} />
      <AtomBackground className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-70" />
      <AtomBackground className="hidden -left-16 -top-16 scale-[0.45] opacity-30 sm:block" />
      <AtomBackground className="hidden -bottom-20 -right-20 scale-[0.55] opacity-25 md:block" />

      <div className="relative z-10 w-full max-w-sm animate-fade-slide-up p-4">
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={() => setLanguage(language === "en" ? "ur" : "en")}
            className="rounded-full border border-border px-3 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-surface-elevated hover:text-ink"
          >
            {language === "en" ? "Roman Urdu" : "English"}
          </button>
        </div>
        <h1 className="text-xl font-semibold text-ink">{t("login.title")}</h1>
        <p className="mt-1 text-sm text-ink-soft">{t("login.subtitle")}</p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-ink">
              {t("login.email")}
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-ink shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-ink">
              {t("login.password")}
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-ink shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-brand-500 px-3 py-2 text-sm font-medium text-white transition-all hover:bg-brand-600 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? t("login.signingIn") : t("login.signIn")}
          </button>

          <p className="text-center text-sm text-ink-soft">
            <Link href="/register" className="text-accent hover:underline">
              {t("login.noAccount")}
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}
