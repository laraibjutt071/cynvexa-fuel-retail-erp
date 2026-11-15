"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Fuel, ShieldCheck, Gauge, FileBarChart, Lock, Eye, EyeOff } from "lucide-react";
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
  const [showPassword, setShowPassword] = useState(false);
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

  const features = [
    { icon: Gauge, label: t("login.feature.reconciliation") },
    { icon: FileBarChart, label: t("login.feature.credit") },
    { icon: ShieldCheck, label: t("login.feature.reports") },
  ];

  return (
    <main className="relative flex min-h-screen flex-col lg:flex-row">
      {/* Left: brand / marketing panel */}
      <section className="relative hidden w-full overflow-hidden bg-[#0a1120] lg:flex lg:w-1/2 lg:flex-col lg:justify-between lg:p-12">
        <div className="absolute inset-0 bg-gradient-to-br from-brand-700/40 via-[#0a1120] to-[#0a1120]" />
        <Particles count={22} />
        <AtomBackground className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-60" />
        <AtomBackground className="-left-20 -top-20 scale-[0.5] opacity-25" />

        <div className="relative z-10 flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500 shadow-lg shadow-brand-500/30">
            <Fuel className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-bold tracking-tight text-ink">CYNVEXA</span>
        </div>

        <div className="relative z-10 max-w-md">
          <h1 className="text-3xl font-bold leading-tight text-ink sm:text-4xl">
            {t("login.heroTitle")}
          </h1>
          <p className="mt-4 text-base leading-relaxed text-ink-soft">
            {t("login.heroSubtitle")}
          </p>

          <ul className="mt-8 space-y-3">
            {features.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-3 text-sm font-medium text-ink">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-accent">
                  <Icon className="h-4 w-4" />
                </span>
                {label}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative z-10 flex items-center gap-2 text-xs text-ink-faint">
          <Lock className="h-3.5 w-3.5" />
          {t("login.securityNote")}
        </div>
      </section>

      {/* Right: auth form */}
      <section className="relative flex w-full flex-1 items-center justify-center overflow-hidden px-4 py-10 lg:w-1/2">
        <div className="absolute inset-0 lg:hidden">
          <Particles count={18} />
          <AtomBackground className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-70" />
        </div>

        <div className="relative z-10 w-full max-w-sm animate-fade-slide-up">
          <div className="mb-6 flex flex-col items-center lg:hidden">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-500 shadow-lg shadow-brand-500/30">
              <Fuel className="h-6 w-6 text-white" />
            </div>
            <h1 className="mt-4 text-2xl font-bold text-ink">CYNVEXA</h1>
            <p className="mt-1 text-sm text-ink-soft">{t("login.subtitle")}</p>
          </div>

          <div className="card-glow rounded-2xl border border-border bg-surface p-7 shadow-2xl shadow-black/40">
            <div className="mb-5 flex items-start justify-between">
              <div>
                <h2 className="text-xl font-semibold text-ink">{t("login.welcomeBack")}</h2>
                <p className="mt-1 text-sm text-ink-soft">{t("login.subtitle")}</p>
              </div>
              <button
                type="button"
                onClick={() => setLanguage(language === "en" ? "ur" : "en")}
                className="shrink-0 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-surface-elevated hover:text-ink"
              >
                {language === "en" ? "UR" : "EN"}
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
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
                  className="mt-1.5 block w-full rounded-lg border border-border bg-surface-muted px-3 py-2.5 text-sm text-ink shadow-sm placeholder:text-ink-faint transition-shadow focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                  placeholder="you@company.com"
                />
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label htmlFor="password" className="block text-sm font-medium text-ink">
                    {t("login.password")}
                  </label>
                </div>
                <div className="relative mt-1.5">
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="block w-full rounded-lg border border-border bg-surface-muted px-3 py-2.5 pr-10 text-sm text-ink shadow-sm placeholder:text-ink-faint transition-shadow focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    tabIndex={-1}
                    className="absolute inset-y-0 right-0 flex items-center px-3 text-ink-faint transition-colors hover:text-ink-soft"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
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
                className="w-full rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:bg-brand-600 hover:shadow-brand-500/40 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none"
              >
                {submitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    {t("login.signingIn")}
                  </span>
                ) : (
                  t("login.signIn")
                )}
              </button>
            </form>
          </div>

          <p className="mt-5 text-center text-sm text-ink-soft">
            <Link href="/register" className="text-accent transition-colors hover:text-brand-400 hover:underline">
              {t("login.noAccount")}
            </Link>
          </p>

          <footer className="mt-8 text-center text-xs text-ink-faint">
            CYNVEXA Fuel Retail ERP
          </footer>
        </div>
      </section>
    </main>
  );
}
