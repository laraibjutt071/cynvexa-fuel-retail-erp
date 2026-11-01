"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useLanguage } from "@/lib/i18n/context";
import { apiJson, ApiError } from "@/lib/api";
import { AtomBackground } from "@/components/decor/AtomBackground";
import { Particles } from "@/components/decor/Particles";
import type { Plan } from "@/lib/types";

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

  return (
    <main className="relative flex flex-1 items-center justify-center overflow-hidden px-4 py-10">
      <Particles count={28} />
      <AtomBackground className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-70" />
      <AtomBackground className="hidden -left-16 -top-16 scale-[0.45] opacity-30 sm:block" />
      <AtomBackground className="hidden -bottom-20 -right-20 scale-[0.55] opacity-25 md:block" />

      <div className="relative z-10 w-full max-w-lg animate-fade-slide-up p-4">
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={() => setLanguage(language === "en" ? "ur" : "en")}
            className="rounded-full border border-border px-3 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-surface-elevated hover:text-ink"
          >
            {language === "en" ? "Roman Urdu" : "English"}
          </button>
        </div>
        <h1 className="text-xl font-semibold text-ink">{t("register.title")}</h1>
        <p className="mt-1 text-sm text-ink-soft">{t("register.subtitle")}</p>

        <form className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2" onSubmit={handleSubmit}>
          <div className="sm:col-span-2">
            <label htmlFor="company_name" className="block text-sm font-medium text-ink">
              {t("register.companyName")}
            </label>
            <input
              id="company_name"
              required
              value={form.company_name}
              onChange={(e) => setForm({ ...form, company_name: e.target.value })}
              className="mt-1 block w-full rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-ink shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div>
            <label htmlFor="station_name" className="block text-sm font-medium text-ink">
              {t("register.stationName")}
            </label>
            <input
              id="station_name"
              required
              value={form.station_name}
              onChange={(e) => setForm({ ...form, station_name: e.target.value })}
              className="mt-1 block w-full rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-ink shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div>
            <label htmlFor="full_name" className="block text-sm font-medium text-ink">
              {t("register.fullName")}
            </label>
            <input
              id="full_name"
              required
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="mt-1 block w-full rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-ink shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-ink">
              {t("login.email")}
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
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
              minLength={10}
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="mt-1 block w-full rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-ink shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {plans.length > 0 && (
            <div className="sm:col-span-2">
              <label htmlFor="plan_code" className="block text-sm font-medium text-ink">
                {t("register.plan")}
              </label>
              <select
                id="plan_code"
                value={form.plan_code}
                onChange={(e) => setForm({ ...form, plan_code: e.target.value })}
                className="mt-1 block w-full rounded-md border border-border bg-surface-muted px-3 py-2 text-sm text-ink shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                {plans.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name} — {p.price_monthly} {t("register.perMonth")}
                  </option>
                ))}
              </select>
            </div>
          )}

          {error && (
            <p role="alert" className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger-600 sm:col-span-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="sm:col-span-2 w-full rounded-md bg-brand-500 px-3 py-2 text-sm font-medium text-white transition-all hover:bg-brand-600 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? t("register.creating") : t("register.createAccount")}
          </button>

          <p className="text-center text-sm text-ink-soft sm:col-span-2">
            <Link href="/login" className="text-accent hover:underline">
              {t("register.haveAccount")}
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}
