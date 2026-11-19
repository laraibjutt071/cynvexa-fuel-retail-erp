"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Clock, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/components/ui/Toast";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextInput } from "@/components/ui/Field";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Dialog } from "@/components/ui/Dialog";
import type { SupportSession } from "@/lib/types";

export const SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES = [15, 30, 60];

const STATUS_TONE: Record<SupportSession["status"], BadgeTone> = {
  active: "success",
  ended: "neutral",
  expired: "neutral",
};

function formatCountdown(expiresAt: string): string {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
}

export function SupportSessionPanel({
  orgId,
  onSessionChange,
}: {
  orgId: string;
  onSessionChange: (session: SupportSession | null) => void;
}) {
  const { authFetch } = useAuth();
  const { notify } = useToast();

  const [activeSession, setActiveSession] = useState<SupportSession | null | undefined>(undefined);
  const [history, setHistory] = useState<SupportSession[]>([]);
  const [startOpen, setStartOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const loadActive = useCallback(async () => {
    const resp = await authFetch("/platform/support-sessions/active");
    const session: SupportSession | null = resp.ok ? await resp.json() : null;
    setActiveSession(session);
    onSessionChange(session);
  }, [authFetch, onSessionChange]);

  const loadHistory = useCallback(async () => {
    const resp = await authFetch("/platform/support-sessions");
    if (resp.ok) setHistory(await resp.json());
  }, [authFetch]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadActive();
    loadHistory();
  }, [loadActive, loadHistory]);

  useEffect(() => {
    if (!activeSession || activeSession.status !== "active") return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [activeSession]);

  const isForThisOrg = activeSession?.status === "active" && activeSession.organization_id === orgId;

  async function handleEnd() {
    if (!activeSession) return;
    const resp = await authFetch(`/platform/support-sessions/${activeSession.id}/end`, { method: "POST" });
    if (!resp.ok) {
      notify("error", "Could not end the support session.");
      return;
    }
    notify("success", "Support session ended.");
    await loadActive();
    await loadHistory();
  }

  return (
    <>
      {activeSession === undefined ? null : isForThisOrg ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-warning-300 bg-warning-50 px-4 py-3">
          <div className="flex items-center gap-2 text-sm">
            <ShieldCheck className="h-4 w-4 shrink-0 text-warning-600" aria-hidden />
            <span className="font-semibold text-warning-700">
              Support session active - inspecting {activeSession.organization_name}
              {activeSession.station_name ? ` / ${activeSession.station_name}` : " (org-wide)"}
            </span>
            <span className="flex items-center gap-1 text-warning-600">
              <Clock className="h-3.5 w-3.5" aria-hidden />
              {formatCountdown(activeSession.expires_at)}
            </span>
          </div>
          <Button size="sm" variant="secondary" onClick={handleEnd}>
            End support session
          </Button>
        </div>
      ) : activeSession?.status === "active" ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface-muted px-4 py-3 text-sm text-ink-soft">
          <span>
            You have an active support session for another organization (
            <Link href={`/dashboard/platform/organizations/${activeSession.organization_id}`} className="text-accent hover:underline">
              {activeSession.organization_name}
            </Link>
            ). End it before starting one here.
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface-muted px-4 py-3">
          <p className="text-sm text-ink-soft">
            Viewing this organization's stations, users and roles requires a time-limited, read-only support session.
          </p>
          <Button size="sm" onClick={() => setStartOpen(true)}>
            Start support session
          </Button>
        </div>
      )}

      {history.length > 0 && (
        <Card title="Support session history" description="Your own sessions for this organization and others.">
          <ul className="divide-y divide-border">
            {history.slice(0, 10).map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <div>
                  <p className="text-ink">
                    {s.organization_name}
                    {s.station_name ? ` / ${s.station_name}` : ""}
                  </p>
                  <p className="text-xs text-ink-faint">{s.reason}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-ink-faint">{new Date(s.created_at).toLocaleString()}</span>
                  <Badge tone={STATUS_TONE[s.status]}>{s.status}</Badge>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <StartSupportSessionDialog
        open={startOpen}
        onClose={() => setStartOpen(false)}
        orgId={orgId}
        onStarted={async () => {
          setStartOpen(false);
          await loadActive();
          await loadHistory();
        }}
      />
    </>
  );
}

function StartSupportSessionDialog({
  open,
  onClose,
  orgId,
  onStarted,
}: {
  open: boolean;
  onClose: () => void;
  orgId: string;
  onStarted: () => void;
}) {
  const { authFetch } = useAuth();
  const { notify } = useToast();
  const [reason, setReason] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES[0]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setReason("");
      setDurationMinutes(SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES[0]);
      setError(null);
    }
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const resp = await authFetch("/platform/support-sessions", {
        method: "POST",
        body: JSON.stringify({
          organization_id: orgId,
          station_id: null,
          reason,
          duration_minutes: durationMinutes,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({ detail: "Could not start a support session." }));
        setError(body.detail ?? "Could not start a support session.");
        return;
      }
      notify("success", "Support session started.");
      onStarted();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Start support session" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-ink-soft">
          Grants time-limited, read-only access to this organization's stations, users, fuel, shift and financial
          records. No write access of any kind - and every view you access while it's active is logged.
        </p>
        <Field label="Reason" required hint="At least 10 characters - visible in the audit log.">
          {(id) => (
            <TextInput id={id} required minLength={10} value={reason} onChange={(e) => setReason(e.target.value)} />
          )}
        </Field>
        <Field label="Duration" required>
          {(id) => (
            <Select id={id} value={durationMinutes} onChange={(e) => setDurationMinutes(Number(e.target.value))}>
              {SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES.map((m) => (
                <option key={m} value={m}>
                  {m} minutes
                </option>
              ))}
            </Select>
          )}
        </Field>
        <p className="text-xs text-ink-faint">
          This session is organization-wide. Station-scoped sessions aren't available from this screen yet.
        </p>
        {error && <p className="text-sm text-danger-600">{error}</p>}
        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={submitting}>
            Start session
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
