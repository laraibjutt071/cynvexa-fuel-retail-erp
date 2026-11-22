"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Fuel,
  ShieldCheck,
  Gauge,
  FileBarChart,
  Lock,
  Eye,
  EyeOff,
  Mail,
  Globe,
  Droplet,
  TrendingUp,
  CircleCheck,
  FileLock2,
  KeyRound,
} from "lucide-react";
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
  const [emailFocused, setEmailFocused] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);

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

  const trustBadges = [
    { icon: FileLock2, label: t("login.trust.encrypted") },
    { icon: KeyRound, label: t("login.trust.roleBased") },
    { icon: CircleCheck, label: t("login.trust.auditReady") },
  ];

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden bg-[#070b14] lg:flex-row">
      {/* Ambient color wash shared by both halves so the split never looks like two separate pages */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_20%_0%,rgba(37,99,235,0.18),transparent),radial-gradient(ellipse_60%_50%_at_100%_100%,rgba(56,189,248,0.12),transparent)]" />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }}
        aria-hidden="true"
      />

      {/* Left: brand / product panel */}
      <section className="relative hidden w-full flex-col justify-between overflow-hidden p-12 lg:flex lg:w-1/2 lg:min-h-screen">
        <Particles count={24} />
        <AtomBackground className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-60" />
        <AtomBackground className="-left-24 -top-24 scale-[0.5] opacity-20" />

        <div className="relative z-10 flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-lg shadow-brand-500/30">
            <Fuel className="h-5 w-5 text-white" />
          </div>
          <span className="text-lg font-bold tracking-tight text-ink">PetroNiq</span>
        </div>

        <div className="relative z-10 max-w-md">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-accent">
            <Droplet className="h-3 w-3" />
            {t("login.badge")}
          </span>

          <h1 className="mt-5 text-3xl font-bold leading-tight text-ink sm:text-4xl">
            {t("login.heroTitle")}
          </h1>
          <p className="mt-4 text-base leading-relaxed text-ink-soft">{t("login.heroSubtitle")}</p>

          <ul className="mt-7 flex flex-wrap gap-2.5">
            {features.map(({ icon: Icon, label }) => (
              <li
                key={label}
                className="card-glow flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3.5 py-2 text-xs font-medium text-ink backdrop-blur-sm"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-accent">
                  <Icon className="h-3.5 w-3.5" />
                </span>
                {label}
              </li>
            ))}
          </ul>

          {/* Floating illustrative dashboard-preview card */}
          <div className="relative mt-10 w-full max-w-sm animate-float-slow">
            <div className="rounded-2xl bg-gradient-to-br from-brand-400/50 via-accent/30 to-brand-700/50 p-[1px] shadow-2xl shadow-black/50">
              <div className="rounded-2xl bg-surface/90 p-4 backdrop-blur-xl">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-xs font-semibold text-ink-soft">{t("login.preview.heading")}</span>
                  <span className="flex items-center gap-1 rounded-full bg-success-100 px-2 py-0.5 text-[10px] font-semibold text-success-600">
                    <span className="h-1.5 w-1.5 rounded-full bg-success-600" />
                    {t("login.preview.statusOpen")}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2.5">
                  <div className="rounded-xl border border-border bg-surface-muted p-2.5">
                    <Droplet className="h-3.5 w-3.5 text-accent" />
                    <p className="mt-1.5 text-sm font-bold text-ink">78%</p>
                    <p className="text-[10px] text-ink-faint">{t("login.preview.tankLevel")}</p>
                  </div>
                  <div className="rounded-xl border border-border bg-surface-muted p-2.5">
                    <TrendingUp className="h-3.5 w-3.5 text-success-600" />
                    <p className="mt-1.5 text-sm font-bold text-ink">+12%</p>
                    <p className="text-[10px] text-ink-faint">{t("login.preview.todaySales")}</p>
                  </div>
                  <div className="rounded-xl border border-border bg-surface-muted p-2.5">
                    <Gauge className="h-3.5 w-3.5 text-brand-400" />
                    <p className="mt-1.5 text-sm font-bold text-ink">3/3</p>
                    <p className="text-[10px] text-ink-faint">{t("login.preview.shiftStatus")}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="relative z-10 flex flex-wrap items-center gap-4 text-xs text-ink-faint">
          <span className="flex items-center gap-1.5">
            <Lock className="h-3.5 w-3.5" />
            {t("login.securityNote")}
          </span>
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
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-lg shadow-brand-500/30">
              <Fuel className="h-6 w-6 text-white" />
            </div>
            <h1 className="mt-4 text-2xl font-bold text-ink">PetroNiq</h1>
            <p className="mt-1 text-sm text-ink-soft">{t("login.subtitle")}</p>
          </div>

          {/* Gradient-ring glass card */}
          <div className="rounded-[26px] bg-gradient-to-br from-brand-400/40 via-accent/25 to-brand-700/40 p-[1px] shadow-2xl shadow-black/50">
            <div className="rounded-[25px] bg-surface/85 p-7 backdrop-blur-xl">
              <div className="mb-5 flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-ink">{t("login.welcomeBack")}</h2>
                  <p className="mt-1 text-sm text-ink-soft">{t("login.subtitle")}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setLanguage(language === "en" ? "ur" : "en")}
                  className="flex shrink-0 items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-surface-elevated hover:text-ink"
                >
                  <Globe className="h-3 w-3" />
                  {language === "en" ? "UR" : "EN"}
                </button>
              </div>

              <form className="space-y-4" onSubmit={handleSubmit}>
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-ink">
                    {t("login.email")}
                  </label>
                  <div
                    className={`relative mt-1.5 flex items-center rounded-lg border bg-surface-muted shadow-sm transition-all ${
                      emailFocused ? "border-brand-500 ring-2 ring-brand-100" : "border-border"
                    }`}
                  >
                    <Mail
                      className={`ml-3 h-4 w-4 shrink-0 transition-colors ${emailFocused ? "text-accent" : "text-ink-faint"}`}
                      aria-hidden
                    />
                    <input
                      id="email"
                      type="email"
                      required
                      autoComplete="username"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      onFocus={() => setEmailFocused(true)}
                      onBlur={() => setEmailFocused(false)}
                      className="block w-full border-0 bg-transparent px-2.5 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none"
                      placeholder={t("login.emailPlaceholder")}
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-sm font-medium text-ink">
                    {t("login.password")}
                  </label>
                  <div
                    className={`relative mt-1.5 flex items-center rounded-lg border bg-surface-muted shadow-sm transition-all ${
                      passwordFocused ? "border-brand-500 ring-2 ring-brand-100" : "border-border"
                    }`}
                  >
                    <Lock
                      className={`ml-3 h-4 w-4 shrink-0 transition-colors ${passwordFocused ? "text-accent" : "text-ink-faint"}`}
                      aria-hidden
                    />
                    <input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      required
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      onFocus={() => setPasswordFocused(true)}
                      onBlur={() => setPasswordFocused(false)}
                      className="block w-full border-0 bg-transparent px-2.5 py-2.5 pr-10 text-sm text-ink placeholder:text-ink-faint focus:outline-none"
                      placeholder={t("login.passwordPlaceholder")}
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
                  className="btn-shine w-full rounded-lg bg-gradient-to-r from-brand-500 to-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:shadow-brand-500/40 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none"
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

              <div className="mt-5 flex items-center justify-center gap-4">
                {trustBadges.map(({ icon: Icon, label }) => (
                  <span key={label} className="flex items-center gap-1 text-[11px] text-ink-faint">
                    <Icon className="h-3 w-3 text-ink-faint" />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <p className="mt-5 text-center text-sm text-ink-soft">
            <Link href="/register" className="text-accent transition-colors hover:text-brand-400 hover:underline">
              {t("login.noAccount")}
            </Link>
          </p>

          <footer className="mt-8 text-center text-xs text-ink-faint">PetroNiq Fuel Retail ERP</footer>
        </div>
      </section>
    </main>
  );
}
