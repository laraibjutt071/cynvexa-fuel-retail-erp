/** A lightweight label that groups the cards below it into a named
 * section (Overview, Operations, Analytics, Reference) - purely visual
 * organization, no new data or behavior. */
export function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="pt-2 text-xs font-semibold uppercase tracking-wider text-ink-faint first:pt-0">{children}</h2>
  );
}
