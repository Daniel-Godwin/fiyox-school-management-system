/** IndexedDB for offline support: a read cache and a write outbox. */
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
}

let dbp: Promise<IDBPDatabase<FiyoxDB>> | null = null;

export function fdb(): Promise<IDBPDatabase<FiyoxDB>> {
  if (!dbp) {
    dbp = openDB<FiyoxDB>("fiyox", 1, {
      upgrade(db) {
        if (!db.objectStoreNames.contains("cache")) db.createObjectStore("cache");
        if (!db.objectStoreNames.contains("outbox")) {
          const o = db.createObjectStore("outbox", { keyPath: "id" });
          o.createIndex("by-created", "createdAt");
        }
      },
    });
  }
  return dbp;
}
