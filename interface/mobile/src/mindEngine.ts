/**
 * mindEngine.ts — MindAI Y-Theory backend client.
 * Change BASE_URL to your machine's local IP when testing on a phone.
 */

// EC2 backend through nginx — has direct access to topology Redis (spirit:events)
export const BASE_URL = 'https://socialfork.ca';

const TIMEOUT_MS = 8000;

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

// ─── types ────────────────────────────────────────────────────────────────────

export interface WisdomEntry {
  id: string;
  mind_name: string;
  category: string;
  title: string;
  content: string;
  claim_type: string;
  tags: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'angel' | 'layer' | 'category';
  weight: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  strength: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  wisdom?: WisdomEntry[];
}

export interface LiveEvent {
  type: string;
  from?: string;
  to?: string;
  pattern?: string;
  strength?: number;
  ts?: string;
}

export interface ThinkResult {
  angel: string;
  entries_written: number;
  y_layer: string;
  mind_name: string;
  summary: string;
}

export interface LearnPhase {
  key: string;
  arabic: string;
  english: string;
  ratio: number;
  y_layer: string;
  angel: string;
  quran_refs: string[];
  topics: string[];
  first_active_at_step: number | null;
}

export interface LearnPlan {
  fibonacci_sequence: number[];
  phases: LearnPhase[];
}

export interface LearnStatus {
  running: boolean;
  steps_done: number;
  last_result: {
    steps_run: number;
    total_entries: number;
    steps: Array<{
      step: number;
      fib_n: number;
      active_phases: string[];
      total_entries: number;
    }>;
  } | null;
}

// ─── API calls ────────────────────────────────────────────────────────────────

export const getGraphData = (): Promise<GraphData> =>
  get('/seed/graph');

export const getWisdom = (): Promise<WisdomEntry[]> =>
  get('/seed/wisdom?limit=30');

export const thinkAndIngest = (text: string, subject = 'general'): Promise<ThinkResult> =>
  post('/think', { text, subject });

export const getLearningStatus = (): Promise<LearnStatus> =>
  get('/learn/status');

export const getLearningPlan = (): Promise<LearnPlan> =>
  get('/learn/plan');

export const startLearning = (steps = 6): Promise<{ status: string; fibonacci_sequence: number[] }> =>
  post('/learn/start', { steps });

// ─── Quran ingestion ──────────────────────────────────────────────────────────

export interface QuranStatus {
  running:                    boolean;
  done:                       number;
  total:                      number;
  progress_pct:               number;
  entries_written:            number;
  current_sura:               number | null;
  errors:                     number;
  last_error:                 string | null;
  pass_number:                number;       // how many full reads completed
  next_read_after_sessions:   number | null; // Fibonacci gap until next re-read
}

export const getQuranStatus = (): Promise<QuranStatus> =>
  get<QuranStatus>('/quran/status');

export const startQuran = (start_from = 0): Promise<{ status: string }> =>
  post('/quran/start', { start_from });

// ─── Monitor / health ──────────────────────────────────────────────────────────

export interface MonitorStats {
  ok: boolean;
  timestamp: string;
  uptime_seconds: number;
  database: {
    connected: boolean;
    total_entries: number;
    recent_60s: number;
    last_entry_at: string | null;
  };
  angels: Record<string, number>;
  categories: Record<string, number>;
}

export const getMonitorStats = (): Promise<MonitorStats> =>
  get<MonitorStats>('/monitor/stats');

// ─── SSE stream ───────────────────────────────────────────────────────────────

export function streamEvents(onEvent: (e: LiveEvent) => void): { close: () => void } {
  const controller = new AbortController();

  (async () => {
    while (true) {
      try {
        const res = await fetch(`${BASE_URL}/admin/topology/stream`, {
          signal: controller.signal,
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

// ─── Mind health (Mind View) ───────────────────────────────────────────────────

export interface MindRing {
  active: boolean;
  recent_events: number;
  domains: Record<string, number>;
}

export interface MindStage {
  stage: number;
  label: string;
  description: string;
}

export interface MindLearningEntry {
  title: string;
  domain: string;
  source: string;
  ts: string;
}

export interface MindHealth {
  corpus: {
    total: number;
    foundation: number;
    structure: number;
    synthesis: number;
    guidance: number;
    synthesis_by_domain: Record<string, number>;
  };
  stage: MindStage;
  rings: {
    adam: MindRing;
    eve:  MindRing;
    ca:   MindRing;
  };
  learning: MindLearningEntry[];
  uptime_secs: number;
}

export const getMindHealth = (): Promise<MindHealth> =>
  get<MindHealth>('/admin/mind/health');

export const clearCorpusSynthesis = (): Promise<{
  synthesis_deleted: number;
  barzakh_deleted: number;
  corpus_remaining: number;
  message: string;
}> => {
  return fetchWithTimeout(`${BASE_URL}/admin/corpus/synthesis`, { method: 'DELETE' })
    .then(res => {
      if (!res.ok) throw new Error(`DELETE /admin/corpus/synthesis → ${res.status}`);
      return res.json();
    });
};
