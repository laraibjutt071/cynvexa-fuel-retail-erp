"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Banknote, FileText, Settings2, Users as UsersIcon, Wallet } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { usePermissions } from "@/lib/permissions";
import { useToast } from "@/components/ui/Toast";
import { formatMoney } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge } from "@/components/ui/Badge";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { Dialog, ConfirmDialog } from "@/components/ui/Dialog";
import { AccessDenied } from "@/components/ui/AccessDenied";
import { EmptyState } from "@/components/ui/EmptyState";
import { Tabs, TabPanel } from "@/components/ui/Tabs";
import { StatCard, StatCardGrid } from "@/components/ui/StatCard";
import type { OrgUser, PayrollRule, SalaryRecord } from "@/lib/types";

type AuthFetch = ReturnType<typeof useAuth>["authFetch"];
type PageTab = "dashboard" | "rules" | "generate" | "history";

export default function PayrollPage() {
  const { orgId, stationId } = useParams<{ orgId: string; stationId: string }>();
  const { authFetch } = useAuth();
  const { can, loading: permLoading } = usePermissions(orgId, stationId);
  const canManage = can("payroll:manage");

  const [tab, setTab] = useState<PageTab>("dashboard");
  const [users, setUsers] = useState<OrgUser[]>([]);
  const [rules, setRules] = useState<PayrollRule[] | null>(null);
  const [salaries, setSalaries] = useState<SalaryRecord[] | null>(null);

  const loadUsers = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/users`);
    if (resp.ok) setUsers(await resp.json());
  }, [authFetch, orgId]);

  const loadRules = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/payroll/rules`);
    if (resp.ok) setRules(await resp.json());
  }, [authFetch, orgId, stationId]);

  const loadSalaries = useCallback(async () => {
    const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/payroll/salary`);
    if (resp.ok) setSalaries(await resp.json());
  }, [authFetch, orgId, stationId]);

  useEffect(() => {
    if (!canManage) return;
    loadUsers();
    loadRules();
    loadSalaries();
  }, [canManage, loadUsers, loadRules, loadSalaries]);

  const userNameById = useMemo(() => new Map(users.map((u) => [u.id, u])), [users]);
  const activeRule = useMemo(() => (rules ?? []).find((r) => r.is_active) ?? null, [rules]);

  if (permLoading) {
    return <main className="flex-1 px-6 py-10 text-sm text-ink-soft">Loading…</main>;
  }

  if (!canManage) {
    return (
      <main className="flex-1">
        <PageHeader title="Payroll" breadcrumbs={[{ label: "Dashboard" }, { label: "Payroll" }]} />
        <div className="mx-auto max-w-3xl px-6 py-10">
          <AccessDenied message="Your role does not include payroll access at this station." />
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1">
      <PageHeader
        title="Payroll"
        description="Salary generation, deduction rules, and payroll history for this station."
        breadcrumbs={[{ label: "Dashboard" }, { label: "Payroll" }]}
      />
      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Tabs
          tabs={[
            { id: "dashboard", label: "Dashboard" },
            { id: "rules", label: "Payroll Rules" },
            { id: "generate", label: "Generate Salary" },
            { id: "history", label: "History" },
          ]}
          active={tab}
          onChange={(id) => setTab(id as PageTab)}
        />

        <TabPanel id="dashboard" active={tab}>
          <DashboardTab salaries={salaries} users={users} />
        </TabPanel>
        <TabPanel id="rules" active={tab}>
          <RulesTab orgId={orgId} stationId={stationId} authFetch={authFetch} rules={rules} onChanged={loadRules} />
        </TabPanel>
        <TabPanel id="generate" active={tab}>
          <GenerateTab
            orgId={orgId}
            stationId={stationId}
            authFetch={authFetch}
            users={users}
            activeRule={activeRule}
            onGenerated={loadSalaries}
          />
        </TabPanel>
        <TabPanel id="history" active={tab}>
          <HistoryTab
            orgId={orgId}
            stationId={stationId}
            authFetch={authFetch}
            users={users}
            userNameById={userNameById}
            salaries={salaries}
            onChanged={loadSalaries}
          />
        </TabPanel>
      </div>
    </main>
  );
}

function DashboardTab({ salaries, users }: { salaries: SalaryRecord[] | null; users: OrgUser[] }) {
  if (salaries === null) {
    return <p className="text-sm text-ink-soft">Loading…</p>;
  }

  const employeeCount = new Set(salaries.map((s) => s.user_id)).size;
  const totalGross = salaries.reduce((sum, s) => sum + Number(s.base_salary), 0);
  const totalDeductions = salaries.reduce((sum, s) => sum + Number(s.total_deductions), 0);
  const totalNet = salaries.reduce((sum, s) => sum + Number(s.net_salary), 0);
  const finalizedNet = salaries.filter((s) => s.is_finalized).reduce((sum, s) => sum + Number(s.net_salary), 0);
  const pendingNet = totalNet - finalizedNet;

  return (
    <div className="space-y-6">
      {salaries.length === 0 ? (
        <EmptyState
          icon={Wallet}
          title="No salary records yet"
          description="Generate salary for an employee in the Generate Salary tab to see payroll totals here."
        />
      ) : (
        <>
          <p className="text-xs text-ink-faint">
            Totals below are a sum of every salary record generated at this station - not an organization-wide figure
            (the backend has no cross-station payroll report).
          </p>
          <StatCardGrid>
            <StatCard label="Employees with a salary record" value={employeeCount} icon={UsersIcon} />
            <StatCard label="Total gross (base salary)" value={`PKR ${formatMoney(totalGross)}`} icon={Wallet} />
            <StatCard label="Total deductions" value={`PKR ${formatMoney(totalDeductions)}`} icon={Banknote} tone="warning" />
            <StatCard label="Total net salary" value={`PKR ${formatMoney(totalNet)}`} icon={Wallet} tone="brand" />
          </StatCardGrid>
          <StatCardGrid>
            <StatCard label="Finalized (net)" value={`PKR ${formatMoney(finalizedNet)}`} icon={Wallet} tone="success" />
            <StatCard label="Pending finalization (net)" value={`PKR ${formatMoney(pendingNet)}`} icon={Wallet} tone="warning" />
          </StatCardGrid>
        </>
      )}
    </div>
  );
}

function RulesTab({
  orgId,
  stationId,
  authFetch,
  rules,
  onChanged,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  rules: PayrollRule[] | null;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<PayrollRule | null>(null);

  const columns: Column<PayrollRule>[] = [
    { key: "name", header: "Rule name", render: (r) => <span className="font-medium text-ink">{r.rule_name}</span> },
    { key: "shift_start", header: "Shift start", render: (r) => r.shift_start_time },
    {
      key: "late",
      header: "Late deduction",
      align: "right",
      render: (r) => `PKR ${formatMoney(r.late_deduction_amount)} / occurrence`,
    },
    {
      key: "absent",
      header: "Absent deduction",
      align: "right",
      render: (r) => `PKR ${formatMoney(r.absent_deduction_amount)} / occurrence`,
    },
    {
      key: "half_day",
      header: "Half-day deduction",
      align: "right",
      render: (r) => `PKR ${formatMoney(r.half_day_deduction_amount)} / occurrence`,
    },
    {
      key: "status",
      header: "Status",
      render: (r) => <Badge tone={r.is_active ? "success" : "neutral"}>{r.is_active ? "Active" : "Inactive"}</Badge>,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (r) => (
        <button className="text-xs font-medium text-accent hover:underline" onClick={() => setEditing(r)}>
          Edit
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4 pt-2">
      <Card
        title="Payroll deduction rules"
        description="Each deduction is a flat amount applied once per occurrence (one late day, one absence, one half-day) - never per minute or per hour. Only one rule can be active per station at a time; salary generation uses whichever rule is currently active."
        action={<Button size="sm" onClick={() => setShowCreate(true)}>Add rule</Button>}
      >
        {rules !== null && rules.length === 0 ? (
          <EmptyState
            icon={Settings2}
            title="No payroll rules yet"
            description="Add a rule to define flat per-occurrence deductions for late arrivals, absences, and half-days."
            action={<Button size="sm" onClick={() => setShowCreate(true)}>Add rule</Button>}
          />
        ) : (
          <DataTable columns={columns} data={rules} keyFn={(r) => r.id} emptyMessage="No payroll rules." />
        )}
      </Card>

      <RuleDialog
        mode="create"
        open={showCreate}
        rule={null}
        onClose={() => setShowCreate(false)}
        orgId={orgId}
        stationId={stationId}
        authFetch={authFetch}
        onSaved={async () => {
          setShowCreate(false);
          notify("success", "Payroll rule created.");
          onChanged();
        }}
      />
      <RuleDialog
        mode="edit"
        open={editing !== null}
        rule={editing}
        onClose={() => setEditing(null)}
        orgId={orgId}
        stationId={stationId}
        authFetch={authFetch}
        onSaved={async () => {
          setEditing(null);
          notify("success", "Payroll rule updated.");
          onChanged();
        }}
      />
    </div>
  );
}

function RuleDialog({
  mode,
  open,
  rule,
  onClose,
  orgId,
  stationId,
  authFetch,
  onSaved,
}: {
  mode: "create" | "edit";
  open: boolean;
  rule: PayrollRule | null;
  onClose: () => void;
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  onSaved: () => void;
}) {
  const { notify } = useToast();
  const [ruleName, setRuleName] = useState("");
  const [shiftStart, setShiftStart] = useState("09:00");
  const [lateThreshold, setLateThreshold] = useState("15");
  const [halfDayThreshold, setHalfDayThreshold] = useState("120");
  const [lateAmount, setLateAmount] = useState("0");
  const [absentAmount, setAbsentAmount] = useState("0");
  const [halfDayAmount, setHalfDayAmount] = useState("0");
  const [isActive, setIsActive] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && rule) {
      setShiftStart(rule.shift_start_time);
      setLateThreshold(String(rule.late_threshold_minutes));
      setHalfDayThreshold(String(rule.half_day_threshold_minutes));
      setLateAmount(rule.late_deduction_amount);
      setAbsentAmount(rule.absent_deduction_amount);
      setHalfDayAmount(rule.half_day_deduction_amount);
      setIsActive(rule.is_active);
    } else {
      setRuleName("");
      setShiftStart("09:00");
      setLateThreshold("15");
      setHalfDayThreshold("120");
      setLateAmount("0");
      setAbsentAmount("0");
      setHalfDayAmount("0");
      setIsActive(true);
    }
  }, [open, mode, rule]);

  async function submit() {
    setSubmitting(true);
    try {
      const base = `/organizations/${orgId}/stations/${stationId}/payroll/rules`;
      const resp =
        mode === "create"
          ? await authFetch(base, {
              method: "POST",
              body: JSON.stringify({
                rule_name: ruleName,
                shift_start_time: shiftStart,
                late_threshold_minutes: Number(lateThreshold),
                half_day_threshold_minutes: Number(halfDayThreshold),
                late_deduction_amount: lateAmount,
                absent_deduction_amount: absentAmount,
                half_day_deduction_amount: halfDayAmount,
              }),
            })
          : await authFetch(`${base}/${rule!.id}`, {
              method: "PATCH",
              body: JSON.stringify({
                shift_start_time: shiftStart,
                late_threshold_minutes: Number(lateThreshold),
                half_day_threshold_minutes: Number(halfDayThreshold),
                late_deduction_amount: lateAmount,
                absent_deduction_amount: absentAmount,
                half_day_deduction_amount: halfDayAmount,
                is_active: isActive,
              }),
            });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not save this rule." }));
        notify("error", body.detail ?? "Could not save this rule.");
        return;
      }
      onSaved();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={mode === "create" ? "Add payroll rule" : `Edit ${rule?.rule_name ?? "rule"}`}
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={submit}
            busy={submitting}
            disabled={mode === "create" ? !ruleName.trim() : false}
          >
            {mode === "create" ? "Create rule" : "Save changes"}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {mode === "create" && (
          <Field label="Rule name" required>
            {(id) => <TextInput id={id} required value={ruleName} onChange={(e) => setRuleName(e.target.value)} />}
          </Field>
        )}
        <Field label="Shift start time" required>
          {(id) => <TextInput id={id} type="time" required value={shiftStart} onChange={(e) => setShiftStart(e.target.value)} />}
        </Field>
        <Field label="Late threshold (minutes)" hint="Not yet used to auto-detect lateness — attendance status is entered manually.">
          {(id) => (
            <TextInput id={id} type="number" min="0" value={lateThreshold} onChange={(e) => setLateThreshold(e.target.value)} />
          )}
        </Field>
        <Field label="Half-day threshold (minutes)" hint="Not yet used to auto-detect a half-day — attendance status is entered manually.">
          {(id) => (
            <TextInput
              id={id}
              type="number"
              min="0"
              value={halfDayThreshold}
              onChange={(e) => setHalfDayThreshold(e.target.value)}
            />
          )}
        </Field>
        <Field label="Late deduction (PKR, flat per occurrence)" required>
          {(id) => (
            <TextInput id={id} type="number" step="0.01" min="0" required value={lateAmount} onChange={(e) => setLateAmount(e.target.value)} />
          )}
        </Field>
        <Field label="Absent deduction (PKR, flat per occurrence)" required>
          {(id) => (
            <TextInput id={id} type="number" step="0.01" min="0" required value={absentAmount} onChange={(e) => setAbsentAmount(e.target.value)} />
          )}
        </Field>
        <Field label="Half-day deduction (PKR, flat per occurrence)" required>
          {(id) => (
            <TextInput
              id={id}
              type="number"
              step="0.01"
              min="0"
              required
              value={halfDayAmount}
              onChange={(e) => setHalfDayAmount(e.target.value)}
            />
          )}
        </Field>
        {mode === "edit" && (
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            Active (only one active rule is used when salary is generated)
          </label>
        )}
      </div>
    </Dialog>
  );
}

function GenerateTab({
  orgId,
  stationId,
  authFetch,
  users,
  activeRule,
  onGenerated,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  users: OrgUser[];
  activeRule: PayrollRule | null;
  onGenerated: () => void;
}) {
  const { notify } = useToast();
  const today = new Date();
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);

  const [userId, setUserId] = useState("");
  const [periodStart, setPeriodStart] = useState(monthAgo.toISOString().slice(0, 10));
  const [periodEnd, setPeriodEnd] = useState(today.toISOString().slice(0, 10));
  const [baseSalary, setBaseSalary] = useState("");
  const [notes, setNotes] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SalaryRecord | null>(null);

  const valid = userId && periodStart && periodEnd && periodEnd >= periodStart && baseSalary && Number(baseSalary) >= 0;

  async function generate() {
    setSubmitting(true);
    try {
      const resp = await authFetch(`/organizations/${orgId}/stations/${stationId}/payroll/salary/generate`, {
        method: "POST",
        body: JSON.stringify({
          user_id: userId,
          period_start: periodStart,
          period_end: periodEnd,
          base_salary: baseSalary,
          notes: notes || undefined,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not generate salary for this period." }));
        notify("error", body.detail ?? "Could not generate salary for this period.");
        return;
      }
      const record: SalaryRecord = await resp.json();
      setResult(record);
      notify("success", "Salary generated.");
      setConfirmOpen(false);
      onGenerated();
    } finally {
      setSubmitting(false);
    }
  }

  const employee = users.find((u) => u.id === userId);

  return (
    <div className="space-y-6 pt-2">
      <Card
        title="Generate salary for a period"
        description="Pulls attendance records for the selected employee and period from this station, applies the station's active payroll rule (flat per-occurrence deductions only), and creates one salary record. This cannot be run twice for the same employee and period."
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Employee" required>
            {(id) => (
              <Select id={id} required value={userId} onChange={(e) => setUserId(e.target.value)}>
                <option value="">Select…</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                    {u.job_title ? ` — ${u.job_title}` : ""}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Base salary (PKR)" required>
            {(id) => (
              <TextInput id={id} type="number" step="0.01" min="0" required value={baseSalary} onChange={(e) => setBaseSalary(e.target.value)} />
            )}
          </Field>
          <Field label="Period start" required>
            {(id) => <TextInput id={id} type="date" required value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />}
          </Field>
          <Field label="Period end" required>
            {(id) => <TextInput id={id} type="date" required value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />}
          </Field>
          <Field label="Notes" hint="Optional">
            {(id) => <TextInput id={id} value={notes} onChange={(e) => setNotes(e.target.value)} />}
          </Field>
        </div>

        {activeRule ? (
          <p className="mt-3 text-xs text-ink-faint">
            Active rule "{activeRule.rule_name}": PKR {formatMoney(activeRule.late_deduction_amount)} per late day, PKR{" "}
            {formatMoney(activeRule.absent_deduction_amount)} per absence, PKR {formatMoney(activeRule.half_day_deduction_amount)} per
            half-day. Approved leave is counted but never deducted.
          </p>
        ) : (
          <p className="mt-3 text-xs text-caution-600">
            No active payroll rule at this station — salary will be generated with zero deductions regardless of attendance.
          </p>
        )}

        <div className="mt-4">
          <Button onClick={() => setConfirmOpen(true)} disabled={!valid}>
            Generate salary
          </Button>
        </div>
      </Card>

      {result && (
        <Card title="Generated salary record">
          <StatCardGrid>
            <StatCard label="Base salary" value={`PKR ${formatMoney(result.base_salary)}`} icon={Wallet} />
            <StatCard label="Total deductions" value={`PKR ${formatMoney(result.total_deductions)}`} icon={Banknote} tone="warning" />
            <StatCard label="Net salary" value={`PKR ${formatMoney(result.net_salary)}`} icon={Wallet} tone="brand" />
          </StatCardGrid>

          <div className="mt-4">
            <p className="mb-2 text-sm font-medium text-ink">Deduction breakdown</p>
            {activeRule ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-ink-faint">
                    <th className="py-2 pr-2">Occurrence type</th>
                    <th className="py-2 pr-2 text-right">Count</th>
                    <th className="py-2 pr-2 text-right">Flat amount each</th>
                    <th className="py-2 pr-2 text-right">Subtotal</th>
                  </tr>
                </thead>
                <tbody>
                  <DeductionRow label="Late" count={result.days_late} amount={activeRule.late_deduction_amount} />
                  <DeductionRow label="Absent" count={result.days_absent} amount={activeRule.absent_deduction_amount} />
                  <DeductionRow label="Half-day" count={result.days_half_day} amount={activeRule.half_day_deduction_amount} />
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-ink-soft">No active payroll rule was applied to this record.</p>
            )}
            <p className="mt-2 text-xs text-ink-faint">
              Present: {result.days_present} · Approved leave (not deducted): {result.days_leave}
            </p>
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={generate}
        title="Generate this salary record?"
        description={`This generates salary for ${employee?.full_name ?? "this employee"} for ${periodStart} to ${periodEnd}. Deductions are calculated by the backend from real attendance records and cannot be edited afterward — only finalized or corrected via a new record if your role permits.`}
        confirmLabel="Yes, generate salary"
        confirmVariant="primary"
        busy={submitting}
      />
    </div>
  );
}

function DeductionRow({ label, count, amount }: { label: string; count: number; amount: string }) {
  const subtotal = count * Number(amount);
  return (
    <tr className="border-b border-border/60 last:border-0">
      <td className="py-2 pr-2 text-ink">{label}</td>
      <td className="py-2 pr-2 text-right text-ink">{count}</td>
      <td className="py-2 pr-2 text-right text-ink-soft">PKR {formatMoney(amount)}</td>
      <td className="py-2 pr-2 text-right font-medium text-ink">PKR {formatMoney(subtotal)}</td>
    </tr>
  );
}

function HistoryTab({
  orgId,
  stationId,
  authFetch,
  users,
  userNameById,
  salaries,
  onChanged,
}: {
  orgId: string;
  stationId: string;
  authFetch: AuthFetch;
  users: OrgUser[];
  userNameById: Map<string, OrgUser>;
  salaries: SalaryRecord[] | null;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "finalized" | "pending">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [detail, setDetail] = useState<SalaryRecord | null>(null);
  const [finalizeTarget, setFinalizeTarget] = useState<SalaryRecord | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!salaries) return salaries;
    return salaries.filter((s) => {
      if (employeeFilter && s.user_id !== employeeFilter) return false;
      if (statusFilter === "finalized" && !s.is_finalized) return false;
      if (statusFilter === "pending" && s.is_finalized) return false;
      if (dateFrom && s.period_end < dateFrom) return false;
      if (dateTo && s.period_start > dateTo) return false;
      return true;
    });
  }, [salaries, employeeFilter, statusFilter, dateFrom, dateTo]);

  async function finalize() {
    if (!finalizeTarget) return;
    setBusyId(finalizeTarget.id);
    try {
      const resp = await authFetch(
        `/organizations/${orgId}/stations/${stationId}/payroll/salary/${finalizeTarget.id}/finalize`,
        { method: "PATCH" }
      );
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not finalize this salary record." }));
        notify("error", body.detail ?? "Could not finalize this salary record.");
        return;
      }
      notify("success", "Salary record finalized.");
      setFinalizeTarget(null);
      setDetail(null);
      await onChanged();
    } finally {
      setBusyId(null);
    }
  }

  const columns: Column<SalaryRecord>[] = [
    {
      key: "employee",
      header: "Employee",
      render: (r) => <span className="font-medium text-ink">{userNameById.get(r.user_id)?.full_name ?? r.user_id.slice(0, 8)}</span>,
    },
    { key: "period", header: "Period", render: (r) => `${r.period_start} → ${r.period_end}` },
    {
      key: "base",
      header: "Base salary",
      align: "right",
      render: (r) => `PKR ${formatMoney(r.base_salary)}`,
    },
    {
      key: "deductions",
      header: "Deductions",
      align: "right",
      render: (r) => `PKR ${formatMoney(r.total_deductions)}`,
    },
    {
      key: "net",
      header: "Net salary",
      align: "right",
      render: (r) => <span className="font-medium text-ink">PKR {formatMoney(r.net_salary)}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (r) => <Badge tone={r.is_finalized ? "success" : "warning"}>{r.is_finalized ? "Finalized" : "Pending"}</Badge>,
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (r) => (
        <div className="flex justify-end gap-3">
          <button className="text-xs font-medium text-accent hover:underline" onClick={() => setDetail(r)}>
            Statement
          </button>
          {!r.is_finalized && (
            <button
              className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
              disabled={busyId === r.id}
              onClick={() => setFinalizeTarget(r)}
            >
              Finalize
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4 pt-2">
      <Card title="Payroll history">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <Field label="Employee">
            {(id) => (
              <Select id={id} className="w-56" value={employeeFilter} onChange={(e) => setEmployeeFilter(e.target.value)}>
                <option value="">All employees</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Status">
            {(id) => (
              <Select id={id} className="w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as "" | "finalized" | "pending")}>
                <option value="">All</option>
                <option value="finalized">Finalized</option>
                <option value="pending">Pending</option>
              </Select>
            )}
          </Field>
          <Field label="Period overlaps from">
            {(id) => <TextInput id={id} type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />}
          </Field>
          <Field label="to">
            {(id) => <TextInput id={id} type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />}
          </Field>
        </div>

        {salaries !== null && salaries.length === 0 ? (
          <EmptyState icon={FileText} title="No salary records yet" description="Generate a salary record for an employee to see payroll history here." />
        ) : (
          <DataTable columns={columns} data={filtered} keyFn={(r) => r.id} emptyMessage="No salary records match these filters." />
        )}
      </Card>

      <Dialog
        open={detail !== null}
        onClose={() => setDetail(null)}
        title="Salary statement"
        size="lg"
        footer={
          <Button size="sm" variant="secondary" onClick={() => window.print()}>
            Print
          </Button>
        }
      >
        {detail && (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <DetailRow label="Employee" value={userNameById.get(detail.user_id)?.full_name ?? detail.user_id} />
              <DetailRow label="Designation" value={userNameById.get(detail.user_id)?.job_title ?? "—"} />
              <DetailRow label="Period" value={`${detail.period_start} to ${detail.period_end}`} />
              <DetailRow label="Status" value={detail.is_finalized ? "Finalized" : "Pending"} />
            </div>
            <div className="rounded-lg border border-border p-3">
              <div className="flex justify-between py-1">
                <span className="text-ink-soft">Base salary</span>
                <span className="text-ink">PKR {formatMoney(detail.base_salary)}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-ink-soft">Total deductions</span>
                <span className="text-ink">PKR {formatMoney(detail.total_deductions)}</span>
              </div>
              <div className="mt-1 flex justify-between border-t border-border py-1 font-semibold">
                <span className="text-ink">Net salary</span>
                <span className="text-ink">PKR {formatMoney(detail.net_salary)}</span>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center sm:grid-cols-5">
              <AttendanceTile label="Present" value={detail.days_present} />
              <AttendanceTile label="Absent" value={detail.days_absent} />
              <AttendanceTile label="Late" value={detail.days_late} />
              <AttendanceTile label="Half-day" value={detail.days_half_day} />
              <AttendanceTile label="Leave" value={detail.days_leave} />
            </div>
            {detail.notes && <p className="text-ink-soft">Notes: {detail.notes}</p>}
            <p className="text-xs text-ink-faint">
              Per-type deduction breakdown is only shown right after generation (Generate Salary tab) - the payroll rule
              used may have changed since this record was created, so it isn't reconstructed here for historical
              records. The totals above are exactly what the backend calculated and stored at generation time.
            </p>
          </div>
        )}
      </Dialog>

      <ConfirmDialog
        open={finalizeTarget !== null}
        onClose={() => setFinalizeTarget(null)}
        onConfirm={finalize}
        title="Finalize this salary record?"
        description="This locks the record - it cannot be finalized again and this action cannot be undone from here."
        confirmLabel="Yes, finalize"
        confirmVariant="primary"
        busy={busyId === finalizeTarget?.id}
      />
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-ink-faint">{label}</p>
      <p className="text-ink">{value}</p>
    </div>
  );
}

function AttendanceTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border p-2">
      <p className="text-lg font-semibold text-ink">{value}</p>
      <p className="text-xs text-ink-faint">{label}</p>
    </div>
  );
}
