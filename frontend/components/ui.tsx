/**
 * Shared design-system primitives for the dashboards. One consistent page
 * header, badge, stat tile and empty state so every panel wears the same
 * skeleton. Pairs with Panels.tsx (Kpi, Card) and Button.tsx.
 */
import React from "react";
import Link from "next/link";

/* ---------- PageHeader: the standard top of every panel ---------- */
export function PageHeader({
  title, subtitle, actions, icon,
}: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-start gap-3 min-w-0">
        {icon && (
          <span className="mt-0.5 hidden sm:flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ink/5 text-ink">
            {icon}
          </span>
        )}
        <div className="min-w-0">
          <h1 className="display text-2xl font-bold text-ink leading-tight break-words">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-ink-soft">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
    </header>
  );
}

/* ---------- Badge: status pill ---------- */
const BADGE_TONE: Record<string, string> = {
  neutral: "bg-line text-ink-soft",
  success: "bg-ledger/10 text-ledger",
  warning: "bg-brass/15 text-brass-ink",
  danger: "bg-sanction/10 text-sanction",
  info: "bg-ink/5 text-ink",
};
export function Badge({
  children, tone = "neutral", dot = false,
}: { children: React.ReactNode; tone?: keyof typeof BADGE_TONE; dot?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_TONE[tone]}`}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />}
      {children}
    </span>
  );
}

/* ---------- StatTile: a KPI with an icon ---------- */
const TILE_TONE: Record<string, { text: string; chip: string }> = {
  ink: { text: "text-ink", chip: "bg-ink/5 text-ink" },
  ledger: { text: "text-ledger", chip: "bg-ledger/10 text-ledger" },
  brass: { text: "text-brass-ink", chip: "bg-brass/15 text-brass-ink" },
  sanction: { text: "text-sanction", chip: "bg-sanction/10 text-sanction" },
};
export function StatTile({
  label, value, hint, icon, tone = "ink", href,
}: {
  label: string; value: React.ReactNode; hint?: React.ReactNode; icon?: React.ReactNode;
  tone?: keyof typeof TILE_TONE; href?: string;
}) {
  const t = TILE_TONE[tone];
  const inner = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-ink-soft">{label}</p>
        {icon && <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${t.chip}`}>{icon}</span>}
      </div>
      <p className={`display text-3xl font-bold mt-2 tabular ${t.text}`}>{value}</p>
      {hint && <p className="mt-1.5 text-sm text-ink-soft">{hint}</p>}
    </>
  );
  const cls = "block bg-card border border-line rounded-xl p-5 card";
  return href
    ? <Link href={href} className={`${cls} card-interactive`}>{inner}</Link>
    : <div className={cls}>{inner}</div>;
}

/* ---------- EmptyState ---------- */
export function EmptyState({
  title, hint, icon, action,
}: { title: string; hint?: string; icon?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-line bg-card/50 px-6 py-12 text-center">
      {icon && <div className="mb-3 text-ink-soft/50">{icon}</div>}
      <p className="font-medium text-ink">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-sm text-ink-soft">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ---------- Skeleton row (loading) ---------- */
export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`block animate-pulse rounded-md bg-line/70 ${className}`} />;
}
