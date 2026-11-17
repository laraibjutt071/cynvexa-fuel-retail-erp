"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";
import type { TenantOnboardingResponse } from "@/lib/types";

const STEPS = ["Business information", "Owner account", "Review & create"] as const;

/** The Super Admin "Create Petrol Pump" workflow - one guided form that
 * submits to POST /platform/organizations, which provisions the
 * organization, its first station, the owner account, and the Owner role
 * assignment atomically via the same logic /auth/register uses
 * (app/core/tenant_provisioning.py). */
export default function CreateOrganizationPage() {
  const { authFetch } = useAuth();
  const { notify } = useToast();
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TenantOnboardingResponse | null>(null);

  const [form, setForm] = useState({
    company_name: "",
    station_name: "Main Station",
    phone: "",
    address: "",
    city: "",
    province: "",
    country: "",
    owner_full_name: "",
    owner_email: "",
    owner_password: "",
  });

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  const step0Valid = form.company_name.trim().length > 0 && form.station_name.trim().length > 0;
  const step1Valid = form.owner_full_name.trim().length > 0 && form.owner_email.trim().length > 0 && form.owner_password.length >= 10;

  async function handleSubmit() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, string> = {
        company_name: form.company_name,
        station_name: form.station_name,
        owner_full_name: form.owner_full_name,
        owner_email: form.owner_email,
        owner_password: form.owner_password,
      };
      if (form.phone) payload.phone = form.phone;
      if (form.address) payload.address = form.address;
      if (form.city) payload.city = form.city;
      if (form.province) payload.province = form.province;
      if (form.country) payload.country = form.country;

      const resp = await authFetch("/platform/organizations", { method: "POST", body: JSON.stringify(payload) });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not create this organization." }));
        throw new ApiError(resp.status, body.detail ?? "Could not create this organization.");
      }
      const body: TenantOnboardingResponse = await resp.json();
      setResult(body);
      notify("success", `${body.organization_name} is onboarded.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
        <Card title="Organization onboarded">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-success-100 text-success-600">
              <Check className="h-5 w-5" aria-hidden />
            </span>
            <div>
              <p className="text-sm font-medium text-ink">{result.organization_name} is live.</p>
              <p className="mt-1 text-sm text-ink-soft">
                The owner account ({result.owner_email}) has been created and can sign in immediately with the
                password you set. A 14-day trial subscription is already active.
              </p>
            </div>
          </div>
          <div className="mt-6 flex gap-2">
            <Button onClick={() => router.push(`/dashboard/platform/organizations/${result.organization_id}`)}>
              View organization
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setResult(null);
                setStep(0);
                setForm({
                  company_name: "",
                  station_name: "Main Station",
                  phone: "",
                  address: "",
                  city: "",
                  province: "",
                  country: "",
                  owner_full_name: "",
                  owner_email: "",
                  owner_password: "",
                });
              }}
            >
              Onboard another
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div>
        <h1 className="text-xl font-semibold text-ink">Create a petrol pump organization</h1>
        <p className="mt-1 text-sm text-ink-soft">A guided, three-step onboarding - nothing is created until the final step.</p>
      </div>

      <div className="flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex flex-1 items-center gap-2">
            <span
              className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                i < step ? "bg-success-100 text-success-600" : i === step ? "bg-brand-500 text-white" : "bg-surface-elevated text-ink-faint"
              }`}
            >
              {i < step ? <Check className="h-3.5 w-3.5" /> : i + 1}
            </span>
            <span className={`text-xs font-medium ${i === step ? "text-ink" : "text-ink-faint"}`}>{label}</span>
            {i < STEPS.length - 1 && <span className="h-px flex-1 bg-border" />}
          </div>
        ))}
      </div>

      <Card title={STEPS[step]}>
        {step === 0 && (
          <div className="space-y-4">
            <Field label="Petrol pump business name" required>
              {(id) => <TextInput id={id} required value={form.company_name} onChange={(e) => update("company_name", e.target.value)} />}
            </Field>
            <Field label="First station name" required hint="Can be renamed or more added later">
              {(id) => <TextInput id={id} required value={form.station_name} onChange={(e) => update("station_name", e.target.value)} />}
            </Field>
            <Field label="Phone">
              {(id) => <TextInput id={id} value={form.phone} onChange={(e) => update("phone", e.target.value)} />}
            </Field>
            <Field label="Address">
              {(id) => <TextInput id={id} value={form.address} onChange={(e) => update("address", e.target.value)} />}
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Field label="City">
                {(id) => <TextInput id={id} value={form.city} onChange={(e) => update("city", e.target.value)} />}
              </Field>
              <Field label="Province">
                {(id) => <TextInput id={id} value={form.province} onChange={(e) => update("province", e.target.value)} />}
              </Field>
              <Field label="Country">
                {(id) => <TextInput id={id} value={form.country} onChange={(e) => update("country", e.target.value)} />}
              </Field>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <Field label="Owner full name" required>
              {(id) => <TextInput id={id} required value={form.owner_full_name} onChange={(e) => update("owner_full_name", e.target.value)} />}
            </Field>
            <Field label="Owner email" required hint="They'll sign in with this">
              {(id) => <TextInput id={id} type="email" required value={form.owner_email} onChange={(e) => update("owner_email", e.target.value)} />}
            </Field>
            <Field label="Owner password" required hint="At least 10 characters - share this with them securely, outside this screen">
              {(id) => (
                <TextInput
                  id={id}
                  type="text"
                  required
                  minLength={10}
                  value={form.owner_password}
                  onChange={(e) => update("owner_password", e.target.value)}
                />
              )}
            </Field>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
              <Row label="Business name" value={form.company_name} />
              <Row label="First station" value={form.station_name} />
              <Row label="Location" value={[form.city, form.province, form.country].filter(Boolean).join(", ") || "—"} />
              <Row label="Phone" value={form.phone || "—"} />
              <Row label="Owner" value={form.owner_full_name} />
              <Row label="Owner email" value={form.owner_email} />
            </dl>
            {error && <p className="text-sm text-danger-600">{error}</p>}
          </div>
        )}

        <div className="mt-6 flex items-center justify-between border-t border-border pt-4">
          <Button variant="secondary" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Back
          </Button>
          {step < STEPS.length - 1 ? (
            <Button disabled={step === 0 ? !step0Valid : !step1Valid} onClick={() => setStep((s) => s + 1)}>
              Next
              <ChevronRight className="h-4 w-4" aria-hidden />
            </Button>
          ) : (
            <Button busy={submitting} onClick={handleSubmit}>
              Create organization
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="text-sm text-ink">{value}</dd>
    </div>
  );
}
