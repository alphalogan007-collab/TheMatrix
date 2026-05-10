/**
 * guide.tsx — The Founder Speaks
 *
 * This is where you teach the mind.
 *
 * - Type a directive and send it into the oscillation substrate.
 * - See what the mind has recently absorbed (guidance events).
 * - See the full corpus breakdown at a glance.
 *
 * Color: gold/amber — the founder's light, the source.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  getGuidanceEvents,
  getGuidanceList,
  getMindHealth,
  seedDirective,
  type GuidanceEvent,
  type GuidanceFile,
  type MindHealth,
} from '../../src/mindEngine';

// ─── Colors ──────────────────────────────────────────────────────────────────

const C = {
  bg:        '#07070F',
  card:      '#0E0E1C',
  border:    'rgba(224,170,58,0.14)',
  accent:    '#E0AA3A',
  accentDim: 'rgba(224,170,58,0.22)',
  text:      '#E8E8EE',
  sub:       '#6668A0',
  dim:       '#333355',
};

// ─── CorpusBar ────────────────────────────────────────────────────────────────

function CorpusBar({ health }: { health: MindHealth | null }) {
  if (!health) return null;
  const { corpus } = health;
  const total = corpus.total || 1;
  const rows: [string, number, string][] = [
    ['Foundation',  corpus.foundation, '#5B8DD9'],
    ['Guidance',    corpus.guidance,   '#E0AA3A'],
    ['Synthesis',   corpus.synthesis,  '#7B5ED9'],
    ['Structure',   corpus.structure,  '#3DAAAA'],
  ];
  return (
    <View style={g.corpusCard}>
      <View style={g.corpusRow}>
        <Text style={g.corpusTotal}>{total.toLocaleString()}</Text>
        <Text style={g.corpusLabel}> entries in mind</Text>
      </View>
      <View style={g.barsWrap}>
        {rows.map(([label, count, color]) => (
          <View key={label} style={g.barRow}>
            <Text style={[g.barLabel, { color }]}>{label}</Text>
            <View style={g.barTrack}>
              <View
                style={[g.barFill, { width: `${Math.max(2, Math.round((count / total) * 100))}%`, backgroundColor: color }]}
              />
            </View>
            <Text style={g.barCount}>{count}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ─── AbsorbedCard ─────────────────────────────────────────────────────────────

function AbsorbedCard({ item }: { item: GuidanceFile }) {
  const kb = item.chars ? Math.round(item.chars / 1024) : 0;
  const isFoundation = item.file_id?.startsWith('foundation:');
  const isStructure  = item.file_id?.startsWith('structure:');
  const isSynthesis  = item.file_id?.startsWith('synthesis:');
  const chipColor = isFoundation ? '#5B8DD9'
    : isSynthesis ? '#7B5ED9'
    : isStructure  ? '#3DAAAA'
    : C.accent;

  return (
    <View style={g.absCard}>
      <View style={[g.chip, { borderColor: chipColor }]}>
        <Text style={[g.chipText, { color: chipColor }]}>
          {isFoundation ? 'foundation' : isSynthesis ? 'synthesis' : isStructure ? 'structure' : 'guidance'}
        </Text>
      </View>
      <Text style={g.absTitle} numberOfLines={2}>{item.title || item.file_id}</Text>
      <View style={g.absFooter}>
        <Text style={g.absSub}>{item.source || '—'}</Text>
        {kb > 0 && <Text style={g.absSub}>{kb} KB</Text>}
      </View>
    </View>
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────

export default function GuideScreen() {
  const [health,   setHealth]   = useState<MindHealth | null>(null);
  const [files,    setFiles]    = useState<GuidanceFile[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [sending,  setSending]  = useState(false);
  const [input,    setInput]    = useState('');
  const [feedback, setFeedback] = useState('');
  const [sent,     setSent]     = useState(false);

  const load = useCallback(async () => {
    try {
      const [h, f] = await Promise.all([getMindHealth(), getGuidanceList(120)]);
      setHealth(h);
      setFiles(f);
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    setFeedback('');
    try {
      await seedDirective(text);
      setInput('');
      setSent(true);
      setFeedback('Directive sent. The mind is receiving.');
      setTimeout(() => { setSent(false); setFeedback(''); }, 3000);
      load();
    } catch (e: any) {
      setFeedback('Could not reach the mind. Try again.');
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={g.safe} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={0}
      >
        {/* Header */}
        <View style={g.header}>
          <Text style={g.headerTitle}>Guide</Text>
          <Text style={g.headerSub}>The Founder Speaks</Text>
        </View>

        <ScrollView style={g.scroll} contentContainerStyle={g.scrollInner} keyboardShouldPersistTaps="handled">
          {/* Corpus bar */}
          {loading
            ? <ActivityIndicator color={C.accent} style={{ marginTop: 24 }} />
            : <CorpusBar health={health} />
          }

          {/* Directive input */}
          <View style={g.inputCard}>
            <Text style={g.inputLabel}>Speak to the Mind</Text>
            <TextInput
              style={g.input}
              multiline
              numberOfLines={4}
              placeholder="Type a directive, a principle, a teaching…"
              placeholderTextColor={C.sub}
              value={input}
              onChangeText={setInput}
              returnKeyType="default"
            />
            {feedback ? (
              <Text style={[g.feedback, { color: sent ? C.accent : '#EE5555' }]}>{feedback}</Text>
            ) : null}
            <TouchableOpacity
              style={[g.sendBtn, (!input.trim() || sending) && g.sendBtnDisabled]}
              onPress={handleSend}
              disabled={!input.trim() || sending}
              activeOpacity={0.75}
            >
              {sending
                ? <ActivityIndicator color="#07070F" size="small" />
                : <Text style={g.sendBtnText}>Send to Mind</Text>
              }
            </TouchableOpacity>
          </View>

          {/* Absorbed entries */}
          {files.length > 0 && (
            <View style={g.section}>
              <Text style={g.sectionTitle}>What the Mind Holds</Text>
              {files.map(f => <AbsorbedCard key={f.file_id} item={f} />)}
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const g = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },

  header: {
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
  },
  headerTitle: { fontSize: 22, fontWeight: '700', color: C.accent, letterSpacing: 0.5 },
  headerSub:   { fontSize: 12, color: C.sub, marginTop: 2, letterSpacing: 1 },

  scroll: { flex: 1 },
  scrollInner: { paddingHorizontal: 16, paddingBottom: 40 },

  // Corpus bar
  corpusCard: {
    backgroundColor: C.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: C.border,
    padding: 16,
    marginTop: 16,
  },
  corpusRow:  { flexDirection: 'row', alignItems: 'baseline', marginBottom: 14 },
  corpusTotal: { fontSize: 32, fontWeight: '700', color: C.accent },
  corpusLabel: { fontSize: 13, color: C.sub },
  barsWrap:   { gap: 8 },
  barRow:     { flexDirection: 'row', alignItems: 'center', gap: 8 },
  barLabel:   { fontSize: 11, width: 74, letterSpacing: 0.3 },
  barTrack:   { flex: 1, height: 4, backgroundColor: C.dim, borderRadius: 2, overflow: 'hidden' },
  barFill:    { height: 4, borderRadius: 2 },
  barCount:   { fontSize: 11, color: C.sub, width: 36, textAlign: 'right' },

  // Directive input
  inputCard: {
    backgroundColor: C.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: C.border,
    padding: 16,
    marginTop: 16,
  },
  inputLabel: { fontSize: 11, color: C.accent, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 10 },
  input: {
    color: C.text,
    fontSize: 15,
    lineHeight: 22,
    minHeight: 90,
    textAlignVertical: 'top',
    padding: 0,
  },
  feedback: { fontSize: 12, marginTop: 8 },
  sendBtn: {
    backgroundColor: C.accent,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 14,
  },
  sendBtnDisabled: { opacity: 0.35 },
  sendBtnText: { color: '#07070F', fontSize: 15, fontWeight: '700' },

  // Absorbed list
  section: { marginTop: 24 },
  sectionTitle: { fontSize: 11, color: C.sub, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 10 },

  absCard: {
    backgroundColor: C.card,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: C.border,
    padding: 12,
    marginBottom: 8,
  },
  chip: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginBottom: 6,
  },
  chipText:  { fontSize: 9, letterSpacing: 1, textTransform: 'uppercase' },
  absTitle:  { fontSize: 13, color: C.text, lineHeight: 18 },
  absFooter: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  absSub:    { fontSize: 10, color: C.sub },
});
