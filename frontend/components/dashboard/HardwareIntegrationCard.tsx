"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { Cpu, CheckCircle2 } from "lucide-react";
import type { HardwareDevice, HardwareDeviceType, HardwareConnectionType } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];

const ALL_DEVICE_TYPE_OPTIONS: { value: HardwareDeviceType; label: string; hint: string }[] = [
  { value: "dispenser_controller", label: "Dispenser / Pump Controller", hint: "Feeds nozzle totalizer readings automatically." },
  { value: "forecourt_controller", label: "Forecourt Controller", hint: "Sits between several dispensers and this system." },
  { value: "atg", label: "ATG (Tank Gauge)", hint: "Feeds tank dip/level readings automatically." },
  { value: "existing_pos", label: "Existing POS / ERP", hint: "Exchanges sales or payment data with this system." },
  { value: "biometric_attendance", label: "Biometric Attendance Device", hint: "Fingerprint/face scanner that marks staff check-in/check-out automatically." },
];

type WizardForm = {
  device_type: HardwareDeviceType;
  label: string;
  brand: string;
  model: string;
  serial_number: string;
  connection_type: HardwareConnectionType;
  ip_address: string;
  port: string;
  com_port: string;
};

function emptyForm(deviceType: HardwareDeviceType): WizardForm {
  return {
    device_type: deviceType,
    label: "",
    brand: "",
    model: "",
    serial_number: "",
    connection_type: "tcp_ip",
    ip_address: "",
    port: "",
    com_port: "",
  };
}

export function HardwareIntegrationCard({
  orgId,
  stationId,
  authFetch,
  allowedTypes,
  title = "Hardware Integration",
  description = "Connect a dispenser controller, forecourt controller, ATG, existing POS or biometric attendance device to this station.",
  idlePrompt = "Click \"Start Hardware Connection\" to walk through connecting real equipment, step by step.",
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  /** Restrict the wizard's type-picker to a subset (e.g. just biometric, from the Attendance page). Omit for all types. */
  allowedTypes?: HardwareDeviceType[];
  title?: string;
  description?: string;
  idlePrompt?: string;
}) {
  const { notify } = useToast();
  const base = `/organizations/${orgId}/stations/${stationId}/hardware-devices`;
  const deviceTypeOptions = allowedTypes
    ? ALL_DEVICE_TYPE_OPTIONS.filter((o) => allowedTypes.includes(o.value))
    : ALL_DEVICE_TYPE_OPTIONS;
  const defaultDeviceType = deviceTypeOptions[0]?.value ?? "dispenser_controller";

  const [devices, setDevices] = useState<HardwareDevice[] | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState(0); // 0 = type, 1 = details, 2 = review/create, 3 = test
  const [form, setForm] = useState<WizardForm>(emptyForm(defaultDeviceType));
  const [busy, setBusy] = useState(false);
  const [createdDevice, setCreatedDevice] = useState<HardwareDevice | null>(null);

  const load = useCallback(async () => {
    const resp = await authFetch(base);
    if (resp.ok) {
      const all: HardwareDevice[] = await resp.json();
      setDevices(allowedTypes ? all.filter((d) => allowedTypes.includes(d.device_type)) : all);
    }
  }, [authFetch, base, allowedTypes]);

  useEffect(() => { load(); }, [load]);

  function startWizard() {
    setForm(emptyForm(defaultDeviceType));
    setCreatedDevice(null);
    setStep(deviceTypeOptions.length > 1 ? 0 : 1);
    setWizardOpen(true);
  }

  function closeWizard() {
    setWizardOpen(false);
    load();
  }

  async function createDevice() {
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        device_type: form.device_type,
        label: form.label,
        brand: form.brand || undefined,
        model: form.model || undefined,
        serial_number: form.serial_number || undefined,
        connection_type: form.connection_type,
      };
      if (form.connection_type === "tcp_ip") {
        payload.ip_address = form.ip_address;
        payload.port = form.port ? Number(form.port) : undefined;
      } else {
        payload.com_port = form.com_port;
      }
      const resp = await authFetch(base, { method: "POST", body: JSON.stringify(payload) });
      if (resp.ok) {
        setCreatedDevice(await resp.json());
        setStep(3);
      } else {
        const body = await resp.json().catch(() => ({ detail: "Could not save this device." }));
        notify("error", body.detail ?? "Could not save this device.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function runTest() {
    if (!createdDevice) return;
    setBusy(true);
    try {
      const resp = await authFetch(`${base}/${createdDevice.id}/test-connection`, { method: "POST" });
      const body = await resp.json().catch(() => null);
      if (resp.ok && body) {
        setCreatedDevice(body.device);
        notify(body.status === "connected" ? "success" : "error", body.message);
      } else {
        notify("error", body?.detail ?? "Connection test failed to run.");
      }
    } finally {
      setBusy(false);
    }
  }

  const canGoToDetails = form.label.trim().length > 0;
  const canCreate =
    form.connection_type === "tcp_ip" ? form.ip_address.trim().length > 0 && form.port.trim().length > 0 : form.com_port.trim().length > 0;

  return (
    <Card
      title={title}
      description={description}
      action={
        <Button type="button" onClick={startWizard}>
          <Cpu className="h-4 w-4" /> Start Hardware Connection
        </Button>
      }
    >
      {!wizardOpen ? (
        <div className="space-y-3">
          <div className="flex items-start gap-3 rounded-lg border border-border bg-background/50 p-4">
            <Cpu className="mt-0.5 h-5 w-5 flex-shrink-0 text-accent" />
            <p className="text-sm text-ink-soft">{idlePrompt}</p>
          </div>
          {devices && devices.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-ink-faint">
                  <th className="py-2 pr-2">Device</th>
                  <th className="py-2 pr-2">Type</th>
                  <th className="py-2 pr-2">Connection</th>
                  <th className="py-2 pr-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {devices.map((d) => (
                  <tr key={d.id} className="border-b border-border/60">
                    <td className="py-2 pr-2 text-ink">{d.label}{d.brand ? ` — ${d.brand} ${d.model ?? ""}` : ""}</td>
                    <td className="py-2 pr-2 text-ink-soft">{ALL_DEVICE_TYPE_OPTIONS.find((o) => o.value === d.device_type)?.label ?? d.device_type}</td>
                    <td className="py-2 pr-2 font-mono text-ink-soft">
                      {d.connection_type === "tcp_ip" ? `${d.ip_address}:${d.port}` : d.com_port}
                    </td>
                    <td className="py-2 pr-2">
                      <Badge tone={d.status === "connected" ? "success" : d.status === "failed" ? "danger" : "neutral"}>
                        {d.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="space-y-5">
          {/* Step indicator */}
          <div className="flex items-center gap-2 text-xs font-medium text-ink-faint">
            {["Hardware type", "Connection details", "Review & save", "Test connection"]
              .slice(deviceTypeOptions.length > 1 ? 0 : 1)
              .map((label, idx) => {
                const i = deviceTypeOptions.length > 1 ? idx : idx + 1;
                return (
                  <div key={label} className="flex items-center gap-2">
                    <span
                      className={`flex h-6 w-6 items-center justify-center rounded-full ${
                        i === step ? "bg-brand-500 text-white" : i < step ? "bg-success-100 text-success-700" : "bg-surface-muted text-ink-faint"
                      }`}
                    >
                      {i < step ? <CheckCircle2 className="h-3.5 w-3.5" /> : i + 1}
                    </span>
                    <span className={i === step ? "text-ink" : ""}>{label}</span>
                    {i < 3 && <span className="mx-1 text-ink-faint">→</span>}
                  </div>
                );
              })}
          </div>

          {step === 0 && (
            <div className="space-y-4">
              <p className="text-sm text-ink-soft">
                First, what kind of hardware are you connecting? Write down the brand/model before you start - you&apos;ll
                need it in the next step.
              </p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {deviceTypeOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setForm({ ...form, device_type: opt.value })}
                    className={`rounded-lg border p-3 text-left transition-colors ${
                      form.device_type === opt.value ? "border-brand-500 bg-brand-50" : "border-border hover:bg-surface-elevated"
                    }`}
                  >
                    <p className="text-sm font-semibold text-ink">{opt.label}</p>
                    <p className="mt-1 text-xs text-ink-soft">{opt.hint}</p>
                  </button>
                ))}
              </div>
              <Field label="Give this device a name" hint='e.g. "Dispenser 1 Controller" or "Main Entrance Fingerprint Scanner"'>
                {(id) => <TextInput id={id} required value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />}
              </Field>
              <div className="flex justify-between border-t border-border pt-4">
                <Button type="button" variant="ghost" onClick={closeWizard}>Cancel</Button>
                <Button type="button" disabled={!canGoToDetails} onClick={() => setStep(1)}>Next</Button>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4">
              {deviceTypeOptions.length === 1 && (
                <Field label="Give this device a name" hint='e.g. "Main Entrance Fingerprint Scanner"'>
                  {(id) => <TextInput id={id} required value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />}
                </Field>
              )}
              <p className="text-sm text-ink-soft">
                Get your vendor&apos;s documentation and written permission to connect before going further. Enter what
                you know below.
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Brand" hint={form.device_type === "biometric_attendance" ? "e.g. ZKTeco, Suprema, Hikvision" : "e.g. Tokheim, Wayne, Gilbarco"}>
                  {(id) => <TextInput id={id} value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} />}
                </Field>
                <Field label="Model">
                  {(id) => <TextInput id={id} value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />}
                </Field>
                <Field label="Serial Number">
                  {(id) => <TextInput id={id} value={form.serial_number} onChange={(e) => setForm({ ...form, serial_number: e.target.value })} />}
                </Field>
                <Field label="Connection Type">
                  {(id) => (
                    <Select id={id} value={form.connection_type} onChange={(e) => setForm({ ...form, connection_type: e.target.value as HardwareConnectionType })}>
                      <option value="tcp_ip">Network (TCP/IP)</option>
                      <option value="serial">Serial (COM port / RS-485)</option>
                    </Select>
                  )}
                </Field>
                {form.connection_type === "tcp_ip" ? (
                  <>
                    <Field label="IP Address" required hint="The device's address on the station's network">
                      {(id) => <TextInput id={id} required value={form.ip_address} onChange={(e) => setForm({ ...form, ip_address: e.target.value })} placeholder="192.168.1.50" />}
                    </Field>
                    <Field label="Port" required hint={form.device_type === "biometric_attendance" ? "ZKTeco devices commonly use 4370" : undefined}>
                      {(id) => <TextInput id={id} required type="number" min="1" max="65535" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} placeholder={form.device_type === "biometric_attendance" ? "4370" : "5002"} />}
                    </Field>
                  </>
                ) : (
                  <Field label="COM Port" required hint="As seen on the till PC physically wired to this device">
                    {(id) => <TextInput id={id} required value={form.com_port} onChange={(e) => setForm({ ...form, com_port: e.target.value })} placeholder="COM3" />}
                  </Field>
                )}
              </div>
              <div className="flex justify-between border-t border-border pt-4">
                <Button type="button" variant="ghost" onClick={() => (deviceTypeOptions.length > 1 ? setStep(0) : closeWizard())}>
                  {deviceTypeOptions.length > 1 ? "Back" : "Cancel"}
                </Button>
                <Button type="button" disabled={!canGoToDetails || !canCreate} onClick={() => setStep(2)}>Next</Button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <p className="text-sm text-ink-soft">Review the details below, then save this device to continue to the connection test.</p>
              <dl className="grid grid-cols-1 gap-3 rounded-lg border border-border p-4 text-sm sm:grid-cols-2">
                <div><dt className="text-ink-faint">Name</dt><dd className="text-ink">{form.label}</dd></div>
                <div><dt className="text-ink-faint">Type</dt><dd className="text-ink">{ALL_DEVICE_TYPE_OPTIONS.find((o) => o.value === form.device_type)?.label}</dd></div>
                <div><dt className="text-ink-faint">Brand / Model</dt><dd className="text-ink">{form.brand || "—"} {form.model}</dd></div>
                <div>
                  <dt className="text-ink-faint">Connection</dt>
                  <dd className="font-mono text-ink">{form.connection_type === "tcp_ip" ? `${form.ip_address}:${form.port}` : form.com_port}</dd>
                </div>
              </dl>
              <div className="flex justify-between border-t border-border pt-4">
                <Button type="button" variant="ghost" onClick={() => setStep(1)}>Back</Button>
                <Button type="button" busy={busy} onClick={createDevice}>Save & Continue</Button>
              </div>
            </div>
          )}

          {step === 3 && createdDevice && (
            <div className="space-y-4">
              <p className="text-sm text-ink-soft">
                {createdDevice.connection_type === "tcp_ip"
                  ? "This will attempt a real network connection to the address you entered, from this server."
                  : "Serial devices are wired directly into the station's till PC, so this server cannot test them over the network - this step will explain what to check on-site instead."}
              </p>
              <div className="flex items-center gap-3 rounded-lg border border-border p-4">
                <Button type="button" busy={busy} onClick={runTest}>Test Connection</Button>
                {createdDevice.status !== "draft" && (
                  <Badge tone={createdDevice.status === "connected" ? "success" : "danger"}>{createdDevice.status}</Badge>
                )}
              </div>
              {createdDevice.last_test_message && (
                <p className={`text-sm ${createdDevice.status === "connected" ? "text-success-700" : "text-ink"}`}>
                  {createdDevice.last_test_message}
                </p>
              )}
              <div className="flex justify-between border-t border-border pt-4">
                <Button type="button" variant="ghost" onClick={() => setStep(1)}>Back to edit details</Button>
                <Button type="button" onClick={closeWizard}>Finish</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
