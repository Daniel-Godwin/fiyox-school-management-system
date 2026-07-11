"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, me, User } from "@/lib/api";

type Student = { id: string };

export default function Overview() {
  const [user, setUser] = useState<User | null>(null);
  const [studentCount, setStudentCount] = useState<number | null>(null);

  useEffect(() => {
    me().then((u) => {
      setUser(u);
      if (["super_admin", "school_admin", "teacher", "bursar"].includes(u.role)) {
        api<Student[]>("/api/students")
          .then((s) => setStudentCount(s.length))
          .catch(() => setStudentCount(null));
      }
    });
  }, []);

  if (!user) return null;
  const staff = ["super_admin", "school_admin", "teacher", "bursar"].includes(user.role);

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold">
        Welcome, {user.first_name}
      </h1>
      <p className="text-ink-soft text-sm mt-1">
        {staff
          ? "Here is where your school's day-to-day work happens."
          : "Here you can follow your ward's results, fees, and attendance."}
      </p>

      {staff && (
        <div className="grid sm:grid-cols-2 gap-4 mt-8">
          <Link
            href="/dashboard/students"
            className="bg-card border border-line rounded-xl p-5 hover:border-ink/30"
          >
            <p className="text-xs uppercase tracking-wide text-ink-soft">Students</p>
            <p className="display text-3xl font-semibold mt-1 tabular">
              {studentCount ?? "—"}
            </p>
            <p className="text-sm text-ink-soft mt-2">View the register →</p>
          </Link>

          <div className="bg-card border border-line rounded-xl p-5">
            <p className="text-xs uppercase tracking-wide text-ink-soft">Coming next</p>
            <p className="text-sm mt-2 text-ink-soft leading-relaxed">
              Results entry, fee collection, and attendance marking arrive here as
              the dashboards are built out.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
