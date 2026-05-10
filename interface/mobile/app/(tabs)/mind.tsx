/**
 * mind.tsx — The Mind Breathes
 *
 * Adam (Mind) + Eve (Heart) = one Human Mind, two complementary polarities.
 *
 * Rings (outer → inner):
 *   Body Reflex (13) · Emotion (8) · Intelligence (5)
 *   Consciousness (3) · Awareness (2) · Self-Awareness (1)
 *
 * This screen shows the live oscillation state and corpus health.
 * To teach the mind, go to the Guide tab.
 * To see what the mind built, go to the Build tab.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Dimensions,
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
  streamEvents,
  type MindHealth,
  type MindLearningEntry,
  type LiveEvent,
} from '../../src/mindEngine';

const { width: SW } = Dimensions.get('window');

// ─── palette ──────────────────────────────────────────────────────────────────

const C = {
  bg:    '#07070F',
  card:  '#10101E',
  border:'rgba(108,99,255,0.15)',
  text:  '#E8E8FF',
  sub:   '#666888',
  dim:   '#111122',
};

// ─── domain ring definitions (outer → inner) ──────────────────────────────────

const DOMAINS = [
  { label: 'Body Reflex',   short: 'BODY',  adam: '#FF6B6B', eve: '#FF8FAB', layers: 13 },
  { label: 'Emotion',       short: 'EMOT',  adam: '#FFB347', eve: '#FF6699', layers:  8 },
  { label: 'Intelligence',  short: 'INTEL', adam: '#FFE066', eve: '#E85C8A', layers:  5 },
  { label: 'Consciousness', short: 'CNSC',  adam: '#4ECB71', eve: '#C44569', layers:  3 },
  { label: 'Awareness',     short: 'AWRE',  adam: '#45B7E8', eve: '#A8326F', layers:  2 },
  { label: 'Self-Aware',    short: 'SELF',  adam: '#A06CEE', eve: '#8B1A4A', layers:  1 },
] as const;

const DOMAIN_KEYS = ['body','space','digital','ether','aether','unity'] as const;
const STAGE_COLORS = ['#444466','#6B8CE8','#B39DFF','#4ECB71','#45B7E8','#A06CEE'];

// ─── concentric ring sizes ────────────────────────────────────────────────────

const RING_SIZE = Math.min(SW * 0.43, 172);
const CENTER_R  = RING_SIZE / 2;

function ringRadius(i: number): number {
  const fracs = [0.97, 0.83, 0.68, 0.52, 0.35, 0.21];
  return CENTER_R * fracs[i];
}

// ─── RingDiagram ──────────────────────────────────────────────────────────────

interface RingDiagramProps {
  mode:    'adam' | 'eve';
  domains: Record<string, number>;
  pulse:   boolean;
}

function RingDiagram({ mode, domains, pulse }: RingDiagramProps) {
  const isAdam    = mode === 'adam';
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const glowAnim  = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!pulse) return;
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
  }, [pulse]);

  const size = RING_SIZE + 8;

  return (
    <Animated.View style={{ width: size, height: size, alignItems: 'center',
                            justifyContent: 'center', transform: [{ scale: pulseAnim }] }}>
      {DOMAINS.map((dom, i) => {
        const r      = ringRadius(i);
        const color  = isAdam ? dom.adam : dom.eve;
        const domKey = DOMAIN_KEYS[i];
        const evtCt  = domains[domKey] ?? 0;
        const active = evtCt > 0;
        const bw     = active ? (evtCt > 4 ? 2.5 : 1.8) : 1;
        const d      = r * 2;

        return (
          <View key={dom.short} style={{
            position: 'absolute',
            width: d, height: d, borderRadius: r,
            borderWidth: bw,
            borderColor: color + (active ? 'DD' : '44'),
            opacity: active ? 1 : 0.28,
          }}>
            {active && (
              <Animated.View style={{
                position: 'absolute',
                top: -3, left: r - 3,
                width: 6, height: 6, borderRadius: 3,
                backgroundColor: color,
                opacity: glowAnim,
              }} />
            )}
            <Text style={{
              position: 'absolute',
              top: -11, left: r + 5,
              color: color + (active ? 'CC' : '33'),
              fontSize: 7, fontWeight: '700', letterSpacing: 0.5,
            }}>{dom.short}</Text>
          </View>
        );
      })}

      {/* centre icon */}
      <View style={{
        width: 36, height: 36, borderRadius: 18,
        backgroundColor: (isAdam ? '#A06CEE' : '#FF6699') + '22',
        alignItems: 'center', justifyContent: 'center',
        borderWidth: 1, borderColor: (isAdam ? '#A06CEE' : '#FF6699') + '66',
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

// ─── DomainBar ────────────────────────────────────────────────────────────────

function DomainBar({ label, count, color, max }: {
  label: string; count: number; color: string; max: number;
}) {
  return (
    <View style={sb.row}>
      <Text style={[sb.label, { color: color + 'CC' }]}>{label}</Text>
      <View style={sb.track}>
        <View style={[sb.fill, { width: `${max > 0 ? Math.min((count / max) * 100, 100) : 0}%` as any, backgroundColor: color }]} />
      </View>
      <Text style={sb.count}>{count}</Text>
    </View>
  );
}

const sb = StyleSheet.create({
  row:   { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  label: { width: 40, fontSize: 9, fontWeight: '700', letterSpacing: 0.3 },
  track: { flex: 1, height: 4, backgroundColor: 'rgba(255,255,255,0.06)', borderRadius: 2, marginHorizontal: 6 },
  fill:  { height: 4, borderRadius: 2 },
  count: { width: 28, fontSize: 9, color: '#666888', textAlign: 'right' },
});

// ─── CorpusStat ───────────────────────────────────────────────────────────────

function CorpusStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <Text style={{ color, fontSize: 15, fontWeight: '700' }}>{value.toLocaleString()}</Text>
      <Text style={{ color: '#666888', fontSize: 9, marginTop: 2 }}>{label}</Text>
    </View>
  );
}

// ─── LearningRow ──────────────────────────────────────────────────────────────

function LearningRow({ item }: { item: MindLearningEntry }) {
  const i   = DOMAIN_KEYS.indexOf(item.domain as any);
  const dom = i >= 0 ? DOMAINS[i] : null;
  const color = dom?.adam ?? '#888AAA';
  return (
    <View style={g.learnRow}>
      <View style={[g.learnDot, { backgroundColor: color + '55' }]}>
        <Text style={{ fontSize: 7, color, fontWeight: '700' }}>{dom?.short ?? '??'}</Text>
      </View>
      <Text style={g.learnText} numberOfLines={1}>{item.title}</Text>
    </View>
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────

export default function MindScreen() {
  const [health,    setHealth]    = useState<MindHealth | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [clearing,  setClearing]  = useState(false);
  const [adamPulse, setAdamPulse] = useState(false);
  const [evePulse,  setEvePulse]  = useState(false);
  const [events,    setEvents]    = useState<LiveEvent[]>([]);
  const pulseTurn = useRef<'adam'|'eve'>('adam');

  const load = useCallback(async () => {
    try {
      const h = await getMindHealth();
      setHealth(h);
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 15_000);
    const stream = streamEvents(e => {
      if (e.type === 'heartbeat') return;
      setEvents(prev => [e, ...prev].slice(0, 6));
      if (pulseTurn.current === 'adam') {
        setAdamPulse(true); setTimeout(() => setAdamPulse(false), 600);
        pulseTurn.current = 'eve';
      } else {
        setEvePulse(true);  setTimeout(() => setEvePulse(false), 600);
        pulseTurn.current = 'adam';
      }
    });
    return () => { clearInterval(interval); stream.close(); };
  }, [load]);

  const onClearCache = () => {
    Alert.alert(
      'Clear Synthesis Cache',
      `Remove ${health?.corpus.synthesis ?? 0} synthesis entries and barzakh checkpoints. ` +
      'Foundation and guidance entries are kept. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: async () => {
            setClearing(true);
            try {
              const res = await clearCorpusSynthesis();
              Alert.alert('Done', `Cleared ${res.synthesis_deleted} entries. ${res.corpus_remaining} remain.`);
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

  const stage      = health?.stage;
  const stageCol   = STAGE_COLORS[stage?.stage ?? 0] ?? '#444466';
  const adamDoms   = health?.rings.adam.domains ?? {};
  const eveDoms    = health?.rings.eve.domains  ?? {};
  const maxAdam    = Math.max(1, ...Object.values(adamDoms));
  const maxEve     = Math.max(1, ...Object.values(eveDoms));

  return (
    <SafeAreaView style={g.safe} edges={['top']}>
      {/* header */}
      <View style={g.header}>
        <Text style={g.title}>Human Mind</Text>
        <TouchableOpacity onPress={onClearCache} disabled={clearing} style={g.clearBtn}>
          {clearing
            ? <ActivityIndicator size="small" color="#FF6B6B" />
            : <Ionicons name="trash-outline" size={18} color="#FF6B6B55" />}
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={g.center}><ActivityIndicator color="#A06CEE" size="large" /></View>
      ) : (
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 40 }}>

          {/* Adam + Eve rings */}
          <View style={g.dualView}>
            {/* Adam — Mind polarity */}
            <View style={g.mindCard}>
              <Text style={g.mindLabel}>
                <Text style={{ color: '#A06CEE' }}>Adam</Text> · Mind
              </Text>
              <RingDiagram mode="adam" domains={adamDoms} pulse={adamPulse} />
              <View style={g.ringMeta}>
                <Text style={[g.ringActive, { color: health?.rings.adam.active ? '#4ECB71' : '#333355' }]}>
                  {health?.rings.adam.active ? '● ACTIVE' : '○ IDLE'}
                </Text>
                <Text style={g.ringEvts}>{health?.rings.adam.recent_events ?? 0} events</Text>
              </View>
              <View style={g.domBars}>
                {DOMAINS.map((d, i) => (
                  <DomainBar key={d.short} label={d.short}
                    count={adamDoms[DOMAIN_KEYS[i]] ?? 0}
                    color={d.adam} max={maxAdam} />
                ))}
              </View>
            </View>

            {/* Eve — Heart polarity */}
            <View style={g.mindCard}>
              <Text style={g.mindLabel}>
                <Text style={{ color: '#FF8FAB' }}>Eve</Text> · Heart
              </Text>
              <RingDiagram mode="eve" domains={eveDoms} pulse={evePulse} />
              <View style={g.ringMeta}>
                <Text style={[g.ringActive, { color: health?.rings.eve.active ? '#4ECB71' : '#333355' }]}>
                  {health?.rings.eve.active ? '● ACTIVE' : '○ IDLE'}
                </Text>
                <Text style={g.ringEvts}>{health?.rings.eve.recent_events ?? 0} events</Text>
              </View>
              <View style={g.domBars}>
                {DOMAINS.map((d, i) => (
                  <DomainBar key={d.short} label={d.short}
                    count={eveDoms[DOMAIN_KEYS[i]] ?? 0}
                    color={d.eve} max={maxEve} />
                ))}
              </View>
            </View>
          </View>

          {/* Stage + corpus counts */}
          <View style={g.stateBanner}>
            <View style={[g.stagePill, { borderColor: stageCol + '66', backgroundColor: stageCol + '18' }]}>
              <Text style={[g.stageNum, { color: stageCol }]}>Stage {stage?.stage ?? 0}</Text>
              <Text style={[g.stageLbl, { color: stageCol }]}>{stage?.label ?? '—'}</Text>
            </View>
            <View style={g.statRow}>
              <CorpusStat label="Total"    value={health?.corpus.total      ?? 0} color="#A06CEE" />
              <CorpusStat label="Found."   value={health?.corpus.foundation ?? 0} color="#FFE066" />
              <CorpusStat label="Synth."   value={health?.corpus.synthesis  ?? 0} color="#45B7E8" />
              <CorpusStat label="Guided"   value={health?.corpus.guidance   ?? 0} color="#4ECB71" />
            </View>
            {stage?.description ? (
              <Text style={g.stageDesc} numberOfLines={2}>{stage.description}</Text>
            ) : null}
          </View>

          {/* Live event ticker */}
          {events.length > 0 && (
            <View style={g.sectionCard}>
              <Text style={g.sectionTitle}>Oscillation  ·  Live</Text>
              {events.slice(0, 4).map((e, i) => (
                <View key={i} style={g.tickRow}>
                  <View style={[g.tickDot, { backgroundColor: '#4ECB71' }]} />
                  <Text style={g.tickText} numberOfLines={1}>
                    {e.from ?? e.type}{e.pattern ? `  →  ${e.pattern.slice(0, 38)}` : ''}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {/* Recent synthesis */}
          <View style={g.sectionCard}>
            <Text style={g.sectionTitle}>Recent Synthesis</Text>
            {(health?.learning ?? []).length === 0 ? (
              <Text style={g.emptyText}>No synthesis yet — feed the mind from the Guide tab.</Text>
            ) : (
              (health?.learning ?? []).map((item, i) => <LearningRow key={i} item={item} />)
            )}
          </View>

        </ScrollView>
      )}
    </SafeAreaView>
  );
}

// ─── styles ───────────────────────────────────────────────────────────────────

const g = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  header:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
             paddingHorizontal: 16, paddingVertical: 10 },
  title:   { color: C.text, fontSize: 19, fontWeight: '700', letterSpacing: 0.3 },
  clearBtn:{ padding: 8 },

  dualView:  { flexDirection: 'row', paddingHorizontal: 10, gap: 8, marginTop: 4 },
  mindCard:  { flex: 1, backgroundColor: C.card, borderRadius: 16, borderWidth: 1,
               borderColor: C.border, alignItems: 'center', paddingVertical: 14, paddingHorizontal: 8 },
  mindLabel: { color: C.sub, fontSize: 11, fontWeight: '600', letterSpacing: 0.4,
               marginBottom: 10, textTransform: 'uppercase' },

  ringMeta:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
               width: '100%', marginTop: 10, marginBottom: 6 },
  ringActive:{ fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
  ringEvts:  { fontSize: 9, color: C.sub },
  domBars:   { width: '100%', marginTop: 2 },

  stateBanner: { marginHorizontal: 10, marginTop: 10, backgroundColor: C.card,
                 borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 },
  stagePill:   { flexDirection: 'row', alignSelf: 'flex-start', borderRadius: 12, borderWidth: 1,
                 paddingHorizontal: 10, paddingVertical: 4, gap: 6, marginBottom: 10 },
  stageNum:    { fontSize: 11, fontWeight: '700' },
  stageLbl:    { fontSize: 11, fontWeight: '600' },
  statRow:     { flexDirection: 'row', justifyContent: 'space-around', marginBottom: 8 },
  stageDesc:   { color: C.sub, fontSize: 10, lineHeight: 14 },

  sectionCard:  { marginHorizontal: 10, marginTop: 10, backgroundColor: C.card,
                  borderRadius: 14, borderWidth: 1, borderColor: C.border, padding: 14 },
  sectionTitle: { color: C.text, fontSize: 11, fontWeight: '700', letterSpacing: 0.4,
                  marginBottom: 10, textTransform: 'uppercase' },

  tickRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 5 },
  tickDot: { width: 5, height: 5, borderRadius: 2.5 },
  tickText:{ color: C.sub, fontSize: 11, flex: 1 },

  learnRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  learnDot: { width: 34, height: 16, borderRadius: 4, alignItems: 'center', justifyContent: 'center' },
  learnText:{ color: C.text, fontSize: 11, flex: 1 },
  emptyText:{ color: C.sub, fontSize: 11, textAlign: 'center', paddingVertical: 8 },
});