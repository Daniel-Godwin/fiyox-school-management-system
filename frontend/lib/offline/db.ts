/** IndexedDB for offline support: a read cache, a write outbox, and a small
 *  meta store the service worker reads to replay the outbox in the background. */
import { openDB, type DBSchema, type IDBPDatabase } from "idb";

export interface OutboxOp {
  id: string;        // client-generated, also sent as X-Op-Id for safe retries
  path: string;      // API path, e.g. /api/scores
  method: string;    // POST
  body: string;      // JSON string
  label: string;     // human text for the pending list, e.g. "Scores — JSS1 A, Maths"
  createdAt: number;
  tries: number;
}

interface FiyoxDB extends DBSchema {
  cache: { key: string; value: { data: unknown; savedAt: number } };
  outbox: { key: string; value: OutboxOp; indexes: { "by-created": number } };
  // key/value: "token" and "apiBase" so the SW can replay writes with no open tab
  meta: { key: string; value: string };
}

let dbp: Promise<IDBPDatabase<FiyoxDB>> | null = null;

export function fdb(): Promise<IDBPDatabase<FiyoxDB>> {
  if (!dbp) {
    dbp = openDB<FiyoxDB>("fiyox", 2, {
      upgrade(db) {
        if (!db.objectStoreNames.contains("cache")) db.createObjectStore("cache");
        if (!db.objectStoreNames.contains("outbox")) {
          const o = db.createObjectStore("outbox", { keyPath: "id" });
          o.createIndex("by-created", "createdAt");
        }
        if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta");
      },
    });
  }
  return dbp;
}

export async function setMeta(key: string, value: string): Promise<void> {
  try { (await fdb()).put("meta", value, key); } catch { /* best-effort */ }
}

export async function getMeta(key: string): Promise<string | undefined> {
  try { return await (await fdb()).get("meta", key); } catch { return undefined; }
}
