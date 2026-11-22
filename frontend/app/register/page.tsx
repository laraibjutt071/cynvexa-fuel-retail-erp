"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Building2, Fuel, Globe, KeyRound, Mail, MapPin, User } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import { apiJson, ApiError } from "@/lib/api";
import { AtomBackground } from "@/components/decor/AtomBackground";
import { Particles } from "@/components/decor/Particles";
import type { Plan } from "@/lib/types";

/** Same bordered-icon-input treatment as the login page's email/password
 * fields (app/login/page.tsx) - register previously used a bare
 * `<input>` with no icon and no focus-ring glow, so it read as a plainer,
 * cheaper screen than the page one click away from it. */
function IconField({
  id,
  icon: Icon,
  label,
  children,
}: {
  id: string;
  icon: typeof Mail;
  label: string;
  children: (focused: boolean) => React.ReactNode;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      <div
        className={`relative mt-1.5 flex items-center rounded-lg border bg-surface-muted shadow-sm transition-all ${
          focused ? "border-brand-500 ring-2 ring-brand-100" : "border-border"
        }`}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      >
        <Icon className={`ml-3 h-4 w-4 shrink-0 transition-colors ${focused ? "text-accent" : "text-ink-faint"}`} aria-hidden />
        {children(focused)}
      </div>
    </div>
  );
}

export default function RegisterPage() {
  const { user, loading, register } = useAuth();
  const { language, setLanguage, t } = useLanguage();
  const router = useRouter();

  const [plans, setPlans] = useState<Plan[]>([]);
  const [form, setForm] = useState({
    company_name: "",
    station_name: "Main Station",
    full_name: "",
    email: "",
    password: "",
    plan_code: "starter",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  useEffect(() => {
    apiJson<Plan[]>("/plans")
      .then(setPlans)
      .catch(() => setPlans([]));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(form);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error.somethingWrong"));
    } finally {
      setSubmitting(false);
    }
  }

  const inputClasses = "block w-full border-0 bg-transparent px-2.5 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none";

  return (
    <main className="relative flex flex-1 items-center justify-center overflow-hidden bg-[#070b14] px-4 py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_80%_0%,rgba(37,99,235,0.18),transparent),radial-gradient(ellipse_60%_50%_at_0%_100%,rgba(56,189,248,0.12),transparent)]" />
      <Particles count={28} />
      <AtomBackground className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-70" />
      <AtomBackground className="hidden -left-16 -top-16 scale-[0.45] opacity-30 sm:block" />
      <AtomBackground className="hidden -bottom-20 -right-20 scale-[0.55] opacity-25 md:block" />

      <div className="relative z-10 w-full max-w-lg animate-fade-slide-up p-4">
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 shadow-lg shadow-brand-500/30">
              <Fuel className="h-5 w-5 text-white" />
            </div>
            <span className="text-lg font-bold tracking-tight text-ink">PetroNiq</span>
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

        {/* Gradient-ring glass card - same treatment as the login card
         * (app/login/page.tsx) so this screen, one click away, doesn't
         * read as a plainer, lower-tier form. */}
        <div className="rounded-[26px] bg-gradient-to-br from-brand-400/40 via-accent/25 to-brand-700/40 p-[1px] shadow-2xl shadow-black/50">
          <div className="rounded-[25px] bg-surface/85 p-7 backdrop-blur-xl">
            <h1 className="text-xl font-semibold text-ink">{t("register.title")}</h1>
            <p className="mt-1 text-sm text-ink-soft">{t("register.subtitle")}</p>

            <form className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2" onSubmit={handleSubmit}>
              <div className="sm:col-span-2">
                <IconField id="company_name" icon={Building2} label={t("register.companyName")}>
                  {() => (
                    <input
                      id="company_name"
                      required
                      value={form.company_name}
                      onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                      className={inputClasses}
                    />
                  )}
                </IconField>
              </div>

              <IconField id="station_name" icon={MapPin} label={t("register.stationName")}>
                {() => (
                  <input
                    id="station_name"
                    required
                    value={form.station_name}
                    onChange={(e) => setForm({ ...form, station_name: e.target.value })}
                    className={inputClasses}
                  />
                )}
              </IconField>

              <IconField id="full_name" icon={User} label={t("register.fullName")}>
                {() => (
                  <input
                    id="full_name"
                    required
                    value={form.full_name}
                    onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                    className={inputClasses}
                  />
                )}
              </IconField>

              <IconField id="email" icon={Mail} label={t("login.email")}>
                {() => (
                  <input
                    id="email"
                    type="email"
                    required
                    autoComplete="username"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    className={inputClasses}
                  />
                )}
              </IconField>

              <IconField id="password" icon={KeyRound} label={t("login.password")}>
                {() => (
                  <input
                    id="password"
                    type="password"
                    required
                    minLength={10}
                    autoComplete="new-password"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className={inputClasses}
                  />
                )}
              </IconField>

              {plans.length > 0 && (
                <div className="sm:col-span-2">
                  <label htmlFor="plan_code" className="block text-sm font-medium text-ink">
                    {t("register.plan")}
                  </label>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
                    {plans.map((p) => {
                      const selected = form.plan_code === p.code;
                      return (
                        <button
                          key={p.code}
                          type="button"
                          onClick={() => setForm({ ...form, plan_code: p.code })}
                          className={`rounded-xl border p-3 text-left transition-all ${
                            selected
                              ? "border-brand-500 bg-brand-50 shadow-lg shadow-brand-500/10"
                              : "border-border bg-surface-muted hover:border-brand-200"
                          }`}
                        >
                          <p className={`text-sm font-semibold ${selected ? "text-accent" : "text-ink"}`}>{p.name}</p>
                          <p className="mt-0.5 text-xs text-ink-faint">
                            {p.price_monthly} {t("register.perMonth")}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                  <select
                    id="plan_code"
                    value={form.plan_code}
                    onChange={(e) => setForm({ ...form, plan_code: e.target.value })}
                    className="sr-only"
                    aria-hidden
                    tabIndex={-1}
                  >
                    {plans.map((p) => (
                      <option key={p.code} value={p.code}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {error && (
                <p role="alert" className="rounded-lg bg-danger-50 px-3 py-2.5 text-sm text-danger-600 sm:col-span-2">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="btn-shine sm:col-span-2 w-full rounded-lg bg-gradient-to-r from-brand-500 to-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:shadow-brand-500/40 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:shadow-none"
              >
                {submitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    {t("register.creating")}
                  </span>
                ) : (
                  t("register.createAccount")
                )}
              </button>

              <p className="text-center text-sm text-ink-soft sm:col-span-2">
                <Link href="/login" className="text-accent transition-colors hover:text-brand-400 hover:underline">
                  {t("register.haveAccount")}
                </Link>
              </p>
            </form>
          </div>
        </div>

        <footer className="mt-8 text-center text-xs text-ink-faint">PetroNiq Fuel Retail ERP</footer>
      </div>
    </main>
  );
}
