"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

type ToastKind = "ok" | "err" | "info";
type Toast = { id: number; kind: ToastKind; text: string };

type ToastCtx = {
  toast: (kind: ToastKind, text: string) => void;
  ok: (text: string) => void;
  err: (text: string) => void;
  info: (text: string) => void;
};

const Ctx = createContext<ToastCtx | null>(null);

export function useToast(): ToastCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

const STYLE: Record<ToastKind, string> = {
  ok: "border-ledger/40 bg-ledger/10 text-ledger",
  err: "border-sanction/40 bg-sanction/10 text-sanction",
  info: "border-line bg-card text-ink",
};

const ICON: Record<ToastKind, string> = { ok: "✓", err: "!", info: "i" };

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    // errors linger a little longer — people need time to read what went wrong
    const ttl = kind === "err" ? 6000 : 4000;
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ttl);
  }, []);

  const value: ToastCtx = {
    toast,
    ok: (t) => toast("ok", t),
    err: (t) => toast("err", t),
    info: (t) => toast("info", t),
  };

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
        {toasts.map((t) => (
          <div key={t.id} role="status"
               className={`toast-in flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur-sm ${STYLE[t.kind]}`}>
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-current text-xs font-bold">
              {ICON[t.kind]}
            </span>
            <span className="pt-0.5">{t.text}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
