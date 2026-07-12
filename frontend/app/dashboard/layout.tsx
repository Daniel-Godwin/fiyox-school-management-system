"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { me, clearToken, getToken, ROLE_LABEL, User } from "@/lib/api";

const NAV: { href: string; label: string; roles: User["role"][] }[] = [
  { href: "/dashboard", label: "Overview",
    roles: ["super_admin", "school_admin", "bursar", "teacher", "student", "parent"] },
  { href: "/dashboard/students", label: "Students",
    roles: ["super_admin", "school_admin", "teacher", "bursar"] },
  { href: "/dashboard/scores", label: "Score entry",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/attendance", label: "Attendance",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/results", label: "Results",
    roles: ["super_admin", "school_admin", "teacher"] },
  { href: "/dashboard/fees", label: "Fees",
    roles: ["super_admin", "school_admin", "bursar"] },
  { href: "/dashboard/wards", label: "My wards",
    roles: ["parent", "student"] },
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

  if (!user) {
    return (
      <main className="min-h-screen grid place-items-center text-ink-soft text-sm">
        Loading your workspace…
      </main>
    );
  }

  const items = NAV.filter((n) => n.roles.includes(user.role));

  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className="bg-ink text-white flex md:flex-col items-center md:items-stretch justify-between md:justify-start px-4 py-3 md:py-6 md:px-0">
        <div className="md:px-5 md:mb-8">
          <span className="display text-xl font-semibold">Fiyox</span>
        </div>
        <nav className="flex md:flex-col gap-1 md:px-3">
          {items.map((n) => {
            const active = pathname === n.href;
            return (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-md px-3 py-2 text-sm ${
                  active ? "bg-white/15 font-medium" : "text-white/75 hover:bg-white/10"
                }`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="md:mt-auto md:px-5 md:pt-6">
          <p className="hidden md:block text-xs text-white/60">
            {user.first_name} {user.last_name}
            <br />
            {ROLE_LABEL[user.role]}
          </p>
          <button
            onClick={signOut}
            className="mt-0 md:mt-2 text-xs text-brass hover:underline"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="p-5 md:p-8">{children}</main>
    </div>
  );
}
