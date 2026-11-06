/**
 * Branded loading indicator — pure SVG + CSS (no JS animation library), so it
 * paints instantly, even before React hydrates, and adds zero bundle weight.
 *
 *  <FiyoxLoader />                      small inline spinner (e.g. on a button)
 *  <FiyoxLoader size={64} />            larger inline spinner
 *  <FiyoxLoader fullScreen label="…" /> full navy splash with the Fiyox mark
 */
export default function FiyoxLoader({
  size = 44,
  label,
  fullScreen = false,
  tone = "light",
}: {
  size?: number;
  label?: string;
  fullScreen?: boolean;
  /** "light" for light backgrounds, "dark" for the navy splash */
  tone?: "light" | "dark";
}) {
  const track = tone === "dark" ? "rgba(255,255,255,0.16)" : "var(--color-line, #e5e7eb)";

  const spinner = (
    <svg
      width={size}
      height={size}
      viewBox="0 0 44 44"
      fill="none"
      role="status"
      aria-label={label ?? "Loading"}
      className="shrink-0"
    >
      <defs>
        <linearGradient id="fiyox-arc-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#c8a24b" />
          <stop offset="100%" stopColor="#1e7a4f" />
        </linearGradient>
      </defs>
      {/* static track */}
      <circle cx="22" cy="22" r="18" stroke={track} strokeWidth="4" />
      {/* outer sweeping arc */}
      <circle
        className="fiyox-arc"
        cx="22" cy="22" r="18"
        stroke="url(#fiyox-arc-grad)" strokeWidth="4" strokeLinecap="round"
        strokeDasharray="30 200"
      />
      {/* inner counter-rotating arc for a livelier, layered feel */}
      <circle
        className="fiyox-arc fiyox-arc--inner"
        cx="22" cy="22" r="10"
        stroke="url(#fiyox-arc-grad)" strokeWidth="3" strokeLinecap="round"
        strokeDasharray="14 120" opacity="0.75"
      />
    </svg>
  );

  if (!fullScreen) return spinner;

  return (
    <div className="min-h-screen grid place-items-center bg-ink relative overflow-hidden">
      {/* brass corner accent, echoing the login register cover */}
      <div className="absolute top-0 right-0 w-28 h-28 bg-brass/80 [clip-path:polygon(100%_0,0_0,100%_100%)]" />
      <div className="flex flex-col items-center gap-6 px-6 text-center">
        <img
          src="/fiyox-logo-white.png"
          alt="Fiyox"
          className="fiyox-breathe"
          style={{ height: 60, width: "auto" }}
        />
        <svg width={52} height={52} viewBox="0 0 44 44" fill="none" role="status"
             aria-label={label ?? "Loading"}>
          <circle cx="22" cy="22" r="18" stroke="rgba(255,255,255,0.16)" strokeWidth="4" />
          <circle className="fiyox-arc" cx="22" cy="22" r="18"
                  stroke="url(#fiyox-arc-grad)" strokeWidth="4" strokeLinecap="round"
                  strokeDasharray="30 200" />
          <circle className="fiyox-arc fiyox-arc--inner" cx="22" cy="22" r="10"
                  stroke="url(#fiyox-arc-grad)" strokeWidth="3" strokeLinecap="round"
                  strokeDasharray="14 120" opacity="0.75" />
          <defs>
            <linearGradient id="fiyox-arc-grad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#c8a24b" />
              <stop offset="100%" stopColor="#1e7a4f" />
            </linearGradient>
          </defs>
        </svg>
        {label && <p className="text-white/70 text-sm tracking-wide">{label}</p>}
      </div>
    </div>
  );
}
