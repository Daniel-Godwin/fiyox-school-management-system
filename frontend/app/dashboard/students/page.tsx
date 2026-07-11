"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Student = {
  id: string;
  admission_number: string;
  first_name: string;
  last_name: string;
  gender: "male" | "female";
  is_active: boolean;
};

export default function StudentsPage() {
  const [students, setStudents] = useState<Student[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api<Student[]>("/api/students")
      .then(setStudents)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load students"),
      );
  }, []);

  const shown = (students ?? []).filter((s) =>
    `${s.admission_number} ${s.first_name} ${s.last_name}`
      .toLowerCase()
      .includes(q.toLowerCase()),
  );

  return (
    <div className="max-w-4xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Students</h1>
          <p className="text-ink-soft text-sm mt-1">
            The school register — {students ? `${students.length} enrolled` : "loading"}.
          </p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name or admission no."
          className="rounded-md border border-line bg-white px-3 py-2 text-sm w-64"
        />
      </div>

      {error && (
        <p role="alert" className="mt-6 text-sanction text-sm">
          {error}
        </p>
      )}

      {students && (
        <div className="mt-6 bg-card border border-line rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-ink text-white text-left">
                <th className="px-4 py-2.5 font-medium">Admission No.</th>
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Gender</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((s, i) => (
                <tr key={s.id} className={i % 2 ? "bg-paper/60" : ""}>
                  <td className="px-4 py-2.5 tabular">{s.admission_number}</td>
                  <td className="px-4 py-2.5">
                    {s.first_name} {s.last_name}
                  </td>
                  <td className="px-4 py-2.5 capitalize">{s.gender}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs ${
                        s.is_active
                          ? "bg-ledger/10 text-ledger"
                          : "bg-sanction/10 text-sanction"
                      }`}
                    >
                      {s.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-ink-soft">
                    {q
                      ? "No student matches that search."
                      : "No students yet. Import a class list to begin."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
