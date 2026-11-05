/** The outbox sync engine: queue writes offline, replay them when back online.
 *
 * Writes are idempotent on the server (score/attendance upserts keyed by their
 * natural keys), so replaying a queued op twice is harmless — which makes retry
 * safe. Each op also carries an X-Op-Id for future server-side de-duplication.
 *
 * Replay happens three ways, so nothing is lost: immediately when online, on the
 * browser "online" event, and — even with no tab open — via the service worker's
 * Background Sync, which reads the token/apiBase mirrored into the meta store.
 */
import { fdb, getMeta, setMeta, type OutboxOp } from "./db";
import { api, ApiError, getToken } from "../api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SYNC_TAG = "fiyox-outbox";

type Listener = () => void;
const listeners = new Set<Listener>();
export function onSyncChange(l: Listener): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
function emit() { listeners.forEach((l) => l()); }

export function isOnline(): boolean {
  return typeof navigator === "undefined" ? true : navigator.onLine;
}

export async function pendingCount(): Promise<number> {
  return (await fdb()).count("outbox");
}

export async function pendingOps(): Promise<OutboxOp[]> {
  return (await fdb()).getAllFromIndex("outbox", "by-created");
}

/** Remove a single queued op (used by the Pending-changes screen). */
export async function discard(id: string): Promise<void> {
  await (await fdb()).delete("outbox", id);
  emit();
}

/** Mirror the current credentials so the service worker can replay with no tab. */
async function mirrorCreds(): Promise<void> {
  const token = getToken();
  if (token) await setMeta("token", token);
  await setMeta("apiBase", API_BASE);
}

/** Ask the browser to drain the outbox in the background when it next can. */
async function requestBackgroundSync(): Promise<void> {
  try {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    const reg = await navigator.serviceWorker.ready;
    // SyncManager is not in every browser; guard it.
    const sm = (reg as unknown as { sync?: { register(tag: string): Promise<void> } }).sync;
    if (sm) await sm.register(SYNC_TAG);
  } catch { /* background sync simply unavailable — the online-event flush covers it */ }
}

export async function enqueue(path: string, body: unknown, label: string): Promise<void> {
  const op: OutboxOp = {
    id: (crypto as Crypto).randomUUID(),
    path, method: "POST", body: JSON.stringify(body), label,
    createdAt: Date.now(), tries: 0,
  };
  await (await fdb()).put("outbox", op);
  await mirrorCreds();
  emit();
  void flush();
  void requestBackgroundSync();
}

let flushing = false;

/** Drain the outbox. Returns how many sent, how many remain, and why it stopped. */
export async function flush(): Promise<{ sent: number; pending: number; blocked: "offline" | "auth" | null }> {
  if (flushing || !isOnline()) return { sent: 0, pending: await pendingCount(), blocked: isOnline() ? null : "offline" };
  flushing = true;
  let sent = 0;
  let blocked: "offline" | "auth" | null = null;
  try {
    const db = await fdb();
    const ops = await db.getAllFromIndex("outbox", "by-created");
    for (const op of ops) {
      try {
        await api(op.path, { method: op.method, body: op.body, headers: { "X-Op-Id": op.id } });
        await db.delete("outbox", op.id);
        sent++;
        emit();
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.status === 401) { blocked = "auth"; break; }      // session expired — stop, keep the op
          // a genuine server rejection: count a try, drop after too many so one bad op can't jam the queue
          op.tries += 1;
          if (op.tries >= 5) await db.delete("outbox", op.id);
          else await db.put("outbox", op);
          emit();
        } else {
          blocked = "offline"; break;   // network dropped mid-flush — retry later
        }
      }
    }
  } finally {
    flushing = false;
    emit();
  }
  return { sent, pending: await pendingCount(), blocked };
}

if (typeof window !== "undefined") {
  window.addEventListener("online", () => { void flush(); emit(); });
  window.addEventListener("offline", () => { emit(); });
  // the service worker tells us when it drained the queue in the background
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", (e: MessageEvent) => {
      if (e.data && e.data.type === "fiyox-synced") emit();
    });
  }
}
