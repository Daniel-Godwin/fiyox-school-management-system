/** Offline-aware helpers over the plain api() client. */
import { fdb } from "./db";
import { api, ApiError } from "../api";
import { enqueue } from "./sync";

/** GET that caches on success and falls back to the last cached copy offline. */
export async function cachedGet<T>(path: string): Promise<{ data: T; stale: boolean }> {
  try {
    const data = await api<T>(path);
    try { (await fdb()).put("cache", { data, savedAt: Date.now() }, path); } catch { /* best-effort */ }
    return { data, stale: false };
  } catch (e) {
    // only fall back to cache on a network failure, not a real server error
    if (e instanceof ApiError) throw e;
    const hit = await (await fdb()).get("cache", path);
    if (hit) return { data: hit.data as T, stale: true };
    throw e;
  }
}

/** Overwrite a cached GET entry (used for optimistic local updates). */
export async function putCache(path: string, data: unknown): Promise<void> {
  try { (await fdb()).put("cache", { data, savedAt: Date.now() }, path); } catch { /* best-effort */ }
}

/**
 * POST that goes straight to the server when online, or is queued to the outbox
 * when offline (or when the network drops mid-request). Genuine server
 * rejections (4xx/5xx) are surfaced, never silently queued.
 */
export async function queuedPost<T>(path: string, body: unknown, label: string): Promise<{ queued: boolean; result: T | null }> {
  if (typeof navigator === "undefined" || navigator.onLine) {
    try {
      const result = await api<T>(path, {
        method: "POST", body: JSON.stringify(body),
        headers: { "X-Op-Id": (crypto as Crypto).randomUUID() },
      });
      return { queued: false, result };
    } catch (e) {
      if (e instanceof ApiError) throw e;   // real error — let the caller show it
      // network failure though we looked online — queue it
    }
  }
  await enqueue(path, body, label);
  return { queued: true, result: null };
}
