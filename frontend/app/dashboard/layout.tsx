"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { me, clearToken, getToken, ROLE_LABEL, User,
         impersonationInfo, exitImpersonation, ActingAs } from "@/lib/api";
import { ToastProvider } from "@/components/Toast";
import SyncStatus from "@/components/SyncStatus";
import FiyoxLoader from "@/components/FiyoxLoader";
import ForcePasswordChange from "@/components/ForcePasswordChange";
import NavIcon from "@/components/NavIcons";

type NavItem = { href: string; label: string; icon: string; group: string; roles: User["role"][] };

// grouped so a long list reads as a few short sections instead of one wall
const GROUP_ORDER = ["Main", "People", "Academics", "Insight", "Money", "Settings"];

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: "overview", group: "Main",
    roles: ["super_admin", "school_admin", "principal", "bursar", "teacher", "student", "parent"] },
  { href: "/dashboard/wards", label: "My wards", icon: "wards", group: "Main",
    roles: ["parent", "student"] },

  { href: "/dashboard/schools", label: "Schools", icon: "schools", group: "People",
    roles: ["super_admin"] },
  { href: "/dashboard/students", label: "Students", icon: "students", group: "People",
    roles: ["super_admin", "school_admin", "principal", "teacher", "bursar"] },
  { href: "/dashboard/admissions", label: "Admissions", icon: "admissions", group: "People",
    roles: ["super_admin", "school_admin", "principal"] },
  { href: "/dashboard/users", label: "Users", icon: "users", group: "People",
    roles: ["super_admin", "school_admin"] },

  { href: "/dashboard/scores", label: "Score entry", icon: "scores", group: "Academics",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/attendance", label: "Attendance", icon: "attendance", group: "Academics",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/results", label: "Results", icon: "results", group: "Academics",
    roles: ["super_admin", "school_admin", "principal", "teacher"] },
  { href: "/dashboard/annual", label: "Annual reports", icon: "annual", group: "Academics",
    roles: ["super_admin", "school_admin", "principal", "teacher"] },
  { href: "/dashboard/cbt", label: "CBT tests", icon: "cbt", group: "Academics",
    roles: ["super_admin", "school_admin", "principal", "teacher", "student"] },
  { href: "/dashboard/timetable", label: "Timetable", icon: "timetable", group: "Academics",
    roles: ["super_admin", "school_admin", "principal", "teacher", "parent", "student"] },
  { href: "/dashboard/pending", label: "Pending changes", icon: "pending", group: "Academics",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/end-of-term", label: "End of term", icon: "endterm", group: "Academics",
    roles: ["super_admin", "school_admin"] },

  { href: "/dashboard/analytics", label: "Analytics", icon: "analytics", group: "Insight",
    roles: ["super_admin", "school_admin", "principal"] },

  { href: "/dashboard/fees", label: "Fees", icon: "fees", group: "Money",
    roles: ["super_admin", "school_admin", "principal", "bursar"] },
  { href: "/dashboard/finance", label: "Finance", icon: "finance", group: "Money",
    roles: ["school_admin", "principal", "bursar"] },
  { href: "/dashboard/delivery", label: "Delivery log", icon: "delivery", group: "Money",
    roles: ["school_admin", "bursar"] },

  { href: "/dashboard/setup", label: "School setup", icon: "setup", group: "Settings",
    roles: ["super_admin", "school_admin"] },
  { href: "/dashboard/account", label: "Account", icon: "account", group: "Settings",
    roles: ["super_admin", "school_admin", "principal", "bursar", "teacher", "student", "parent"] },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [acting, setActing] = useState<ActingAs | null>(null);

  useEffect(() => { setActing(impersonationInfo()); }, [user]);

  function exitAsOwner() {
    exitImpersonation();
    window.location.href = "/dashboard/schools";
  }

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    me()
      .then(setUser)
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
  }, [router]);

  function signOut() {
    clearToken();
    router.replace("/login");
  }

  // reload the session (e.g. after the password gate is cleared) so the flag updates
  function refreshUser() {
    me().then(setUser).catch(() => {});
  }

  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  // remember the desktop sidebar's collapsed state per browser
  useEffect(() => {
    try { setCollapsed(localStorage.getItem("fiyox:nav-collapsed") === "1"); } catch { /* ignore */ }
  }, []);
  function toggleCollapsed() {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem("fiyox:nav-collapsed", next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  }

  // close the drawer whenever the route changes (i.e. a nav item was tapped)
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  // lock the background page from scrolling while the mobile drawer is open
  useEffect(() => {
    if (!menuOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [menuOpen]);

  // idle auto-logout: schools often share a computer, so sign out after a spell
  // of no activity to protect whoever's data is on screen
  useEffect(() => {
    if (!user) return;
    const IDLE_MS = 30 * 60 * 1000; // 30 minutes
    let timer: ReturnType<typeof setTimeout>;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        clearToken();
        router.replace("/login");
      }, IDLE_MS);
    };
    const events = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }));
    reset();
    return () => {
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [user, router]);

  if (!user) {
    return <FiyoxLoader fullScreen label="Loading your workspace…" />;
  }

  const items = NAV.filter((n) => n.roles.includes(user.role));

  function renderNav(mini: boolean) {
    return GROUP_ORDER.map((group) => {
      const groupItems = items.filter((n) => n.group === group);
      if (groupItems.length === 0) return null;
      return (
        <div key={group} className={mini ? "" : "mb-1"}>
          {!mini && group !== "Main" && (
            <p className="px-3 pt-4 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/35">
              {group}
            </p>
          )}
          <div className="flex flex-col gap-0.5">
            {groupItems.map((n) => {
              const active = pathname === n.href;
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  title={mini ? n.label : undefined}
                  className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] md:text-sm transition-colors ${
                    mini ? "md:justify-center md:px-0 md:py-2.5" : ""
                  } ${
                    active
                      ? "bg-white text-ink font-semibold shadow-sm"
                      : "text-white/70 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  {active && !mini && (
                    <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-brass" />
                  )}
                  <NavIcon name={n.icon} className={active ? "text-ledger" : ""} />
                  {!mini && <span className="truncate">{n.label}</span>}
                </Link>
              );
            })}
          </div>
        </div>
      );
    });
  }

  return (
    <>
    {acting && (
      <div className="flex items-center justify-between gap-3 bg-brass text-ink px-4 py-2 text-sm">
        <span className="truncate">
          Support mode — viewing <strong>{acting.school}</strong> as {acting.name}
        </span>
        <button onClick={exitAsOwner}
                className="shrink-0 rounded-md bg-ink text-white px-3 py-1 text-xs font-medium hover:bg-ink-soft">
          Exit to owner
        </button>
      </div>
    )}
    <div className="min-h-screen md:flex bg-paper">
      {/* ---- desktop sidebar ---- */}
      <aside
        className="hidden md:flex md:flex-col shrink-0 self-start sticky top-0 h-screen bg-ink text-white transition-[width] duration-200 ease-out"
        style={{ width: collapsed ? 72 : 244 }}
      >
        <div className={`flex items-center gap-2 py-5 ${collapsed ? "justify-center px-2" : "px-5"}`}>
          <img src="/fiyox-logo-white.png" alt="Fiyox"
               style={{ height: collapsed ? 30 : 40, width: "auto" }} />
        </div>
        {!collapsed && <div className="px-5 pb-3"><SyncStatus /></div>}
        <nav className="flex-1 overflow-y-auto overscroll-contain px-3 pb-4">
          {renderNav(collapsed)}
        </nav>
        <div className={`border-t border-white/10 ${collapsed ? "px-2 py-3" : "px-4 py-4"}`}>
          {!collapsed && (
            <div className="mb-2 flex items-center gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold">
                {(user.first_name?.[0] ?? "") + (user.last_name?.[0] ?? "")}
              </span>
              <div className="min-w-0">
                <p className="truncate text-xs font-medium text-white">{user.first_name} {user.last_name}</p>
                <p className="truncate text-[11px] text-white/55">{ROLE_LABEL[user.role]}</p>
              </div>
            </div>
          )}
          <div className={`flex items-center ${collapsed ? "flex-col gap-2" : "justify-between"}`}>
            <button onClick={signOut} title="Sign out"
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-brass hover:bg-white/10">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
                   strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
              {!collapsed && "Sign out"}
            </button>
            <button onClick={toggleCollapsed} aria-label="Toggle sidebar"
                    className="flex h-8 w-8 items-center justify-center rounded-md text-white/60 hover:bg-white/10 hover:text-white">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                   strokeLinecap="round" strokeLinejoin="round"
                   className={`h-4 w-4 transition-transform ${collapsed ? "rotate-180" : ""}`}>
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* ---- content column ---- */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* phone/tablet top bar */}
        <header className="md:hidden sticky top-0 z-40 flex items-center justify-between bg-ink text-white px-4 py-3 shadow-sm">
          <div className="flex items-center gap-3">
            <img src="/fiyox-logo-white.png" alt="Fiyox" style={{ height: 30, width: "auto" }} />
            <SyncStatus />
          </div>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            className="flex h-11 w-11 items-center justify-center rounded-md hover:bg-white/10"
          >
            <span className="relative block h-4 w-6">
              <span className={`absolute left-0 top-0 h-0.5 w-6 bg-white transition-transform ${menuOpen ? "translate-y-[7px] rotate-45" : ""}`} />
              <span className={`absolute left-0 top-[7px] h-0.5 w-6 bg-white transition-opacity ${menuOpen ? "opacity-0" : ""}`} />
              <span className={`absolute left-0 top-[14px] h-0.5 w-6 bg-white transition-transform ${menuOpen ? "-translate-y-[7px] -rotate-45" : ""}`} />
            </span>
          </button>
        </header>

        <main className="flex-1 p-4 sm:p-5 md:p-8 max-w-full overflow-x-hidden">
          {user.must_change_password ? (
            <ForcePasswordChange onDone={refreshUser} />
          ) : (
            <>
              {user.email && !user.email_verified &&
                ["school_admin", "principal", "bursar", "teacher"].includes(user.role) && (
                <Link href="/dashboard/account"
                      className="mb-4 flex items-center gap-2 rounded-md border border-brass/40 bg-brass/10 px-4 py-2.5 text-sm text-brass-ink hover:bg-brass/20">
                  <span className="h-1.5 w-1.5 rounded-full bg-brass shrink-0" />
                  Your email isn&apos;t verified yet — tap to verify {user.email}.
                </Link>
              )}
              <ToastProvider>{children}</ToastProvider>
            </>
          )}
        </main>
      </div>
    </div>

    {/* ---- phone/tablet slide-out drawer (from the left) ---- */}
    <div className={`md:hidden fixed inset-0 z-50 ${menuOpen ? "" : "pointer-events-none"}`}
         aria-hidden={!menuOpen}>
      <div className={`absolute inset-0 bg-black/50 transition-opacity duration-200 ${menuOpen ? "opacity-100" : "opacity-0"}`}
           onClick={() => setMenuOpen(false)} />
      <nav className={`absolute left-0 top-0 h-full w-[82%] max-w-[300px] bg-ink text-white flex flex-col shadow-2xl transition-transform duration-200 ease-out ${menuOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between px-5 py-4">
          <img src="/fiyox-logo-white.png" alt="Fiyox" style={{ height: 32, width: "auto" }} />
          <button onClick={() => setMenuOpen(false)} aria-label="Close menu"
                  className="flex h-9 w-9 items-center justify-center rounded-md hover:bg-white/10 text-white/80">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                 strokeLinecap="round" className="h-5 w-5"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto overscroll-contain px-3 pb-4">
          {renderNav(false)}
        </div>
        <div className="border-t border-white/10 px-4 py-3 flex items-center justify-between">
          <p className="min-w-0 truncate text-xs text-white/60">
            {user.first_name} {user.last_name} · {ROLE_LABEL[user.role]}
          </p>
          <button onClick={signOut} className="shrink-0 text-sm text-brass tap-target px-2">Sign out</button>
        </div>
      </nav>
    </div>
    </>
  );
}
