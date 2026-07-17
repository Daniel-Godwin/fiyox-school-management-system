"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { me, clearToken, getToken, ROLE_LABEL, User } from "@/lib/api";
import { ToastProvider } from "@/components/Toast";

const NAV: { href: string; label: string; roles: User["role"][] }[] = [
  { href: "/dashboard", label: "Overview",
    roles: ["super_admin", "school_admin", "bursar", "teacher", "student", "parent"] },
  { href: "/dashboard/schools", label: "Schools",
    roles: ["super_admin"] },
  { href: "/dashboard/students", label: "Students",
    roles: ["super_admin", "school_admin", "teacher", "bursar"] },
  { href: "/dashboard/setup", label: "School setup",
    roles: ["super_admin", "school_admin"] },
  { href: "/dashboard/scores", label: "Score entry",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/attendance", label: "Attendance",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/results", label: "Results",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/timetable", label: "Timetable",
    roles: ["super_admin", "school_admin", "teacher", "parent", "student"] },
  { href: "/dashboard/fees", label: "Fees",
    roles: ["super_admin", "school_admin", "bursar"] },
  { href: "/dashboard/end-of-term", label: "End of term",
    roles: ["super_admin", "school_admin"] },
  { href: "/dashboard/wards", label: "My wards",
    roles: ["parent", "student"] },
  { href: "/dashboard/users", label: "Users",
    roles: ["super_admin", "school_admin"] },
  { href: "/dashboard/account", label: "Account",
    roles: ["super_admin", "school_admin", "bursar", "teacher", "student", "parent"] },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);

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

  const [menuOpen, setMenuOpen] = useState(false);

  // close the drawer whenever the route changes (i.e. a nav item was tapped)
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  if (!user) {
    return (
      <main className="min-h-screen grid place-items-center text-ink-soft text-sm">
        Loading your workspace…
      </main>
    );
  }

  const items = NAV.filter((n) => n.roles.includes(user.role));

  const navLinks = items.map((n) => {
    const active = pathname === n.href;
    return (
      <Link
        key={n.href}
        href={n.href}
        className={`rounded-md px-3 py-2.5 text-[15px] md:text-sm ${
          active ? "bg-white/15 font-medium" : "text-white/75 hover:bg-white/10"
        }`}
      >
        {n.label}
      </Link>
    );
  });

  return (
    <div className="min-h-screen md:grid md:grid-cols-[230px_1fr]">
      {/* ---- phone/tablet top bar ---- */}
      <header className="md:hidden sticky top-0 z-40 flex items-center justify-between bg-ink text-white px-4 py-3">
        <span className="display text-lg font-bold">Fiyox</span>
        <button
          onClick={() => setMenuOpen((o) => !o)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          className="flex h-11 w-11 items-center justify-center rounded-md hover:bg-white/10"
        >
          {/* hamburger / close, pure CSS so no icon library needed */}
          <span className="relative block h-4 w-6">
            <span className={`absolute left-0 top-0 h-0.5 w-6 bg-white transition-transform ${menuOpen ? "translate-y-[7px] rotate-45" : ""}`} />
            <span className={`absolute left-0 top-[7px] h-0.5 w-6 bg-white transition-opacity ${menuOpen ? "opacity-0" : ""}`} />
            <span className={`absolute left-0 top-[14px] h-0.5 w-6 bg-white transition-transform ${menuOpen ? "-translate-y-[7px] -rotate-45" : ""}`} />
          </span>
        </button>
      </header>

      {/* ---- phone/tablet slide-down drawer ---- */}
      {menuOpen && (
        <div className="md:hidden fixed inset-0 z-30 bg-black/40" onClick={() => setMenuOpen(false)}>
          <nav
            className="mt-[52px] bg-ink text-white px-4 pb-6 pt-2 flex flex-col gap-1 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {navLinks}
            <div className="mt-3 border-t border-white/15 pt-3 flex items-center justify-between">
              <p className="text-xs text-white/60">
                {user.first_name} {user.last_name} · {ROLE_LABEL[user.role]}
              </p>
              <button onClick={signOut} className="text-sm text-brass tap-target px-2">
                Sign out
              </button>
            </div>
          </nav>
        </div>
      )}

      {/* ---- desktop sidebar ---- */}
      <aside className="hidden md:flex bg-ink text-white flex-col py-6">
        <div className="px-5 mb-8">
          <span className="display text-xl font-bold">Fiyox</span>
        </div>
        <nav className="flex flex-col gap-1 px-3">{navLinks}</nav>
        <div className="mt-auto px-5 pt-6">
          <p className="text-xs text-white/60">
            {user.first_name} {user.last_name}
            <br />
            {ROLE_LABEL[user.role]}
          </p>
          <button onClick={signOut} className="mt-2 text-xs text-brass hover:underline">
            Sign out
          </button>
        </div>
      </aside>

      <main className="p-4 sm:p-5 md:p-8 max-w-full overflow-x-hidden">
        <ToastProvider>{children}</ToastProvider>
      </main>
    </div>
  );
}
