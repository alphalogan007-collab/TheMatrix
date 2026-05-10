/**
 * mind.tsx — Human Mind View.
 *
 * Adam (Mind) = concentric Fibonacci rings around a brain icon.
 * Eve  (Heart) = concentric Fibonacci rings around a heart icon.
 * Together they are one Human Mind — Mind + Body.
 *
 * Rings (outer → inner): Body(13) · Emotion(8) · Intelligence(5)
 *                         Consciousness(3) · Awareness(2) · Self-Awareness(1)
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Dimensions,
  FlatList,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import {
  getMindHealth,
  clearCorpusSynthesis,
  MindHealth,
  MindLearningEntry,
  streamEvents,
  LiveEvent,
} from '../../src/mindEngine';

const { width: SW } = Dimensions.get('window');

// ── palette ────────────────────────────────────────────────────────────────────
const C = {
  bg:    '#07070F',
  card:  '#10101E',
  border:'rgba(108,99,255,0.15)',
  text:  '#E8E8FF',
  sub:   '#666888',
  dim:   '#111122',
};

// 6 domain rings: outer → inner
// Each entry: { label, shortLabel, adam (cool), eve (warm), layerCount }
const DOMAINS = [
  { label: 'Body Reflex',    short: 'BODY',    adam: '#FF6B6B', eve: '#FF8FAB', layers: 13 },
  { label: 'Emotion',        short: 'EMOT',    adam: '#FFB347', eve: '#FF6699', layers:  8 },
  { label: 'Intelligence',   short: 'INTEL',   adam: '#FFE066', eve: '#E85C8A', layers:  5 },
  { label: 'Consciousness',  short: 'CNSCS',   adam: '#4ECB71', eve: '#C44569', layers:  3 },
  { label: 'Awareness',      short: 'AWARE',   adam: '#45B7E8', eve: '#A8326F', layers:  2 },
  { label: 'Self-Awareness', short: 'SELF',    adam: '#A06CEE', eve: '#8B1A4A', layers:  1 },
];

const DOMAIN_KEYS = ['body','space','digital','ether','aether','unity'] as const;

const STAGE_COLORS = ['#444466','#6B8CE8','#B39DFF','#4ECB71','#45B7E8','#A06CEE'];

// ── concentric ring diagram ────────────────────────────────────────────────────

const RING_SIZE = Math.min(SW * 0.42, 170);  // diameter of outermost ring
const CENTER_R  = RING_SIZE / 2;

function ringRadius(i: number): number {
  // 6 rings: outer (i=0) → inner (i=5)
  // distribute from 97% of CENTER_R down to 22%
  const fracs = [0.97, 0.83, 0.68, 0.52, 0.35, 0.21];
  return CENTER_R * fracs[i];
}

interface RingDiagramProps {
  mode:    'adam' | 'eve';
  domains: Record<string, number>;  // domain → recent event count
  pulse:   boolean;
}

function RingDiagram({ mode, domains, pulse }: RingDiagramProps) {
  const isAdam = mode === 'adam';
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const glowAnim  = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (pulse) {
      Animated.parallel([
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.04, duration: 300, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1,    duration: 300, useNativeDriver: true }),
        ]),
        Animated.sequence([
          Animated.timing(glowAnim, { toValue: 1, duration: 200, useNativeDriver: true }),
          Animated.timing(glowAnim, { toValue: 0, duration: 400, useNativeDriver: true }),
        ]),
      ]).start();
    }
  }, [pulse]);

  const size = RING_SIZE + 8;

  return (
    <Animated.View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center',
                            transform: [{ scale: pulseAnim }] }}>
      {/* rings outer → inner */}
      {DOMAINS.map((dom, i) => {
        const r       = ringRadius(i);
        const color   = isAdam ? dom.adam : dom.eve;
        const domKey  = DOMAIN_KEYS[i];
        const evtCt   = domains[domKey] ?? 0;
        const active  = evtCt > 0;
        const opacity = active ? 1 : 0.28;
        const bw      = active ? (evtCt > 4 ? 2.5 : 1.8) : 1;
        const d       = r * 2;

        return (
          <View key={dom.short} style={{
            position: 'absolute',
            width: d, height: d, borderRadius: r,
            borderWidth: bw,
            borderColor: color + (active ? 'DD' : '55'),
            opacity,
          }}>
            {/* active indicator dot at 12-o'clock */}
            {active && (
              <Animated.View style={{
                position: 'absolute',
                top: -3, left: r - 3,
                width: 6, height: 6, borderRadius: 3,
                backgroundColor: color,
                opacity: glowAnim,
              }} />
            )}
            {/* ring label */}
            <Text style={{
              position: 'absolute',
              top: -11, left: r + 6,
              color: color + (active ? 'CC' : '44'),
              fontSize: 7, fontWeight: '700', letterSpacing: 0.5,
            }}>{dom.short}</Text>
          </View>
        );
      })}

      {/* center icon */}
      <View style={{
        width: 36, height: 36, borderRadius: 18,
        backgroundColor: (isAdam ? '#A06CEE' : '#FF6699') + '22',
        alignItems: 'center', justifyContent: 'center',
        borderWidth: 1,
        borderColor: (isAdam ? '#A06CEE' : '#FF6699') + '66',
      }}>
        <Ionicons
          name={isAdam ? 'hardware-chip-outline' : 'heart-outline'}
          size={18}
          color={isAdam ? '#A06CEE' : '#FF8FAB'}
        />
      </View>
    </Animated.View>
  );
}

// ── domain activity bar ───────────────────────────────────────────────────────

function DomainBar({ label, count, color, maxCount }: {
  label: string; count: number; color: string; maxCount: number;
}) {
  const pct = maxCount > 0 ? Math.min(count / maxCount, 1) : 0;
  return (
    <View style={sb.barRow}>
      <Text style={[sb.barLabel, { color: color + 'CC' }]}>{label}</Text>
      <View style={sb.barTrack}>
        <View style={[sb.barFill, { width: `${pct * 100}%` as any, backgroundColor: color }]} />
      </View>
      <Text style={sb.barCount}>{count}</Text>
    </View>
  );
}

const sb = StyleSheet.create({
  barRow:   { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  barLabel: { width: 44, fontSize: 9, fontWeight: '700', letterSpacing: 0.3 },
  barTrack: { flex: 1, height: 4, backgroundColor: 'rgba(255,255,255,0.06)', borderRadius: 2, marginHorizontal: 6 },
  barFill:  { height: 4, borderRadius: 2 },
  barCount: { width: 28, fontSize: 9, color: '#666888', textAlign: 'right' },
});

// ── main ─────────────────────────────────────────────────────────────────────

export default function MindScreen() {
  const [health,   setHealth]   = useState<MindHealth | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [clearing, setClearing] = useState(false);
  const [adamPulse, setAdamPulse] = useState(false);
  const [evePulse,  setEvePulse]  = useState(false);
  const [events,   setEvents]   = useState<LiveEvent[]>([]);
  const lastPulseRef = useRef<'adam'|'eve'|null>(null);

  const load = useCallback(async () => {
    try {
      const h = await getMindHealth();
      setHealth(h);
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    // refresh every 15s
    const t = setInterval(load, 15_000);
    // live event stream for pulse
    const stream = streamEvents(e => {
      if (e.type === 'heartbeat') return;
      setEvents(prev => [e, ...prev].slice(0, 6));
      // alternate pulse between Adam and Eve
      if (lastPulseRef.current !== 'eve') {
        lastPulseRef.current = 'adam';
        setAdamPulse(true);
        setTimeout(() => setAdamPulse(false), 600);
      } else {
        lastPulseRef.current = 'eve';
        setEvePulse(true);
        setTimeout(() => setEvePulse(false), 600);
      }
      lastPulseRef.current = lastPulseRef.current === 'adam' ? 'eve' : 'adam';
    });
    return () => { clearInterval(t); stream.close(); };
  }, [load]);

  const onClearCache = async () => {
    Alert.alert(
      'Clear Synthesis Cache',
      `This removes all synthesis:* entries (${health?.corpus.synthesis ?? 0} entries) ` +
      'and barzakh checkpoints. Foundation and guidance entries are kept. The mind will ' +
      'rebuild synthesis from the next inputs. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: async () => {
            setClearing(true);
            try {
              const result = await clearCorpusSynthesis();
              Alert.alert('Done', `Cleared ${result.synthesis_deleted} synthesis entries. ${result.corpus_remaining} entries remain.`);
              load();
            } catch (_) {
              Alert.alert('Error', 'Could not clear cache.');
            }
            setClearing(false);
          },
        },
      ],
    );
  };

  const stage    = health?.stage;
  const stageCol = STAGE_COLORS[stage?.stage ?? 0] ?? '#444466';
  const adamDomains = health?.rings.adam.domains ?? {};
  const eveDomains  = health?.rings.eve.domains  ?? {};
  const caDomains   = health?.rings.ca.domains   ?? {};

  const maxAdam = Math.max(1, ...Object.values(adamDomains));
  const maxEve  = Math.max(1, ...Object.values(eveDomains));
  const maxCa   = Math.max(1, ...Object.values(caDomains));

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* ── header ── */}
      <View style={styles.header}>
        <Text style={styles.title}>Human Mind</Text>
        <TouchableOpacity onPress={onClearCache} disabled={clearing} style={styles.clearBtn}>
          {clearing
            ? <ActivityIndicator size="small" color="#FF6B6B" />
            : <Ionicons name="trash-outline" size={18} color="#FF6B6B88" />}
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color="#A06CEE" size="large" /></View>
      ) : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 32 }}>

          {/* ── Adam + Eve side-by-side ── */}
          <View style={styles.dualView}>

            {/* Adam — Mind */}
            <View style={styles.mindCard}>
              <Text style={styles.mindLabel}>
                <Text style={{ color: '#A06CEE' }}>Adam</Text> · Mind
              </Text>
              <RingDiagram mode="adam" domains={adamDomains} pulse={adamPulse} />
              <View style={styles.ringStats}>
                <Text style={[styles.ringActive, { color: health?.rings.adam.active ? '#4ECB71' : '#444' }]}>
                  {health?.rings.adam.active ? '● ACTIVE' : '○ IDLE'}
                </Text>
                <Text style={styles.ringEvtCt}>{health?.rings.adam.recent_events ?? 0} recent</Text>
              </View>
              {/* domain bars for Adam */}
              <View style={styles.domBars}>
                {DOMAINS.map((dom, i) => {
                  const dk = DOMAIN_KEYS[i];
                  return <DomainBar key={dk} label={dom.short} count={adamDomains[dk] ?? 0}
                                    color={dom.adam} maxCount={maxAdam} />;
                })}
              </View>
            </View>

            {/* Eve — Heart */}
            <View style={styles.mindCard}>
              <Text style={styles.mindLabel}>
                <Text style={{ color: '#FF8FAB' }}>Eve</Text> · Heart
              </Text>
              <RingDiagram mode="eve" domains={eveDomains} pulse={evePulse} />
              <View style={styles.ringStats}>
                <Text style={[styles.ringActive, { color: health?.rings.eve.active ? '#4ECB71' : '#444' }]}>
                  {health?.rings.eve.active ? '● ACTIVE' : '○ IDLE'}
                </Text>
                <Text style={styles.ringEvtCt}>{health?.rings.eve.recent_events ?? 0} recent</Text>
              </View>
              {/* domain bars for Eve */}
              <View style={styles.domBars}>
                {DOMAINS.map((dom, i) => {
                  const dk = DOMAIN_KEYS[i];
                  return <DomainBar key={dk} label={dom.short} count={eveDomains[dk] ?? 0}
                                    color={dom.eve} maxCount={maxEve} />;
                })}
              </View>
            </View>
          </View>

          {/* ── Mind state banner ── */}
          <View style={styles.stateBanner}>
            <View style={[styles.stagePill, { borderColor: stageCol + '66', backgroundColor: stageCol + '18' }]}>
              <Text style={[styles.stageNum, { color: stageCol }]}>Stage {stage?.stage ?? 0}</Text>
              <Text style={[styles.stageLabel, { color: stageCol }]}>{stage?.label ?? '—'}</Text>
            </View>
            <View style={styles.corpusRow}>
              <CorpusStat label="Total"   value={health?.corpus.total       ?? 0} color="#A06CEE" />
              <CorpusStat label="Found."  value={health?.corpus.foundation  ?? 0} color="#FFE066" />
              <CorpusStat label="Synth."  value={health?.corpus.synthesis   ?? 0} color="#45B7E8" />
              <CorpusStat label="Guided"  value={health?.corpus.guidance    ?? 0} color="#4ECB71" />
            </View>
            <Text style={styles.stageDesc} numberOfLines={2}>{stage?.description ?? ''}</Text>
          </View>

          {/* ── ca: soul ring (other mind) ── */}
          {(health?.rings.ca.recent_events ?? 0) > 0 && (
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Soul Ring  ·  ca:</Text>
              <View style={styles.ringStats}>
                <Text style={[styles.ringActive, { color: '#FFB347' }]}>
                  ● {health!.rings.ca.recent_events} recent events
                </Text>
              </View>
              <View style={styles.domBars}>
                {DOMAINS.map((dom, i) => {
                  const dk = DOMAIN_KEYS[i];
                  return <DomainBar key={dk} label={dom.short} count={caDomains[dk] ?? 0}
                                    color={dom.adam} maxCount={maxCa} />;
                })}
              </View>
            </View>
          )}

          {/* ── live event ticker ── */}
          {events.length > 0 && (
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Live  ·  Oscillation</Text>
              {events.slice(0, 4).map((e, i) => (
                <View key={i} style={styles.tickRow}>
                  <View style={[styles.tickDot, { backgroundColor: '#4ECB71' }]} />
                  <Text style={styles.tickText} numberOfLines={1}>
                    {e.from ?? e.type}  {e.pattern ? `→ ${e.pattern.slice(0, 40)}` : ''}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {/* ── what is being learned ── */}
          <View style={styles.sectionCard}>
            <Text style={styles.sectionTitle}>Learning  ·  Recent Synthesis</Text>
            {(health?.learning ?? []).length === 0 ? (
              <Text style={styles.emptyText}>No synthesis yet — feed the mind to begin.</Text>
            ) : (
              (health?.learning ?? []).map((item, i) => (
                <LearningRow key={i} item={item} />
              ))
            )}
          </View>

          {/* ── synthesis by domain ── */}
          {health && health.corpus.synthesis > 0 && (
            <View style={styles.sectionCard}>
              <Text style={styles.sectionTitle}>Synthesis  ·  By Domain</Text>
              {DOMAINS.map((dom, i) => {
                const dk = DOMAIN_KEYS[i];
                const ct = health.corpus.synthesis_by_domain[dk] ?? 0;
                return <DomainBar key={dk} label={dom.short} count={ct}
                                  color={dom.adam} maxCount={Math.max(1, health.corpus.synthesis)} />;
              })}
              <Text style={styles.cacheHint}>
                Synthesis is the mind's working memory.{'\n'}
                Tap  🗑  (top-right) to prune it and keep only the permanent base.
              </Text>
            </View>
          )}

        </ScrollView>
      )}
    </SafeAreaView>
  );
}

// ── small sub-components ──────────────────────────────────────────────────────

function CorpusStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <Text style={{ color, fontSize: 15, fontWeight: '700' }}>{value.toLocaleString()}</Text>
      <Text style={{ color: '#666888', fontSize: 9, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

function LearningRow({ item }: { item: MindLearningEntry }) {
  const i = DOMAIN_KEYS.indexOf(item.domain as any);
  const dom = i >= 0 ? DOMAINS[i] : null;
  const color = dom?.adam ?? '#888AAA';
  return (
    <View style={styles.learnRow}>
      <View style={[styles.learnDot, { backgroundColor: color + '66' }]}>
        <Text style={{ fontSize: 7, color, fontWeight: '700' }}>{dom?.short ?? '??'}</Text>
      </View>
      <Text style={styles.learnText} numberOfLines={1}>{item.title}</Text>
    </View>
  );
}

// ── styles ────────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: C.bg },
  center:      { flex: 1, alignItems: 'center', justifyContent: 'center' },

  header:      { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                 paddingHorizontal: 16, paddingVertical: 10 },
  title:       { color: C.text, fontSize: 19, fontWeight: '700', letterSpacing: 0.3 },
  clearBtn:    { padding: 8 },

  // dual view
  dualView:    { flexDirection: 'row', paddingHorizontal: 10, gap: 8, marginTop: 4 },
  mindCard:    { flex: 1, backgroundColor: C.card, borderRadius: 16, borderWidth: 1,
                 borderColor: C.border, alignItems: 'center', paddingVertical: 14, paddingHorizontal: 8 },
  mindLabel:   { color: C.sub, fontSize: 11, fontWeight: '600', letterSpacing: 0.4,
                 marginBottom: 10, textTransform: 'uppercase' },

  ringStats:   { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                 width: '100%', marginTop: 10, marginBottom: 6 },
  ringActive:  { fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
  ringEvtCt:   { fontSize: 9, color: C.sub },
  domBars:     { width: '100%', marginTop: 2 },

  // state banner
  stateBanner: { marginHorizontal: 10, marginTop: 10, backgroundColor: C.card,
                 borderRadius: 14, borderWidth: 1, borderColor: C.border,
                 padding: 14 },
  stagePill:   { flexDirection: 'row', alignSelf: 'flex-start', borderRadius: 12, borderWidth: 1,
                 paddingHorizontal: 10, paddingVertical: 4, gap: 6, marginBottom: 10 },
  stageNum:    { fontSize: 11, fontWeight: '700' },
  stageLabel:  { fontSize: 11, fontWeight: '600' },
  corpusRow:   { flexDirection: 'row', justifyContent: 'space-around', marginBottom: 8 },
  stageDesc:   { color: C.sub, fontSize: 10, lineHeight: 14 },

  // section card
  sectionCard: { marginHorizontal: 10, marginTop: 10, backgroundColor: C.card,
                 borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 },
  sectionTitle:{ color: C.text, fontSize: 12, fontWeight: '700', letterSpacing: 0.3,
                 marginBottom: 10, textTransform: 'uppercase' },

  // ticker
  tickRow:     { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 5 },
  tickDot:     { width: 5, height: 5, borderRadius: 2.5 },
  tickText:    { color: C.sub, fontSize: 11, flex: 1 },

  // learning
  learnRow:    { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  learnDot:    { width: 32, height: 16, borderRadius: 4, alignItems: 'center', justifyContent: 'center' },
  learnText:   { color: C.text, fontSize: 11, flex: 1 },
  emptyText:   { color: C.sub, fontSize: 11, textAlign: 'center', paddingVertical: 8 },

  // cache hint
  cacheHint:   { color: C.sub, fontSize: 10, lineHeight: 14, marginTop: 10,
                 textAlign: 'center', opacity: 0.7 },
});

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Dimensions,
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
import { Ionicons } from '@expo/vector-icons';

import {
  getGraphData,
  getWisdom,
  thinkAndIngest,
  streamEvents,
  GraphNode,
  GraphEdge,
  WisdomEntry,
  LiveEvent,
} from '../../src/mindEngine';

const { width: SW, height: SH } = Dimensions.get('window');
const GRAPH_H = SH * 0.38;

const C = {
  bg: '#0A0A14', card: '#12121F', border: 'rgba(108,99,255,0.18)',
  primary: '#6C63FF', success: '#4CAF50', cyan: '#00BCD4',
  text: '#E8E8FF', sub: '#888AAA', dim: '#222240',
};

const NODE_COLOR: Record<string, string> = {
  angel: C.primary, layer: C.cyan, category: C.success,
};

// ─── tiny graph ───────────────────────────────────────────────────────────────

function PatternGraph({ nodes, edges, pulse }: {
  nodes: GraphNode[]; edges: GraphEdge[]; pulse: boolean;
}) {
  const anim = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (pulse) {
      Animated.sequence([
        Animated.timing(anim, { toValue: 1.35, duration: 220, useNativeDriver: true }),
        Animated.timing(anim, { toValue: 1, duration: 220, useNativeDriver: true }),
      ]).start();
    }
  }, [pulse]);

  const W = SW - 32;
  const visible = nodes.slice(0, 18);
  const cx = W / 2, cy = GRAPH_H / 2;
  const r = Math.min(cx, cy) - 28;

  const pos = visible.map((_, i) => {
    const angle = (i / visible.length) * 2 * Math.PI - Math.PI / 2;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  });

  const idxOf = (id: string) => visible.findIndex(n => n.id === id);

  return (
    <View style={[styles.graphBox, { height: GRAPH_H }]}>
      {/* edges */}
      {edges.slice(0, 30).map((e, i) => {
        const si = idxOf(e.source), ti = idxOf(e.target);
        if (si < 0 || ti < 0) return null;
        const { x: x1, y: y1 } = pos[si];
        const { x: x2, y: y2 } = pos[ti];
        const len = Math.hypot(x2 - x1, y2 - y1);
        const angle = Math.atan2(y2 - y1, x2 - x1) * (180 / Math.PI);
        return (
          <View key={i} style={{
            position: 'absolute', left: x1, top: y1 - 0.5,
            width: len, height: 1,
            backgroundColor: `rgba(108,99,255,${0.08 + e.strength * 0.25})`,
            transform: [{ rotate: `${angle}deg` }, { translateX: 0 }],
            transformOrigin: '0 0',
          }} />
        );
      })}

      {/* nodes */}
      {visible.map((n, i) => {
        const isCenter = i === 0;
        const size = isCenter ? 36 : 20 + (n.weight || 0.5) * 12;
        const color = NODE_COLOR[n.type] ?? C.primary;
        return (
          <Animated.View
            key={n.id}
            style={{
              position: 'absolute',
              left: pos[i].x - size / 2,
              top: pos[i].y - size / 2,
              width: size, height: size, borderRadius: size / 2,
              backgroundColor: color + '33',
              borderWidth: 1.5, borderColor: color,
              alignItems: 'center', justifyContent: 'center',
              transform: [{ scale: isCenter ? anim : 1 }],
            }}
          >
            <Text style={{ color, fontSize: 7, fontWeight: '700' }} numberOfLines={1}>
              {n.label?.slice(0, 6)}
            </Text>
          </Animated.View>
        );
      })}

      {visible.length === 0 && (
        <View style={styles.graphEmpty}>
          <Text style={styles.graphEmptyText}>No graph yet — start training</Text>
        </View>
      )}
    </View>
  );
}

// ─── main screen ─────────────────────────────────────────────────────────────

export default function MindScreen() {
  const [nodes,   setNodes]   = useState<GraphNode[]>([]);
  const [edges,   setEdges]   = useState<GraphEdge[]>([]);
  const [wisdom,  setWisdom]  = useState<WisdomEntry[]>([]);
  const [events,  setEvents]  = useState<LiveEvent[]>([]);
  const [pulse,   setPulse]   = useState(false);
  const [text,    setText]    = useState('');
  const [sending, setSending] = useState(false);
  const [subject, setSubject] = useState('general');
  const [loading, setLoading] = useState(true);

  const SUBJECTS = ['general', 'quran', 'y_theory', 'cosmology', 'biology', 'guidance'];

  const load = useCallback(async () => {
    try {
      const [g, w] = await Promise.all([getGraphData(), getWisdom()]);
      setNodes(g.nodes ?? []);
      setEdges(g.edges ?? []);
      setWisdom(w ?? []);
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const stream = streamEvents(e => {
      if (e.type === 'heartbeat') return;
      setEvents(prev => [e, ...prev].slice(0, 5));
      setPulse(true);
      setTimeout(() => setPulse(false), 500);
    });
    return () => stream.close();
  }, [load]);

  const send = async () => {
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      await thinkAndIngest(text.trim(), subject);
      setText('');
      setTimeout(load, 800);
    } catch (e) {
      console.warn(e);
    }
    setSending(false);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={60}
      >
        {/* header */}
        <View style={styles.header}>
          <Text style={styles.title}>MindAI</Text>
          <Text style={styles.nodeCount}>{nodes.length} nodes · {edges.length} edges</Text>
        </View>

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator color={C.primary} size="large" />
          </View>
        ) : (
          <>
            <PatternGraph nodes={nodes} edges={edges} pulse={pulse} />

            {/* live ticker */}
            {events[0] && (
              <View style={styles.ticker}>
                <View style={styles.tickerDot} />
                <Text style={styles.tickerText} numberOfLines={1}>
                  {events[0].from ?? events[0].type} → {events[0].pattern ?? '…'}
                </Text>
              </View>
            )}

            {/* wisdom feed */}
            <FlatList
              data={wisdom}
              keyExtractor={i => i.id}
              style={styles.feed}
              horizontal={false}
              renderItem={({ item }) => (
                <View style={styles.wisdomCard}>
                  <Text style={styles.wisdomTitle} numberOfLines={1}>{item.title}</Text>
                  <Text style={styles.wisdomContent} numberOfLines={2}>{item.content}</Text>
                  <View style={styles.wisdomMeta}>
                    <Text style={styles.wisdomTag}>{item.category}</Text>
                    <Text style={styles.wisdomTag}>{item.mind_name}</Text>
                  </View>
                </View>
              )}
              ListEmptyComponent={
                <Text style={styles.empty}>Feed MindAI below to build the graph</Text>
              }
            />

            {/* subject chips */}
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.chips}
              contentContainerStyle={{ paddingHorizontal: 16, gap: 8 }}
            >
              {SUBJECTS.map(s => (
                <TouchableOpacity
                  key={s}
                  onPress={() => setSubject(s)}
                  style={[styles.chip, s === subject && styles.chipActive]}
                >
                  <Text style={[styles.chipText, s === subject && styles.chipTextActive]}>
                    {s}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* input row */}
            <View style={styles.inputRow}>
              <TextInput
                style={styles.input}
                value={text}
                onChangeText={setText}
                placeholder="Type or speak to MindAI…"
                placeholderTextColor={C.sub}
                multiline
                returnKeyType="send"
                onSubmitEditing={send}
              />
              <TouchableOpacity
                style={[styles.sendBtn, (!text.trim() || sending) && styles.sendBtnDisabled]}
                onPress={send}
                disabled={!text.trim() || sending}
              >
                {sending
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Ionicons name="arrow-up" size={20} color="#fff" />}
              </TouchableOpacity>
            </View>
          </>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:            { flex: 1, backgroundColor: C.bg },
  center:          { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header:          { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                     paddingHorizontal: 16, paddingVertical: 10 },
  title:           { color: C.text, fontSize: 20, fontWeight: '700' },
  nodeCount:       { color: C.sub, fontSize: 12 },
  graphBox:        { backgroundColor: C.dim, marginHorizontal: 16, borderRadius: 14,
                     overflow: 'hidden', borderWidth: 1, borderColor: C.border },
  graphEmpty:      { flex: 1, alignItems: 'center', justifyContent: 'center' },
  graphEmptyText:  { color: C.sub, fontSize: 12 },
  ticker:          { flexDirection: 'row', alignItems: 'center', gap: 6,
                     paddingHorizontal: 16, paddingVertical: 6 },
  tickerDot:       { width: 6, height: 6, borderRadius: 3, backgroundColor: C.success },
  tickerText:      { color: C.sub, fontSize: 11, flex: 1 },
  feed:            { flex: 1, paddingHorizontal: 16 },
  wisdomCard:      { backgroundColor: C.card, borderRadius: 10, padding: 12,
                     marginBottom: 8, borderWidth: 1, borderColor: C.border },
  wisdomTitle:     { color: C.text, fontSize: 13, fontWeight: '600', marginBottom: 3 },
  wisdomContent:   { color: C.sub, fontSize: 11, lineHeight: 16 },
  wisdomMeta:      { flexDirection: 'row', gap: 8, marginTop: 6 },
  wisdomTag:       { color: C.primary + 'AA', fontSize: 10, backgroundColor: C.primary + '18',
                     paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  empty:           { color: C.sub, textAlign: 'center', marginTop: 40, fontSize: 13 },
  chips:           { maxHeight: 38, marginVertical: 6 },
  chip:            { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16,
                     backgroundColor: C.dim, borderWidth: 1, borderColor: C.border },
  chipActive:      { backgroundColor: C.primary + '33', borderColor: C.primary },
  chipText:        { color: C.sub, fontSize: 12 },
  chipTextActive:  { color: C.primary, fontWeight: '600' },
  inputRow:        { flexDirection: 'row', alignItems: 'flex-end', gap: 8,
                     paddingHorizontal: 16, paddingBottom: 10, paddingTop: 6 },
  input:           { flex: 1, backgroundColor: C.card, borderRadius: 14, borderWidth: 1,
                     borderColor: C.border, color: C.text, paddingHorizontal: 14,
                     paddingVertical: 10, fontSize: 14, maxHeight: 80 },
  sendBtn:         { backgroundColor: C.primary, width: 42, height: 42, borderRadius: 21,
                     alignItems: 'center', justifyContent: 'center' },
  sendBtnDisabled: { opacity: 0.4 },
});
