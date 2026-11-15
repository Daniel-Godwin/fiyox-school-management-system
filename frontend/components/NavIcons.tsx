/**
 * Line icons for the sidebar — one per destination. Inline SVG (no icon
 * dependency), 20×20, 1.6 stroke, currentColor so they inherit nav text colour.
 */
import React from "react";

const P = (d: string) => <path d={d} />;

const PATHS: Record<string, React.ReactNode> = {
  overview: <>{P("M3 3h7v7H3z")}{P("M14 3h7v4h-7z")}{P("M14 11h7v10h-7z")}{P("M3 14h7v7H3z")}</>,
  schools: <>{P("M3 21h18")}{P("M5 21V7l7-4 7 4v14")}{P("M9 21v-6h6v6")}{P("M9 10h.01M15 10h.01")}</>,
  students: <>{P("M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2")}<circle cx="9" cy="7" r="4" />{P("M22 21v-2a4 4 0 0 0-3-3.87")}{P("M16 3.13a4 4 0 0 1 0 7.75")}</>,
  admissions: <>{P("M9 2h6a1 1 0 0 1 1 1v1H8V3a1 1 0 0 1 1-1z")}{P("M8 4H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h8")}{P("M16 4h2a2 2 0 0 1 2 2v5")}{P("M18 14v6M15 17h6")}</>,
  setup: <>{P("M4 7h11M19 7h1M4 12h1M9 12h11M4 17h7M15 17h5")}<circle cx="17" cy="7" r="2" /><circle cx="7" cy="12" r="2" /><circle cx="13" cy="17" r="2" /></>,
  scores: <>{P("M12 20h9")}{P("M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z")}</>,
  attendance: <>{P("M8 2v4M16 2v4M3 10h18")}<rect x="3" y="4" width="18" height="18" rx="2" />{P("M9 16l2 2 4-4")}</>,
  pending: <>{P("M3 6h18M3 12h12M3 18h8")}<circle cx="18" cy="17" r="4" />{P("M18 15.5V17l1 1")}</>,
  results: <>{P("M14 2v6h6")}{P("M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z")}{P("M8 13h6M8 17h5")}</>,
  annual: <>{P("M4 19.5A2.5 2.5 0 0 1 6.5 17H20")}{P("M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z")}{P("M9 7h7")}</>,
  cbt: <>{P("M3 4h18v12H3z")}{P("M8 20h8M12 16v4")}{P("M7 9l2 2-2 2M12 13h4")}</>,
  analytics: <>{P("M3 3v18h18")}{P("M7 14l3-4 3 3 4-6")}</>,
  timetable: <>{P("M8 2v4M16 2v4M3 10h18")}<rect x="3" y="4" width="18" height="18" rx="2" />{P("M8 14h2M14 14h2M8 18h2M14 18h2")}</>,
  fees: <>{P("M2 7h20v12H2z")}{P("M2 11h20")}<circle cx="12" cy="15" r="1.5" /></>,
  finance: <>{P("M3 3v18h18")}{P("M7 15l3-3 2 2 5-6")}{P("M17 8h3v3")}</>,
  delivery: <>{P("M22 2L11 13")}{P("M22 2l-7 20-4-9-9-4z")}</>,
  endterm: <>{P("M22 10L12 5 2 10l10 5 10-5z")}{P("M6 12v5c0 1 2.7 2.5 6 2.5s6-1.5 6-2.5v-5")}{P("M22 10v6")}</>,
  users: <>{P("M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2")}<circle cx="9" cy="7" r="4" /><circle cx="18" cy="8" r="2.5" />{P("M22 19a3.5 3.5 0 0 0-5-3.2")}</>,
  account: <>{P("M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2")}<circle cx="12" cy="7" r="4" /></>,
  wards: <>{P("M9 21v-6a3 3 0 0 1 6 0v6")}<circle cx="12" cy="6" r="3" />{P("M4 21v-4M20 21v-4")}</>,
};

export default function NavIcon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
         className={`h-[18px] w-[18px] shrink-0 ${className}`}>
      {PATHS[name] ?? PATHS.overview}
    </svg>
  );
}
