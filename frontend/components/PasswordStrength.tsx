"use client";

/**
 * A small password strength meter. Purely advisory UI — the real rules are
 * enforced on the server. Scores on length and character variety and mirrors
 * the backend's "at least 8 characters" floor.
 */
export function scorePassword(pw: string): number {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  // all-identical characters are never "strong"
  if (new Set(pw).size === 1) return pw ? 1 : 0;
  return Math.min(score, 4);
}

const LABELS = ["Too short", "Weak", "Fair", "Good", "Strong"];
const COLORS = ["#b4232a", "#b4232a", "#c8a24b", "#1e7a4f", "#1e7a4f"];

export default function PasswordStrength({ value }: { value: string }) {
  if (!value) return null;
  const score = scorePassword(value);
  const pct = ((score + 1) / 5) * 100;
  return (
    <div className="mt-1.5">
      <div className="h-1.5 w-full rounded-full bg-line overflow-hidden">
        <div className="h-full rounded-full transition-all"
             style={{ width: `${pct}%`, background: COLORS[score] }} />
      </div>
      <p className="text-[11px] mt-1" style={{ color: COLORS[score] }}>
        {value.length < 8 ? "At least 8 characters" : LABELS[score]}
      </p>
    </div>
  );
}
