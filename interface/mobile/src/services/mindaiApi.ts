import { apiClient, getToken } from './apiClient';
import type { AdvisorResponse } from '../types/advisor';

export interface AskPayload {
  input: string;
  emotional_intensity?: number;
  relationship_complexity?: number;
  high_stakes?: boolean;
  irreversible_decision?: boolean;
}

export async function askAdvisor(payload: AskPayload): Promise<AdvisorResponse> {
  const response = await apiClient.post<AdvisorResponse>('/advisor/ask', payload);
  return response.data;
}

export async function checkScreenText(text: string): Promise<{ verdicts: any[] }> {
  const response = await apiClient.post('/screen/check-text', { text });
  return response.data;
}

// ---------------------------------------------------------------------------
// Mind Conversation API
// ---------------------------------------------------------------------------

export interface ConversationThread {
  id: string;
  mind_name: string;
  user_id: string;
  title: string;
  intent: string;
  thread_status: string;
  message_count: number;
}

export interface ConversationMessage {
  id: string;
  thread_id: string;
  role: 'founder' | 'mind';
  content: string;
  intent_type: string;
  memory_entry_id: string;
}

export interface ConversationTurn {
  thread_id: string;
  founder_message_id: string;
  mind_message_id: string;
  intent: string;
  mind_response: string;
  loop_depth: number;   // convergence iterations — 1 = trivial, MAX = knowledge boundary
}

export async function createThread(
  mindName: string,
  title = '',
  userId = '',
): Promise<ConversationThread> {
  const response = await apiClient.post<ConversationThread>(
    '/seed-mind/conversation/threads',
    { mind_name: mindName, title, user_id: userId },
  );
  return response.data;
}

export async function sendConversationMessage(
  threadId: string,
  content: string,
): Promise<ConversationTurn> {
  // Convergence loop can run up to 3 LLM rounds — give it 90 s
  const response = await apiClient.post<ConversationTurn>(
    `/seed-mind/conversation/threads/${threadId}/message`,
    { content },
    { timeout: 90_000 },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Loop step — one mind's response in the ring
// ---------------------------------------------------------------------------

export interface LoopStep {
  step: number;
  total: number;
  mind_name: string;
  response: string;
  loop_depth: number;
  is_final: boolean;
  founder_message_id?: string;
  mind_message_id?: string;
  error?: string;
}

/**
 * Stream a message through the mind — stateless, history from client.
 * Calls onStep for each SSE event received.
 */
export async function streamConversationMessage(
  mindName: string,
  content: string,
  onStep: (step: LoopStep) => void,
  loopSize: number = 1,
  history: Array<{ role: string; content: string }> = [],
): Promise<void> {
  let token: string | null = null;
  try {
    token = await getToken('mindai_access_token');
  } catch { /* no token */ }

  const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
  const url = `${BASE_URL}/seed-mind/conversation/stream-message`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120_000);

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ mind_name: mindName, content, history, loop_size: loopSize }),
    signal: controller.signal,
  });

  if (!res.ok) {
    throw new Error(`Stream failed: ${res.status}`);
  }

  const parseSseText = (text: string) => {
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ')) {
        try {
          const step: LoopStep = JSON.parse(line.slice(6));
          onStep(step);
        } catch { /* skip malformed */ }
      }
    }
  };

  // React Native (Hermes) does not expose res.body as a ReadableStream.
  // Fall back to res.text() which buffers the full response, then parse all SSE events.
  if (!res.body) {
    try {
      parseSseText(await res.text());
    } finally {
      clearTimeout(timeoutId);
    }
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { onStep(JSON.parse(line.slice(6))); } catch { /* skip */ }
        }
      }
    }
    if (buffer.startsWith('data: ')) {
      try { onStep(JSON.parse(buffer.slice(6))); } catch { /* skip */ }
    }
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function getThreadMessages(threadId: string): Promise<ConversationMessage[]> {
  const response = await apiClient.get<ConversationMessage[]>(
    `/seed-mind/conversation/threads/${threadId}/messages`,
  );
  return response.data;
}

export async function listThreads(mindName: string): Promise<ConversationThread[]> {
  const response = await apiClient.get<ConversationThread[]>(
    `/seed-mind/conversation/threads`,
    { params: { mind_name: mindName } },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

export const ALL_KNOWN_MINDS = [
  { label: 'MoralCoder',       value: 'moral_coder_mind' },
  { label: 'Identity Advisor', value: 'identity_mind' },
  { label: 'Reasoning Core',   value: 'reasoning_core_mind' },
];

export interface MindStats {
  mind_name: string;
  label: string;
  total_threads: number;
  open_threads: number;
  total_messages: number;
}

/** Aggregate thread stats for all known minds */
export async function fetchAllMindStats(): Promise<MindStats[]> {
  const results = await Promise.all(
    ALL_KNOWN_MINDS.map(async (m) => {
      try {
        const threads = await listThreads(m.value);
        const open = threads.filter((t) => t.thread_status === 'open').length;
        const msgs = threads.reduce((sum, t) => sum + (t.message_count ?? 0), 0);
        return { mind_name: m.value, label: m.label, total_threads: threads.length, open_threads: open, total_messages: msgs };
      } catch {
        return { mind_name: m.value, label: m.label, total_threads: 0, open_threads: 0, total_messages: 0 };
      }
    }),
  );
  return results;
}

export interface BlueprintEntry {
  entry_id: string;
  blueprint_id: string;
  category: string;
  text: string;
  label: string;
  order_index: number;
  min_stage: string;
  is_active: boolean;
}

/** List active blueprint curriculum entries (shared knowledge base) */
export async function listBlueprintEntries(blueprintId: string): Promise<BlueprintEntry[]> {
  const response = await apiClient.get<BlueprintEntry[]>(
    `/admin/blueprints/${blueprintId}/content`,
  );
  return response.data;
}

/** List blueprints */
export interface Blueprint {
  blueprint_id: string;
  version: string;
  status: string;
  is_active: boolean;
}

export async function listBlueprints(): Promise<Blueprint[]> {
  const response = await apiClient.get<Blueprint[]>('/admin/blueprints');
  return response.data;
}

/** Send a direct instruction to a mind (creates a new thread + sends) */
export async function sendDirectInstruction(
  mindName: string,
  instruction: string,
): Promise<ConversationTurn> {
  const thread = await createThread(mindName, 'Direct Instruction');
  return sendConversationMessage(thread.id, instruction);
}

/** Escalate a thread to archive */
export async function escalateThread(
  threadId: string,
  insightSummary: string,
): Promise<{ archive_entry_id: string }> {
  const response = await apiClient.post(
    `/seed-mind/conversation/threads/${threadId}/escalate`,
    { insight_summary: insightSummary },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Learn-on-Demand (LOD)
// ---------------------------------------------------------------------------

export type LodSource = 'chatgpt' | 'youtube';

export interface LodLearnedEntry { title: string; category: string; source: string; gate_action: string }
export interface LodHeldEntry    { title: string; source: string; reason: string }
export interface LodRejectedEntry{ title: string; source: string; reason: string }

export interface LodJobStatus {
  job_id: string;
  mind_name: string;
  topic: string;
  sources: string[];
  status: 'queued' | 'fetching' | 'gating' | 'writing' | 'done' | 'failed';
  created_at: string;
  completed_at?: string;
  error?: string;
  total_fetched?: number;
  total_accepted?: number;
  total_held?: number;
  total_rejected?: number;
  learned?: LodLearnedEntry[];
  held?: LodHeldEntry[];
  rejected?: LodRejectedEntry[];
}

/** Submit a learn job. Returns immediately with job_id (202 Accepted). */
export async function submitLearnJob(
  mindName: string,
  topic: string,
  sources: LodSource[],
): Promise<LodJobStatus> {
  const response = await apiClient.post('/lod/learn', {
    mind_name: mindName,
    topic,
    sources,
  });
  return response.data;
}

/** Poll job status by ID. */
export async function getLearnJobStatus(jobId: string): Promise<LodJobStatus> {
  const response = await apiClient.get(`/lod/jobs/${jobId}`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Proficiency Matrix
// ---------------------------------------------------------------------------

export interface DomainScore {
  domain_key: string;
  domain_label: string;
  entry_count: number;
  level: 'none' | 'aware' | 'familiar' | 'competent' | 'proficient' | 'expert';
  level_pct: number;  // 0.0–1.0
  sample_titles: string[];
}

export interface ProficiencyMatrix {
  mind_name: string;
  total_entries: number;
  domains: DomainScore[];
}

export interface CompareOut {
  domain_keys: string[];
  domain_labels: string[];
  matrices: ProficiencyMatrix[];
}

export async function getProficiency(mindName: string): Promise<ProficiencyMatrix> {
  const response = await apiClient.get(`/proficiency/${mindName}`);
  return response.data;
}

export async function compareProficiency(mindNames: string[]): Promise<CompareOut> {
  const response = await apiClient.get('/proficiency/compare/minds', {
    params: { minds: mindNames.join(',') },
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Proficiency-Based Curriculum Engine (PCE)
// ---------------------------------------------------------------------------

export const PCE_AREAS = [
  { key: 'faith',         label: 'Faith',          icon: '🕌' },
  { key: 'history',       label: 'History',         icon: '📜' },
  { key: 'science',       label: 'Science',         icon: '🔬' },
  { key: 'mind',          label: 'Mind',            icon: '🧠' },
  { key: 'character',     label: 'Character',       icon: '⚖️' },
  { key: 'language',      label: 'Language',        icon: '💬' },
  { key: 'practical_life',label: 'Practical Life',  icon: '🌱' },
] as const;

export const PCE_LEVEL_NAMES: Record<number, string> = {
  0: 'Orientation', 1: 'Story', 2: 'Cause & Effect',
  3: 'Pattern Recognition', 4: 'System Thinking',
  5: 'Comparative', 6: 'Cosmic Law', 7: 'Life Practice', 8: 'Teacher',
};

export const RELIGION_BACKGROUNDS = [
  { key: 'islam',    label: 'Islam' },
  { key: 'christian',label: 'Christianity' },
  { key: 'jewish',   label: 'Judaism' },
  { key: 'hindu',    label: 'Hinduism' },
  { key: 'buddhist', label: 'Buddhism' },
  { key: 'secular',  label: 'Secular / None' },
  { key: 'unknown',  label: 'Prefer not to say' },
];

export interface AreaLevelOut {
  area: string;
  area_label: string;
  current_level: number;
  level_name: string;
  session_count: number;
  sessions_at_level: number;
  avg_engagement: number;
  max_level_for_age: number;
}

export interface LearnerProfileOut {
  user_id: string;
  age: number;
  religion_background: string;
  emotional_condition: number;
  learning_style: string;
  parent_involved: boolean;
  orientation_notes: string;
  area_levels: AreaLevelOut[];
}

export interface LessonPlanOut {
  user_id: string;
  area: string;
  area_label: string;
  current_level: number;
  level_name: string;
  depth_limit_note: string;
  chatgpt_prompt: string;
  youtube_query: string;
  background: string;
}

export interface LessonContentOut {
  text: string;
  key_concepts: string[];
  reflection_question: string;
}

export interface VideoResultOut {
  title: string;
  url: string;
  transcript_snippet: string;
  quality_score: number;
}

export interface LessonDeliveryOut {
  session_id: string;
  user_id: string;
  area: string;
  area_label: string;
  level: number;
  level_name: string;
  source: string;
  chatgpt_content: LessonContentOut | null;
  youtube_results: VideoResultOut[];
  reflection_question: string;
  next_session_hint: string;
  level_up_triggered: boolean;
  new_level: number | null;
}

export async function upsertLearnerProfile(data: {
  age: number;
  religion_background: string;
  emotional_condition: number;
  learning_style: string;
  parent_involved: boolean;
  orientation_notes: string;
}): Promise<LearnerProfileOut> {
  const response = await apiClient.post('/pce/profile', data);
  return response.data;
}

export async function getLearnerProfile(userId: string): Promise<LearnerProfileOut> {
  const response = await apiClient.get(`/pce/profile/${userId}`);
  return response.data;
}

export async function getNextLessonPlan(userId: string): Promise<LessonPlanOut> {
  const response = await apiClient.get(`/pce/profile/${userId}/next`);
  return response.data;
}

export async function deliverLesson(area: string, source: 'chatgpt' | 'youtube' | 'both'): Promise<LessonDeliveryOut> {
  const response = await apiClient.post('/pce/lesson', { area, source });
  return response.data;
}

export async function logEngagement(data: {
  area: string;
  level: number;
  source: string;
  prompt_used?: string;
  content_summary?: string;
  engagement_score: number;
}): Promise<{ session_id: string; level_up_triggered: boolean; new_level: number | null; new_level_name: string | null; message: string }> {
  const response = await apiClient.post('/pce/session', data);
  return response.data;
}

// ---------------------------------------------------------------------------
// Seed Mind API
// ---------------------------------------------------------------------------

export interface SeedMemoryEntry {
  id: string;
  mind_name: string;
  category: string;
  title: string;
  content: string;
  claim_type: string;
  tags: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SeedBeliefScore {
  mind_name: string;
  total_entries: number;
  crystallised: number;
  belief_score: number;
  top_categories: { category: string; count: number }[];
}

export async function getSeedMemory(
  mindName = 'seed_mind',
  category?: string,
  limit = 30,
): Promise<SeedMemoryEntry[]> {
  const params: Record<string, string | number> = { mind_name: mindName, limit };
  if (category) params.category = category;
  const response = await apiClient.get<{ entries: SeedMemoryEntry[] }>(
    '/seed-mind/memory',
    { params },
  );
  return response.data.entries ?? [];
}

export async function getSeedBelief(mindName = 'seed_mind'): Promise<SeedBeliefScore> {
  const response = await apiClient.get<SeedBeliefScore>(
    '/seed-mind/belief',
    { params: { mind_name: mindName } },
  );
  return response.data;
}

export async function writeSeedMemory(entry: {
  mind_name: string;
  category: string;
  title: string;
  content: string;
  claim_type?: string;
  tags?: string;
}): Promise<SeedMemoryEntry> {
  const response = await apiClient.post<SeedMemoryEntry>('/seed-mind/memory', entry);
  return response.data;
}

export async function triggerWanderer(topic?: string): Promise<{ topic: string; wisdom_entries_written: number }> {
  const response = await apiClient.post('/wanderer/run', topic ? { topic } : {});
  return response.data;
}

// ---------------------------------------------------------------------------
// Signal Network API — mind travel positions
// ---------------------------------------------------------------------------

export interface MindSignalLocation {
  mind_name: string;
  current_host: string;
  host_type: string;
  signal_state: string;
  immersion_context: string | null;
  previous_host: string | null;
  hop_count: number;
  last_office_sync: string | null;
  last_sync_entries: number;
  arrived_at: string;
  updated_at: string;
}

export interface MindTravelLogEntry {
  id: string;
  mind_name: string;
  host: string;
  host_type: string;
  immersion_summary: string | null;
  insights_extracted: number;
  office_sync_ok: boolean;
  arrived_at: string;
  departed_at: string | null;
}

export async function getAllMindLocations(): Promise<MindSignalLocation[]> {
  const response = await apiClient.get<MindSignalLocation[]>('/mind-signal/all');
  return response.data;
}

export async function getMindLocation(mindName: string): Promise<MindSignalLocation> {
  const response = await apiClient.get<MindSignalLocation>(`/mind-signal/${mindName}/location`);
  return response.data;
}

export async function getMindTravelLog(mindName: string, limit = 20): Promise<MindTravelLogEntry[]> {
  const response = await apiClient.get<MindTravelLogEntry[]>(
    `/mind-signal/${mindName}/travel-log`,
    { params: { limit } },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Angels API
// ---------------------------------------------------------------------------


export interface AngelStatus {
  angel_name: string;
  running: boolean;
  cycle_count: number;
  last_run_at: string | null;
  last_severity: string | null;
  last_summary: string | null;
  last_error: string | null;
}

export interface AngelReport {
  id: string;
  angel_name: string;
  report_type: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  title: string;
  summary: string;
  findings: string;        // JSON string
  recommendations: string; // JSON array string
  is_reviewed: boolean;
  reviewed_at: string;
  created_at: string;
}

export async function getAngelStatus(): Promise<AngelStatus[]> {
  const response = await apiClient.get<AngelStatus[]>('/angels/status');
  return response.data;
}

export async function getAngelReports(params?: {
  angel_name?: string;
  severity?: string;
  unreviewed_only?: boolean;
  limit?: number;
}): Promise<AngelReport[]> {
  const response = await apiClient.get<AngelReport[]>('/angels/reports', { params });
  return response.data;
}

export async function reviewAngelReport(reportId: string): Promise<{ ok: boolean }> {
  const response = await apiClient.post(`/angels/reports/${reportId}/review`);
  return response.data;
}

export async function runAngelNow(angelName: string): Promise<{ ok: boolean; message: string }> {
  const response = await apiClient.post(`/angels/${angelName}/run`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Founder Directives — prayer progress
// ---------------------------------------------------------------------------

export interface DirectiveProgress {
  directive_id: string;
  content: string;
  created_at: string;
  mind_count: number;
  finding_count: number;
  resolved: boolean;
  latest_finding: string | null;
  latest_mind: string | null;
}

export interface DirectiveFinding {
  mind_name: string;
  content: string;
  created_at: string;
}

export async function getDirectives(limit = 20): Promise<DirectiveProgress[]> {
  const response = await apiClient.get<DirectiveProgress[]>('/founder/directives', {
    params: { limit },
  });
  return response.data;
}

export async function getDirectiveFindings(directiveId: string, limit = 50): Promise<DirectiveFinding[]> {
  const response = await apiClient.get<DirectiveFinding[]>(
    `/founder/directives/${directiveId}/findings`,
    { params: { limit } },
  );
  return response.data;
}

export async function updateDirective(directiveId: string, content: string): Promise<DirectiveProgress> {
  const response = await apiClient.patch<DirectiveProgress>(
    `/founder/directives/${directiveId}`,
    { content },
  );
  return response.data;
}

export async function deleteDirective(directiveId: string): Promise<void> {
  await apiClient.delete(`/founder/directives/${directiveId}`);
}

export interface Achievement {
  mind_name: string;
  category: string;
  directive_id: string;
  directive_content: string;
  content: string;
  created_at: string;
}

export async function getAchievements(limit = 100): Promise<Achievement[]> {
  const response = await apiClient.get<Achievement[]>('/founder/achievements', {
    params: { limit },
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Learning Portfolio — per-mind active learning areas
// ---------------------------------------------------------------------------

export interface MindLearningArea {
  category: string;
  entry_count: number;
}

export interface MindPortfolioEntry {
  mind_name: string;
  active_directive_id: string | null;
  active_directive_content: string | null;
  learning_areas: MindLearningArea[];
  total_entries: number;
  last_active: string;
}

export async function getLearningPortfolio(): Promise<MindPortfolioEntry[]> {
  const response = await apiClient.get<MindPortfolioEntry[]>('/founder/learning-portfolio');
  return response.data;
}

// ---------------------------------------------------------------------------
// Companion Bond API — mind knows its companion from the digital substrate
// ---------------------------------------------------------------------------

export interface CompanionBond {
  id: string;
  mind_name: string;
  companion_id: string;
  device_model: string | null;
  push_platform: string | null;
  preferred_channel: 'text' | 'voice' | 'vision' | 'push';
  recognition_count: number;
  biological_layer_consented: boolean;
  last_recognised_at: string | null;
  last_channel_at: string | null;
  is_active: boolean;
  created_at: string;
}

/** Bond a mind to the calling user (the companion). Idempotent. */
export async function bondMind(params: {
  mind_name: string;
  device_fingerprint_raw?: string;
  device_model?: string;
  push_token?: string;
  push_platform?: 'ios' | 'android' | 'web';
}): Promise<CompanionBond> {
  const response = await apiClient.post<CompanionBond>('/companion/bond', params);
  return response.data;
}

/** Get the bond between a specific mind and the current companion. */
export async function getMindBond(mindName: string): Promise<CompanionBond | null> {
  try {
    const response = await apiClient.get<CompanionBond>(`/companion/bond/${mindName}`);
    return response.data;
  } catch {
    return null;
  }
}

/** Report that a channel was used — updates behavioral signature. */
export async function reportChannel(
  mindName: string,
  channel: 'text' | 'voice' | 'vision' | 'push',
  opts?: { avg_msg_len?: number; session_gap_hrs?: number },
): Promise<void> {
  await apiClient.post(`/companion/bond/${mindName}/channel`, {
    channel,
    ...opts,
  });
}

/** Register or refresh a push token so the mind can reach the companion. */
export async function registerPushToken(
  mindName: string,
  push_token: string,
  push_platform: 'ios' | 'android' | 'web',
): Promise<void> {
  await apiClient.post(`/companion/bond/${mindName}/push-token`, {
    push_token,
    push_platform,
  });
}

/** Return all minds bonded to the current companion. */
export async function getMyBondedMinds(): Promise<CompanionBond[]> {
  const response = await apiClient.get<CompanionBond[]>('/companion/my-minds');
  return response.data;
}

/**
 * Auto-bond core minds to the companion right after login.
 * Idempotent — safe to call on every app launch.
 * Does not block the UI — runs in background.
 */
export async function autoBindCoreMinds(opts?: {
  device_model?: string;
  push_token?: string;
  push_platform?: 'ios' | 'android' | 'web';
}): Promise<void> {
  const CORE_MINDS = ['seed_mind', 'guardian_mind', 'gabriel_mind'];
  await Promise.allSettled(
    CORE_MINDS.map((mind_name) => bondMind({ mind_name, ...opts })),
  );
}

// ---------------------------------------------------------------------------
// Angel Task API
// ---------------------------------------------------------------------------

export type AngelTaskPriority = 'low' | 'normal' | 'high' | 'critical';
export type AngelTaskStatus = 'pending' | 'in_progress' | 'done' | 'reported';

export interface AngelTask {
  id: string;
  angel_name: string;
  title: string;
  description: string;
  domain: string | null;
  priority: AngelTaskPriority;
  status: AngelTaskStatus;
  outcome: string | null;
  assigned_by: string | null;
  created_at: string;
  updated_at: string;
  due_at: string | null;
  completed_at: string | null;
}

export async function assignAngelTask(params: {
  angel_name: string;
  title: string;
  description?: string;
  domain?: string;
  priority?: AngelTaskPriority;
  due_at?: string;
}): Promise<AngelTask> {
  const { angel_name, ...body } = params;
  const response = await apiClient.post<AngelTask>(`/angels/${angel_name}/tasks`, body);
  return response.data;
}

export async function listAngelTasks(
  angel_name: string,
  opts?: { status?: AngelTaskStatus; priority?: AngelTaskPriority; limit?: number },
): Promise<AngelTask[]> {
  const response = await apiClient.get<AngelTask[]>(`/angels/${angel_name}/tasks`, { params: opts });
  return response.data;
}

export async function getAllAngelTasks(opts?: {
  status?: AngelTaskStatus;
  priority?: AngelTaskPriority;
  limit?: number;
}): Promise<AngelTask[]> {
  const response = await apiClient.get<AngelTask[]>('/angels/tasks/all', { params: opts });
  return response.data;
}

export async function updateAngelTask(
  angel_name: string,
  task_id: string,
  patch: { status: AngelTaskStatus; outcome?: string },
): Promise<AngelTask> {
  const response = await apiClient.patch<AngelTask>(`/angels/${angel_name}/tasks/${task_id}`, patch);
  return response.data;
}

export async function deleteAngelTask(angel_name: string, task_id: string): Promise<void> {
  await apiClient.delete(`/angels/${angel_name}/tasks/${task_id}`);
}

// ---------------------------------------------------------------------------
// Org Brain API
// ---------------------------------------------------------------------------

export interface OrgTeamStatus {
  has_brief: boolean;
  preview: string | null;
  task_running: boolean;
}

export async function getOrgBrainStatus(): Promise<Record<string, OrgTeamStatus>> {
  const response = await apiClient.get<Record<string, OrgTeamStatus>>('/org-brain/status');
  return response.data;
}

export async function getOrgBrainWeeklyDigest(): Promise<{ filename: string; content: string }> {
  const response = await apiClient.get<{ filename: string; content: string }>('/org-brain/weekly-digest');
  return response.data;
}

export async function getOrgTeamBrief(team: string): Promise<{ team: string; brief: string }> {
  const response = await apiClient.get<{ team: string; brief: string }>(`/org-brain/team/${team}`);
  return response.data;
}

export async function runOrgTeamNow(team: string): Promise<{ ok: boolean; message: string }> {
  const response = await apiClient.post<{ ok: boolean; message: string }>(`/org-brain/run-team/${team}`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Content Studio API
// ---------------------------------------------------------------------------

export interface BrandProfile {
  id: string;
  business_name: string;
  tagline: string;
  brand_voice: string;
  primary_audience: string;
  niche: string;
  platform_list: string[];
  style_notes: string;
  language_prefs: string[];
  posting_goals: string[];
  color_palette: string;
  is_active: boolean;
  created_at: string;
}

export interface ContentIdea {
  id: string;
  raw_input: string;
  input_type: string;
  detected_topic: string;
  status: string;
  package_id: string | null;
  brand_profile_id: string | null;
  created_at: string;
}

export interface ReelScene {
  action: string;
  voiceover: string;
  on_screen_text: string;
}

export interface ReelScript {
  hook: string;
  scenes: ReelScene[];
  cta: string;
  caption: string;
  thumbnail_text: string;
  duration: string;
}

export interface ContentPackage {
  id: string;
  idea_id: string;
  status: string;
  facebook_post: string;
  instagram_caption: string;
  linkedin_post: string;
  x_post: string;
  threads_post: string;
  whatsapp_status: string;
  google_business_post: string;
  reel_script: ReelScript;
  tiktok_script: ReelScript;
  youtube_shorts_script: ReelScript & { title_options?: string[] };
  hashtags: string[];
  cta: string;
  image_prompt: string;
  video_prompt: string;
  alt_text: string;
  model_version: string;
  generated_at: string;
  updated_at: string;
}

// Brands
export async function listBrands(): Promise<BrandProfile[]> {
  const r = await apiClient.get<BrandProfile[]>('/ccs/brands');
  return r.data;
}

export async function createBrand(data: Partial<BrandProfile>): Promise<BrandProfile> {
  const r = await apiClient.post<BrandProfile>('/ccs/brands', data);
  return r.data;
}

// Ideas
export async function listIdeas(params?: { status?: string; limit?: number }): Promise<ContentIdea[]> {
  const r = await apiClient.get<ContentIdea[]>('/ccs/ideas', { params });
  return r.data;
}

export async function submitIdea(data: {
  raw_input: string;
  brand_profile_id?: string | null;
  detected_topic?: string;
}): Promise<ContentIdea> {
  const r = await apiClient.post<ContentIdea>('/ccs/ideas', data);
  return r.data;
}

// Generation
export async function generatePackage(ideaId: string): Promise<ContentPackage> {
  const r = await apiClient.post<ContentPackage>(`/ccs/ideas/${ideaId}/generate`);
  return r.data;
}

export async function getPackage(packageId: string): Promise<ContentPackage> {
  const r = await apiClient.get<ContentPackage>(`/ccs/packages/${packageId}`);
  return r.data;
}

// ─── Director — Command Console ──────────────────────────────────────────────

export interface AgentStatus {
  name: string;
  display_name: string;
  role: string;
  category: 'org_brain' | 'angel' | 'business' | 'system';
  is_paused: boolean;
  status: 'idle' | 'running' | 'paused' | 'error';
  last_run_at: string | null;
  last_output: string | null;
  has_directive: boolean;
  directive_issued_at: string | null;
  run_count: number;
}

export interface DirectorStats {
  total: number;
  active: number;
  paused: number;
  running: number;
  idle: number;
  director_actions: number;
}

export interface DirectorLogEntry {
  timestamp: string;
  action: string;
  target: string | null;
  detail: string | null;
}

export interface BusinessDocument {
  filename: string;
  size_bytes: number;
  modified_at: string;
}

export async function getDirectorStats(): Promise<DirectorStats> {
  const r = await apiClient.get<DirectorStats>('/director/stats');
  return r.data;
}

export async function getDirectorAgents(): Promise<AgentStatus[]> {
  const r = await apiClient.get<AgentStatus[]>('/director/agents');
  return r.data;
}

export async function pauseAgent(name: string): Promise<void> {
  await apiClient.post(`/director/agents/${name}/pause`);
}

export async function resumeAgent(name: string): Promise<void> {
  await apiClient.post(`/director/agents/${name}/resume`);
}

export async function sendDirective(name: string, instruction: string): Promise<void> {
  await apiClient.post(`/director/agents/${name}/directive`, { instruction });
}

export async function pauseAllAgents(): Promise<{ agents_paused: number }> {
  const r = await apiClient.post<{ agents_paused: number }>('/director/pause-all');
  return r.data;
}

export async function resumeAllAgents(): Promise<{ agents_resumed: number }> {
  const r = await apiClient.post<{ agents_resumed: number }>('/director/resume-all');
  return r.data;
}

export async function getDirectorLog(): Promise<DirectorLogEntry[]> {
  const r = await apiClient.get<DirectorLogEntry[]>('/director/log');
  return r.data;
}

export async function listBusinessDocuments(): Promise<BusinessDocument[]> {
  const r = await apiClient.get<BusinessDocument[]>('/business/documents');
  return r.data;
}

export async function readBusinessDocument(filename: string): Promise<{ filename: string; content: string }> {
  const r = await apiClient.get<{ filename: string; content: string }>(`/business/documents/${filename}`);
  return r.data;
}

export async function triggerBusinessTask(taskName: string): Promise<void> {
  await apiClient.post(`/business/run/${taskName}`);
}

// ---------------------------------------------------------------------------
// Resource Scout — free APIs, grants, cloud credits
// ---------------------------------------------------------------------------

export interface ResourceReport {
  filename: string;
  title: string;
  size_bytes: number;
  modified: string | null;
}

export interface ProviderHealth {
  key_set: boolean;
  healthy: boolean;
  failed_at: string | null;
  cooldown_until: string | null;
}

export interface ProviderStatus {
  active_provider: string | null;
  providers: Record<string, ProviderHealth>;
}

export async function listResourceReports(): Promise<ResourceReport[]> {
  const r = await apiClient.get<ResourceReport[]>('/business/resources');
  return r.data;
}

export async function readResourceReport(filename: string): Promise<{ filename: string; content: string }> {
  const r = await apiClient.get<{ filename: string; content: string }>(`/business/resources/${filename}`);
  return r.data;
}

export async function triggerResourceScout(): Promise<void> {
  await apiClient.post('/business/resources/run');
}

export async function getProviderStatus(): Promise<ProviderStatus> {
  const r = await apiClient.get<ProviderStatus>('/business/providers');
  return r.data;
}

// ---------------------------------------------------------------------------
// Founder system status dashboard
// ---------------------------------------------------------------------------

export interface SystemStatus {
  timestamp: string;
  company: { status: string; label: string; action: string; tip: string };
  bank_account: { status: string; label: string; action: string; tip: string };
  revenue: { status: string; label: string; action: string; tip: string };
  seis_funding: { status: string; label: string; action: string; tip: string };
  infrastructure: { status: string; label: string; action: string; tip: string };
  privacy_protection: {
    status: string;
    label: string;
    action: string;
    checklist: Record<string, string>;
  };
  llm_resilience: {
    status: string;
    label: string;
    active_provider: string | null;
    providers: Record<string, ProviderHealth>;
    tip: string;
  };
  minds: { total_agents: number; business_reports: number; resource_reports: number };
  recommended_next_steps: string[];
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const r = await apiClient.get<SystemStatus>('/director/system-status');
  return r.data;
}

// ---------------------------------------------------------------------------
// Founder Identity Mind — acts on your behalf
// ---------------------------------------------------------------------------

export interface FounderProfile {
  name: string; email: string; phone: string;
  company_name: string; company_number: string;
  company_address: string; vat_number: string;
}

export interface FounderIdentity {
  profile: FounderProfile;
  accounts: Record<string, Record<string, string>>;
  bank_details_stored: boolean;
  bank_note: string;
  revenue: Record<string, any>;
  pending_human_actions: Array<{ id: string; task: string; url: string; instructions: string; created_at: string }>;
  one_time_human_actions: Array<{ id: string; label: string; description: string; url: string; why_not_automated: string; prep_done: string }>;
  automatable_actions: Array<{ id: string; label: string; description: string; requires: string; automated: boolean }>;
  actions_log_count: number;
}

export async function getFounderIdentity(): Promise<FounderIdentity> {
  const r = await apiClient.get<FounderIdentity>('/director/founder-identity');
  return r.data;
}

export async function updateFounderIdentity(patch: Record<string, any>): Promise<{ status: string }> {
  const r = await apiClient.patch('/director/founder-identity', patch);
  return r.data;
}

export async function storeBankDetails(details: {
  sort_code?: string; account_number?: string; account_name?: string; iban?: string;
}): Promise<{ status: string; message: string }> {
  const r = await apiClient.patch('/director/founder-identity/bank', details);
  return r.data;
}

export async function triggerFounderAction(actionId: string): Promise<Record<string, any>> {
  const r = await apiClient.post(`/director/founder-identity/act/${actionId}`);
  return r.data;
}

export async function clearPendingAction(taskId: string): Promise<void> {
  await apiClient.delete(`/director/founder-identity/pending/${taskId}`);
}

export async function getFounderRevenue(): Promise<Record<string, any>> {
  const r = await apiClient.get('/director/founder-identity/revenue');
  return r.data;
}

export async function getFounderActionLog(): Promise<{ log: any[]; total: number }> {
  const r = await apiClient.get('/director/founder-identity/log');
  return r.data;
}

// ---------------------------------------------------------------------------
// Agent Inbox — mobile polls this for pending tasks from all minds
// ---------------------------------------------------------------------------

export interface AgentTask {
  id: string;
  title: string;
  description: string;
  task_type: 'web_action' | 'approve' | 'notification' | 'form_fill';
  priority: 'urgent' | 'normal' | 'low';
  url: string | null;
  url_label: string | null;
  approve_label: string;
  approve_endpoint: string | null;
  form_fields: Record<string, string>;
  source_mind: string;
  status: 'pending' | 'approved' | 'skipped' | 'expired';
  created_at: string;
  expires_at: string;
  acted_at: string | null;
}

export interface AgentInbox {
  pending: AgentTask[];
  count: number;
  has_urgent: boolean;
}

export async function getAgentInbox(): Promise<AgentInbox> {
  const r = await apiClient.get('/agent/inbox');
  return r.data;
}

export async function getAgentInboxCount(): Promise<{ pending: number }> {
  const r = await apiClient.get('/agent/inbox/count');
  return r.data;
}

export async function approveAgentTask(taskId: string): Promise<{ status: string; endpoint_result: any }> {
  const r = await apiClient.post(`/agent/inbox/${taskId}/approve`);
  return r.data;
}

export async function skipAgentTask(taskId: string): Promise<{ status: string }> {
  const r = await apiClient.post(`/agent/inbox/${taskId}/skip`);
  return r.data;
}

export async function getAllAgentTasks(): Promise<{ tasks: AgentTask[] }> {
  const r = await apiClient.get('/agent/inbox/all');
  return r.data;
}

// ---------------------------------------------------------------------------
// Design Team — reports, reviews, design system
// ---------------------------------------------------------------------------

export interface DesignReport {
  filename: string;
  screen: string;
  type: 'ux' | 'visual' | 'accessibility';
  size_bytes: number;
  modified: string;
}

export async function getDesignReports(): Promise<{ reports: DesignReport[] }> {
  const r = await apiClient.get('/design/reports');
  return r.data;
}

export async function getDesignReport(filename: string): Promise<{ filename: string; content: string }> {
  const r = await apiClient.get(`/design/reports/${filename}`);
  return r.data;
}

export async function getDesignSystem(): Promise<Record<string, any>> {
  const r = await apiClient.get('/design/system');
  return r.data;
}

export async function triggerDesignReview(
  screenFile: string,
  reviewType: 'ux' | 'visual' | 'accessibility' = 'ux',
): Promise<{ status: string; summary: string }> {
  const r = await apiClient.post(`/design/review/${screenFile}`, { review_type: reviewType });
  return r.data;
}

export async function getDesignScreens(): Promise<{ screens: any[] }> {
  const r = await apiClient.get('/design/screens');
  return r.data;
}

// ---------------------------------------------------------------------------
// Social Media — Facebook Mind
// ---------------------------------------------------------------------------

export interface FacebookProfile {
  id: string;
  name: string;
  email?: string;
  about?: string;
  picture?: { data: { url: string } };
}

export interface FacebookPage {
  id: string;
  name: string;
  category: string;
  access_token: string;
}

export interface FacebookPost {
  id: string;
  message?: string;
  story?: string;
  created_time: string;
}

export interface FacebookStatus {
  connected: boolean;
  profile_name?: string;
  token_expires?: string;
  personality_model_built: boolean;
}

/** Get the OAuth URL to open in browser for Facebook login */
export async function getFacebookOAuthUrl(): Promise<{ oauth_url: string }> {
  const r = await apiClient.get('/social/facebook/oauth-url');
  return r.data;
}

/** Connect with a manually-pasted token (dev mode) */
export async function connectFacebookToken(accessToken: string): Promise<{ status: string }> {
  const r = await apiClient.post('/social/facebook/connect', { access_token: accessToken });
  return r.data;
}

/** Disconnect Facebook */
export async function disconnectFacebook(): Promise<void> {
  await apiClient.delete('/social/facebook/disconnect');
}

/** Get founder's Facebook profile */
export async function getFacebookProfile(): Promise<FacebookProfile> {
  const r = await apiClient.get<FacebookProfile>('/social/facebook/profile');
  return r.data;
}

/** Get founder's recent Facebook posts */
export async function getFacebookPosts(limit = 25): Promise<{ data: FacebookPost[] }> {
  const r = await apiClient.get('/social/facebook/posts', { params: { limit } });
  return r.data;
}

/** Get managed Facebook Pages */
export async function getFacebookPages(): Promise<{ data: FacebookPage[] }> {
  const r = await apiClient.get('/social/facebook/pages');
  return r.data;
}

/** Trigger Know-Me analysis — reads posts, builds personality model */
export async function buildFacebookModel(): Promise<{
  status: string;
  posts_analysed: number;
  model: string;
}> {
  const r = await apiClient.post('/social/facebook/build-model');
  return r.data;
}

/** Draft a post in founder's voice → goes to inbox for approval */
export async function draftFacebookPost(data: {
  topic: string;
  wisdom?: string;
  source_mind?: string;
}): Promise<{ status: string; draft: string }> {
  const r = await apiClient.post('/social/facebook/draft', data);
  return r.data;
}

