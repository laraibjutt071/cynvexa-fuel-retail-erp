/**
 * Consistent display formatting for money and litre quantities across the
 * app. Every API amount arrives as a decimal-safe string (never a JS
 * number - see backend's own Decimal discipline); these helpers format
 * that string for display only and never do arithmetic on it, so they
 * cannot introduce the floating-point error the backend goes out of its
 * way to avoid.
 *
 * No currency symbol is added. `Organization.currency_code` exists on the
 * backend (ASSUMPTIONS.md #19) but is not currently exposed to the
 * frontend at all - inventing a "Rs." or "$" prefix here would be a
 * guess, not a real integration. This is a named, honest limitation
 * (see docs/PHASE_4_DESIGN_SYSTEM_REPORT.md), not an oversight.
 */

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** "140000" -> "140,000.00". Returns an em dash for null/invalid input. */
export function formatMoney(value: string | number | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return "—";
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** "10000.500" -> "10,000.500 L". Only inserts thousands separators into
 * the integer part - the fractional digits are passed through exactly as
 * the backend sent them, never rounded or trimmed. A reading recorded to
 * 3 decimal places (NUMERIC(14,3)) is meaningfully different from the
 * same value rounded to 0 - toLocaleString's default rounding would
 * silently collapse "100.000" to "100", losing that precision. */
export function formatLitres(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const str = typeof value === "number" ? String(value) : value;
  if (!/^-?\d+(\.\d+)?$/.test(str.trim())) return "—";
  const [intPart, fracPart] = str.trim().split(".");
  const withSeparators = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${withSeparators}${fracPart ? `.${fracPart}` : ""} L`;
}

/** Plain thousands-separated number, no unit - for counts, not money or litres. */
export function formatNumber(value: string | number | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return "—";
  return n.toLocaleString();
}
