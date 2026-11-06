"use client";

/**
 * Lightweight, dependency-free SVG charts for the analytics dashboard.
 * Animated on mount and interactive on hover — no charting library, so the
 * page stays small and fast on phones.
 */
import { useEffect, useState } from "react";

function useMounted(delay = 40) {
  const [m, setM] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setM(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  return m;
}

export type Segment = { label: string; value: number; color: string };

/** Donut with a legend, a center total, and hover-to-inspect each slice. */
export function Donut({
  data, size = 168, thickness = 24, centerSub = "total",
}: { data: Segment[]; size?: number; thickness?: number; centerSub?: string }) {
  const mounted = useMounted();
  const [active, setActive] = useState<number | null>(null);
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;

  let acc = 0;
  const segs = data.map((d) => {
    const len = (d.value / total) * c;
    const seg = { ...d, len, offset: acc };
    acc += len;
    return seg;
  });

  const shown = active != null ? data[active] : null;

  return (
    <div className="flex flex-col sm:flex-row items-center gap-4 sm:gap-5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                  stroke="var(--color-line,#e5e7eb)" strokeWidth={thickness} />
          {segs.map((s, i) => (
            <circle
              key={i} cx={size / 2} cy={size / 2} r={r} fill="none"
              stroke={s.color} strokeLinecap="butt"
              strokeWidth={active === i ? thickness + 4 : thickness}
              strokeDasharray={`${mounted ? s.len : 0} ${c}`}
              strokeDashoffset={-s.offset}
              style={{ transition: "stroke-dasharray .9s cubic-bezier(.4,0,.2,1), stroke-width .15s", cursor: "pointer" }}
              onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
            />
          ))}
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center pointer-events-none">
          <div>
            <div className="display text-2xl font-bold tabular">
              {(shown ? shown.value : total).toLocaleString()}
            </div>
            <div className="text-xs text-ink-soft capitalize">{shown ? shown.label : centerSub}</div>
          </div>
        </div>
      </div>
      <ul className="space-y-2 text-sm w-full sm:w-auto min-w-0">
        {data.map((d, i) => {
          const pct = Math.round((d.value / total) * 100);
          return (
            <li key={i}
                className={`flex items-center gap-2 rounded-md px-2 py-1 -mx-2 transition-colors ${active === i ? "bg-paper" : ""}`}
                onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}>
              <span className="h-3 w-3 rounded-full shrink-0" style={{ background: d.color }} />
              <span className="truncate text-ink-soft">{d.label}</span>
              <span className="ml-auto tabular font-medium">{d.value.toLocaleString()}</span>
              <span className="tabular text-ink-soft w-10 text-right">{pct}%</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Circular progress ring for a single 0–100 value, animated on mount. */
export function ProgressRing({
  value, label, color = "#1e7a4f", size = 148, thickness = 14, sub,
}: { value: number | null; label: string; color?: string; size?: number; thickness?: number; sub?: string }) {
  const mounted = useMounted();
  const v = Math.max(0, Math.min(100, value ?? 0));
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const shown = mounted ? (v / 100) * c : 0;
  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                  stroke="var(--color-line,#e5e7eb)" strokeWidth={thickness} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color}
                  strokeWidth={thickness} strokeLinecap="round"
                  strokeDasharray={`${shown} ${c}`}
                  style={{ transition: "stroke-dasharray 1s cubic-bezier(.4,0,.2,1)" }} />
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="display text-2xl font-bold tabular">
              {value === null ? "—" : `${Math.round(v)}%`}
            </div>
            {sub && <div className="text-xs text-ink-soft">{sub}</div>}
          </div>
        </div>
      </div>
      <p className="text-sm text-ink-soft mt-2">{label}</p>
    </div>
  );
}

/** Vertical column chart, animated heights, hover to highlight. */
export function Columns({
  data, height = 150,
}: { data: { label: string; value: number; color?: string }[]; height?: number }) {
  const mounted = useMounted();
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="flex items-end gap-2" style={{ height: height + 28 }}>
      {data.map((d, i) => {
        const h = mounted ? Math.max(4, (d.value / max) * height) : 0;
        return (
          <div key={i} className="flex-1 flex flex-col items-center justify-end gap-1 min-w-0"
               onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}>
            <span className={`text-xs tabular font-medium transition-opacity ${active === i ? "opacity-100" : "opacity-70"}`}>
              {d.value}
            </span>
            <div className="w-full rounded-t-md" title={`${d.label}: ${d.value}`}
                 style={{
                   height: h, background: d.color ?? "var(--color-ink,#0b1f3a)",
                   transition: "height .9s cubic-bezier(.4,0,.2,1)",
                   opacity: active == null || active === i ? 1 : 0.55,
                 }} />
            <span className="text-xs text-ink-soft truncate w-full text-center">{d.label}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Horizontal bar row (kept for class lists), animated width. */
export function BarRow({
  label, value, max, suffix = "", color = "var(--color-ink,#0b1f3a)",
}: { label: string; value: number; max: number; suffix?: string; color?: string }) {
  const mounted = useMounted();
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-24 shrink-0 text-ink-soft truncate">{label}</span>
      <div className="flex-1 h-5 rounded bg-paper overflow-hidden border border-line">
        <div className="h-full rounded"
             style={{ width: `${mounted ? Math.max(pct, 2) : 0}%`, background: color,
                      transition: "width .9s cubic-bezier(.4,0,.2,1)" }} />
      </div>
      <span className="w-16 shrink-0 text-right tabular font-medium">{value}{suffix}</span>
    </div>
  );
}
