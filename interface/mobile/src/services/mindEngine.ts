/**
 * mindEngine.ts — Client for the MindAI Y-Theory engine.
 *
 * Endpoints:
 *   POST /ingest          — feed text into engine, seed builds itself
 *   POST /think           — user input → engine response
 *   GET  /events          — SSE stream of live pattern events
 *   GET  /seed/graph      — graph nodes + edges
 *   GET  /seed/wisdom     — wisdom entries list
 */

const BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

// ─── types ────────────────────────────────────────────────────────────────────

export interface GraphNode {
  id:     string;
  label:  string;
  type:   'angel' | 'layer' | 'category';
  weight: number;
}

export interface GraphEdge {
  source:   string;
  target:   string;
  strength: number;
}

export interface GraphData {
  nodes:   GraphNode[];
  edges:   GraphEdge[];
  wisdom?: WisdomEntry[];
}

export interface WisdomEntry {
  id:        string;
  mind_name: string;
  category:  string;
  title:     string;
  content:   string;
  claim_type:string;
  tags:      string;
}

export interface ThinkResult {
  angel:          string;
  entries_written:number;
  y_layer:        string;
  mind_name:      string;
  summary:        string;
}

export interface IngestResult {
  source:        string;
  subject:       string;
  angel:         string;
  chunks:        number;
  total_entries: number;
}

// ─── helpers ──────────────────────────────────────────────────────────────────

async function post<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ─── public API ───────────────────────────────────────────────────────────────

/** Feed text into the Y-Theory engine — wisdom writes to seed automatically. */
export async function ingestText(params: {
  source:      string;
  subject:     string;
  text:        string;
  angel_name?: string;
}): Promise<IngestResult> {
  return post<IngestResult>('/ingest', params);
}

/** User types/speaks → engine processes → response from seeded wisdom. */
export async function thinkAndIngest(params: {
  text:    string;
  subject?: string;
}): Promise<ThinkResult> {
  return post<ThinkResult>('/think', params);
}

/** Get the pattern graph (nodes + edges) built from all seeded wisdom. */
export async function getGraphData(): Promise<GraphData> {
  const [graph, wisdom] = await Promise.all([
    get<{ nodes: GraphNode[]; edges: GraphEdge[] }>('/seed/graph'),
    get<WisdomEntry[]>('/seed/wisdom?limit=30'),
  ]);
  return { ...graph, wisdom };
}

// ─── learn / training API ─────────────────────────────────────────────────────

export interface LearnPhase {
  key:                 string;
  arabic:              string;
  english:             string;
  ratio:               number;
  y_layer:             string;
  angel:               string;
  quran_refs:          string[];
  topics:              string[];
  first_active_at_step:number | null;
}

export interface LearnPlan {
  fibonacci_sequence: number[];
  phases:             LearnPhase[];
}

export interface LearnStatus {
  running:     boolean;
  steps_done:  number;
  last_result: {
    steps_run:    number;
    total_entries:number;
    steps:        Array<{
      step:          number;
      fib_n:         number;
      active_phases: string[];
      total_entries: number;
    }>;
  } | null;
}

export async function startLearning(steps = 6): Promise<{ status: string; fibonacci_sequence: number[] }> {
  return post('/learn/start', { steps });
}

export async function getLearningStatus(): Promise<LearnStatus> {
  return get<LearnStatus>('/learn/status');
}

export async function getLearningPlan(): Promise<LearnPlan> {
  return get<LearnPlan>('/learn/plan');
}

// ─── SSE event stream ─────────────────────────────────────────────────────────

export interface LiveEvent {
  type:     string;
  from:     string;
  to:       string;
  pattern:  string;
  strength: number;
  ts:       string;
}

export interface EventStream {
  close: () => void;
}

/**
 * Subscribe to live engine events via SSE.
 * React Native doesn't have native EventSource — we use fetch with streaming.
 * Returns a handle with .close() to cancel.
 */
export function streamEvents(onEvent: (e: LiveEvent) => void): EventStream {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE}/events`, {
        signal: controller.signal,
        headers: { Accept: 'text/event-stream' },
      });
      const reader = res.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6)) as LiveEvent;
              onEvent(event);
            } catch (_) {}
          }
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        // Reconnect after 3s on non-abort error
        setTimeout(() => streamEvents(onEvent), 3000);
      }
    }
  })();

  return { close: () => controller.abort() };
}
