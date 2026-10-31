/**
 * Triggers a browser download for a CSV (or other file) response fetched
 * through authFetch. The backend's export endpoints require a bearer
 * token, so a plain `<a href=...>` won't carry auth - this fetches the
 * body as a blob and downloads it via a short-lived object URL instead.
 */
export async function downloadFromResponse(response: Response, fallbackFilename: string): Promise<void> {
  if (!response.ok) {
    throw new Error(`Export failed with status ${response.status}`);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? fallbackFilename;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
