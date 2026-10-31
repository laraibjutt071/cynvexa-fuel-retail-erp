"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { downloadFromResponse } from "@/lib/download";

/** A button that downloads a CSV export through authFetch (the backend's
 * export endpoints require a bearer token, so a plain link won't work). */
export function ExportButton({ path, filename }: { path: string; filename: string }) {
  const { authFetch } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      const response = await authFetch(path);
      await downloadFromResponse(response, filename);
    } catch {
      setError("Export failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={handleClick}
        disabled={busy}
        className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-elevated disabled:opacity-50"
      >
        {busy ? "Exporting…" : "Export CSV"}
      </button>
      {error && <span className="text-xs text-danger-600">{error}</span>}
    </div>
  );
}
