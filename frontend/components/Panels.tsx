/**
 * Small shared presentational pieces for the dashboards — a KPI tile and a
 * titled card — so CBT, Timetable, Attendance and Admissions share one look.
 */
export const BRAND = {
  ink: "#0b1f3a", inkSoft: "#274264", ledger: "#1e7a4f", brass: "#c8a24b", sanction: "#b4232a",
};

export function Kpi({
  label, value, hint, accent = BRAND.ink, href,
}: { label: string; value: string; hint?: string; accent?: string; href?: string }) {
  const inner = (
    <>
      <span className="absolute left-0 top-0 h-full w-1" style={{ background: accent }} />
      <p className="text-xs uppercase tracking-wide text-ink-soft">{label}</p>
      <p className="display text-2xl font-bold mt-1 tabular" style={{ color: accent }}>{value}</p>
      {hint && <p className="text-xs text-ink-soft mt-1">{hint}</p>}
    </>
  );
  const cls = "group relative bg-card border border-line rounded-xl p-4 overflow-hidden " +
    "transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-md";
  return href
    ? <a href={href} className={`${cls} block`}>{inner}</a>
    : <div className={cls}>{inner}</div>;
}

export function Card({
  title, children, className = "", right,
}: { title?: string; children: React.ReactNode; className?: string; right?: React.ReactNode }) {
  return (
    <div className={`bg-card border border-line rounded-xl p-5 ${className}`}>
      {(title || right) && (
        <div className="flex items-center justify-between mb-3">
          {title && <p className="text-xs text-ink-soft uppercase tracking-wide">{title}</p>}
          {right}
        </div>
      )}
      {children}
    </div>
  );
}
