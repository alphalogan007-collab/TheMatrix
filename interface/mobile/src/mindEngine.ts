/**
 * mindEngine.ts — MindAI Creator Console backend client.
 *
 * Single source of truth for all API calls from the UI.
 * Every function maps to a real, current backend endpoint.
 *
 * BASE_URL: EC2 backend (nginx → FastAPI).
 * For local dev, change to http://<your-machine-ip>:8000
 */

export const BASE_URL = 'https://socialfork.ca';

const TIMEOUT_MS = 10_000;

function fetchWithTimeout(url: string, options?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  return fetch(url, { ...options, signal: controller.signal })
    .finally(() => clearTimeout(timer));
}

async function get<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: object): Promise<T> {
  const res = await fetchWithTimeout(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(`${BASE_URL}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
  return res.json();
}

// ─── types ────────────────────────────────────────────────────────────────────

export interface LiveEvent {
  type:      string;
  ring?:     string;
  from?:     string;
  pattern?:  string;
  domain?:   string;
  layer?:    string | number;
  direction?: string;
  ts?:       string;
}

export interface MindRing {
  active:        boolean;
  recent_events: number;
  domains:       Record<string, number>;
}

export interface MindStage {
  stage:       number;
  label:       string;
  description: string;
}

export interface MindLearningEntry {
  title:  string;
  domain: string;
  source: string;
  ts:     string;
}

export interface MindHealth {
  corpus: {
    total:               number;
    foundation:          number;
    structure:           number;
    synthesis:           number;
    guidance:            number;
    synthesis_by_domain: Record<string, number>;
  };
  stage:    MindStage;
  rings:    { adam: MindRing; eve: MindRing; ca: MindRing };
  learning: MindLearningEntry[];
  uptime_secs: number;
}

export interface GuidanceFile {
  file_id: string;
  title:   string;
  source:  string;
  chars:   number;
  ts:      string;
}

export interface GuidanceEvent {
  msg_id: string;
  file_id?: string;
  title?:   string;
  chars?:   string;
  ts?:      string;
}

export interface SeedResult {
  session_id: string;
  queued:     boolean;
}

export interface AdminStatus {
  ok:             boolean;
  corpus_total:   number;
  containers:     number;
  barzakh_keys:   number;
  uptime_secs:    number;
  rings:          { adam: boolean; eve: boolean; ca: boolean };
  foundation_ok:  boolean;
  stream_len:     number;
}

// ─── Guide tab ────────────────────────────────────────────────────────────────

/** All corpus entries as a flat list (metadata only, no content). */
export const getGuidanceList = (limit = 80): Promise<GuidanceFile[]> =>
  get<GuidanceFile[]>(`/guidance/list?limit=${limit}`);

/** Recent file ingestion events from the guidance scanner. */
export const getGuidanceEvents = (count = 15): Promise<GuidanceEvent[]> =>
  get<GuidanceEvent[]>(`/guidance/events/recent?count=${count}`);

/** Seed text into the mind as a directive from the Founder. */
export const seedDirective = (content: string, source = 'founder'): Promise<SeedResult> =>
  post<SeedResult>('/admin/seed', { content, source });

// ─── Mind tab ─────────────────────────────────────────────────────────────────

/** Full mind health: corpus stats, awakening stage, ring activity, recent synthesis. */
export const getMindHealth = (): Promise<MindHealth> =>
  get<MindHealth>('/admin/mind/health');

/** Clear synthesis entries + barzakh keys. Foundation and guidance preserved. */
export const clearCorpusSynthesis = (): Promise<{
  synthesis_deleted: number;
  barzakh_deleted:   number;
  corpus_remaining:  number;
}> => del('/admin/corpus/synthesis');

// ─── World tab ────────────────────────────────────────────────────────────────

/** System status: containers, corpus, ring health, barzakh cache. */
export const getAdminStatus = (): Promise<MindHealth> =>
  get<MindHealth>('/admin/mind/health');

/** Clear only stale barzakh session checkpoint keys (no corpus change). */
export const clearBarzakh = (): Promise<{ barzakh_deleted: number }> =>
  del('/admin/barzakh');

// ─── SSE stream (live oscillation events) ─────────────────────────────────────

export function streamEvents(onEvent: (e: LiveEvent) => void): { close: () => void } {
  const controller = new AbortController();

  (async () => {
    while (true) {
      try {
        const res = await fetch(`${BASE_URL}/admin/topology/stream`, {
          signal:  controller.signal,
          headers: { Accept: 'text/event-stream' },
        });
        const reader = res.body?.getReader();
        if (!reader) break;
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try { onEvent(JSON.parse(line.slice(6))); } catch (_) {}
            }
          }
        }
      } catch (e: any) {
        if (e?.name === 'AbortError') return;
        await new Promise(r => setTimeout(r, 3000));
      }
    }
  })();

  return { close: () => controller.abort() };
}