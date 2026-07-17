"use client";

import { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  busy?: boolean;
  busyLabel?: string;
};

const BASE =
  "inline-flex items-center justify-center rounded-md font-medium " +
  "focus-visible:outline-2 disabled:opacity-50 disabled:pointer-events-none select-none";

const VARIANT: Record<Variant, string> = {
  primary: "bg-ink text-white hover:bg-ink-soft",
  secondary: "border border-ink text-ink hover:bg-ink hover:text-white",
  ghost: "text-ink hover:bg-paper",
  danger: "border border-sanction text-sanction hover:bg-sanction hover:text-white",
};

const SIZE: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
};

export function Button({
  variant = "primary", size = "md", busy = false, busyLabel,
  children, className = "", disabled, ...rest
}: Props) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy}
      className={`${BASE} ${VARIANT[variant]} ${SIZE[size]} ${className}`}
    >
      {busy && <span className="spinner" aria-hidden="true" />}
      {busy ? (busyLabel ?? "Working…") : children}
    </button>
  );
}
