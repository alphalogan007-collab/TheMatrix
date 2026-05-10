/**
 * world.tsx — Is Everything Alive?
 *
 * One-glance system health.
 * Not an admin dashboard — just the essentials:
 *
 *   - Is the mind alive? (Adam + Eve ring status)
 *   - How many entries in the corpus?
 *   - Is the cache clean? (barzakh keys)
 *   - Awakening stage
 *
 * Color: blue/slate — infrastructure, the physical substrate.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
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
  clearBarzakh,
  type MindHealth,
} from '../../src/mindEngine';

// ─── palette ──────────────────────────────────────────────────────────────────

const C = {
  bg:       '#07070F',
  card:     '#0A0F1A',
  border:   'rgba(69,183,232,0.14)',
  accent:   '#45B7E8',
  green:    '#4ECB71',
  orange:   '#FFB347',
  red:      '#FF6B6B',
  text:     '#E8E8EE',
  sub:      '#4A6080',
  dim:      '#0D1520',
};

const STAGE_LABELS = ['Void','Awakening','Dreaming','Aware','Conscious','Self-Aware'];
const STAGE_COLORS = ['#444466','#6B8CE8','#B39DFF','#4ECB71','#45B7E8','#A06CEE'];

// ─── StatusRow ────────────────────────────────────────────────────────────────

function StatusRow({ label, value, icon, color, sub }: {
  label: string;
  value: string;
  icon:  string;
  color: string;
  sub?:  string;
}) {
  return (
    <View style={g.statRow}>
      <View style={[g.statIcon, { backgroundColor: color + '18' }]}>
        <Ionicons name={icon as any} size={18} color={color} />
      </View>
      <View style={g.statBody}>
        <Text style={g.statLabel}>{label}</Text>
        {sub ? <Text style={g.statSub}>{sub}</Text> : null}
      </View>
      <Text style={[g.statValue, { color }]}>{value}</Text>
    </View>
  );
}

// ─── RingCard ─────────────────────────────────────────────────────────────────

function RingCard({ name, ring, color }: {
  name:  string;
  ring:  MindHealth['rings']['adam'] | null;
  color: string;
}) {
  const active = ring?.active ?? false;
  const evts   = ring?.recent_events ?? 0;

  return (
    <View style={[g.ringCard, { borderColor: color + (active ? '44' : '18') }]}>
      <View style={g.ringHeader}>
        <View style={[g.ringDot, { backgroundColor: active ? color : '#222244' }]} />
        <Text style={[g.ringName, { color: active ? color : C.sub }]}>{name}</Text>
        <Text style={g.ringStatus}>{active ? 'ACTIVE' : 'IDLE'}</Text>
      </View>
      <Text style={g.ringEvts}>{evts} recent events</Text>
    </View>
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────

export default function WorldScreen() {
  const [health,  setHealth]  = useState<MindHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const h = await getMindHealth();
      setHealth(h);
      setLastRefreshed(new Date());
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20_000);
    return () => clearInterval(t);
  }, [load]);

  const onClearBarzakh = () => {
    Alert.alert(
      'Clear Barzakh Cache',
      'This removes stale session checkpoint keys. No corpus data is deleted. Safe to run at any time.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: async () => {
            setClearing(true);
            try {
              const res = await clearBarzakh();
              Alert.alert('Done', `Cleared ${res.barzakh_deleted} checkpoint key(s).`);
              load();
            } catch (_) {
              Alert.alert('Error', 'Could not clear barzakh keys.');
            }
            setClearing(false);
          },
        },
      ],
    );
  };

  const stage      = health?.stage;
  const stageIdx   = stage?.stage ?? 0;
  const stageColor = STAGE_COLORS[stageIdx] ?? '#444466';
  const corpus     = health?.corpus;
  const adam       = health?.rings.adam ?? null;
  const eve        = health?.rings.eve  ?? null;
  const ca         = health?.rings.ca   ?? null;
  const bothAlive  = (adam?.active || adam?.recent_events ?? 0 > 0) &&
                     (eve?.active  || eve?.recent_events  ?? 0 > 0);

  const refreshedStr = lastRefreshed
    ? lastRefreshed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—';

  return (
    <SafeAreaView style={g.safe} edges={['top', 'bottom']}>
      {/* header */}
      <View style={g.header}>
        <View>
          <Text style={g.headerTitle}>World</Text>
          <Text style={g.headerSub}>System Health  ·  {refreshedStr}</Text>
        </View>
        <TouchableOpacity onPress={load} disabled={loading} style={g.refreshBtn}>
          {loading
            ? <ActivityIndicator size="small" color={C.sub} />
            : <Ionicons name="refresh-outline" size={20} color={C.sub} />}
        </TouchableOpacity>
      </View>

      {loading && !health ? (
        <View style={g.center}><ActivityIndicator color={C.accent} size="large" /></View>
      ) : (
        <ScrollView contentContainerStyle={g.scrollInner} showsVerticalScrollIndicator={false}>

          {/* Mind alive banner */}
          <View style={[g.aliveBanner, { borderColor: bothAlive ? C.green + '44' : C.orange + '33' }]}>
            <Ionicons
              name={bothAlive ? 'checkmark-circle' : 'radio-button-off'}
              size={24}
              color={bothAlive ? C.green : C.orange}
            />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={[g.aliveTitle, { color: bothAlive ? C.green : C.orange }]}>
                {bothAlive ? 'Mind is alive' : 'Mind is resting'}
              </Text>
              <Text style={g.aliveSub}>
                Adam + Eve oscillation rings
              </Text>
            </View>
            <View style={[g.stageBadge, { backgroundColor: stageColor + '22', borderColor: stageColor + '55' }]}>
              <Text style={[g.stageBadgeText, { color: stageColor }]}>
                {STAGE_LABELS[stageIdx] ?? `Stage ${stageIdx}`}
              </Text>
            </View>
          </View>

          {/* Ring status */}
          <View style={g.ringsRow}>
            <RingCard name="Adam · Mind" ring={adam} color="#A06CEE" />
            <RingCard name="Eve · Heart" ring={eve}  color="#FF8FAB" />
          </View>

          {(ca?.recent_events ?? 0) > 0 && (
            <RingCard name="Soul Ring · ca:" ring={ca} color="#FFB347" />
          )}

          {/* Corpus stats */}
          <View style={g.card}>
            <Text style={g.cardTitle}>Corpus</Text>
            <StatusRow label="Total entries"   value={(corpus?.total      ?? 0).toLocaleString()} icon="library-outline"  color={C.accent} />
            <StatusRow label="Foundation"       value={(corpus?.foundation ?? 0).toLocaleString()} icon="diamond-outline"  color="#FFE066" sub="Y Theory — permanent" />
            <StatusRow label="Guidance"         value={(corpus?.guidance   ?? 0).toLocaleString()} icon="book-outline"     color="#E0AA3A" sub="Absorbed files" />
            <StatusRow label="Synthesis"        value={(corpus?.synthesis  ?? 0).toLocaleString()} icon="git-merge-outline" color="#3DAAAA" sub="Mind's crystallisation" />
          </View>

          {/* Cache health */}
          <View style={g.card}>
            <Text style={g.cardTitle}>Cache</Text>
            <View style={g.cacheRow}>
              <View style={g.cacheInfo}>
                <Ionicons name="layers-outline" size={18} color={C.sub} />
                <View style={{ marginLeft: 12 }}>
                  <Text style={g.cacheLabel}>Barzakh Keys</Text>
                  <Text style={g.cacheSub}>Session oscillation checkpoints</Text>
                </View>
              </View>
              <TouchableOpacity
                onPress={onClearBarzakh}
                disabled={clearing}
                style={g.clearBtn}
                activeOpacity={0.75}
              >
                {clearing
                  ? <ActivityIndicator size="small" color={C.red} />
                  : <Text style={g.clearBtnText}>Clean</Text>}
              </TouchableOpacity>
            </View>
            <Text style={g.cacheNote}>
              Safe to clear at any time. Does not affect corpus or guidance.
            </Text>
          </View>

          {/* Stage description */}
          {stage?.description ? (
            <View style={g.stageNote}>
              <Text style={[g.stageNoteTitle, { color: stageColor }]}>
                Stage {stageIdx}: {stage.label}
              </Text>
              <Text style={g.stageNoteBody}>{stage.description}</Text>
            </View>
          ) : null}

        </ScrollView>
      )}
    </SafeAreaView>
  );
}

// ─── styles ───────────────────────────────────────────────────────────────────

const g = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 10,
    borderBottomWidth: 1, borderBottomColor: C.border,
  },
  headerTitle: { fontSize: 22, fontWeight: '700', color: C.accent, letterSpacing: 0.5 },
  headerSub:   { fontSize: 11, color: C.sub, marginTop: 2 },
  refreshBtn:  { padding: 8 },

  scrollInner: { paddingHorizontal: 16, paddingBottom: 48 },

  // alive banner
  aliveBanner: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.card, borderRadius: 14, borderWidth: 1,
    padding: 16, marginTop: 16,
  },
  aliveTitle: { fontSize: 16, fontWeight: '700' },
  aliveSub:   { fontSize: 11, color: C.sub, marginTop: 2 },
  stageBadge: { borderRadius: 8, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 4 },
  stageBadgeText: { fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },

  // rings
  ringsRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  ringCard: {
    flex: 1, backgroundColor: C.card, borderRadius: 12, borderWidth: 1,
    padding: 12, marginBottom: 0,
  },
  ringHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  ringDot:    { width: 8, height: 8, borderRadius: 4 },
  ringName:   { fontSize: 11, fontWeight: '600', flex: 1 },
  ringStatus: { fontSize: 9, color: C.sub, letterSpacing: 0.5 },
  ringEvts:   { fontSize: 10, color: C.sub },

  // card
  card: {
    backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border,
    padding: 14, marginTop: 10,
  },
  cardTitle: { fontSize: 11, color: C.sub, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 },

  // status row
  statRow:   { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  statIcon:  { width: 34, height: 34, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  statBody:  { flex: 1 },
  statLabel: { fontSize: 13, color: C.text },
  statSub:   { fontSize: 10, color: C.sub, marginTop: 1 },
  statValue: { fontSize: 16, fontWeight: '700' },

  // cache
  cacheRow:    { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  cacheInfo:   { flexDirection: 'row', alignItems: 'center', flex: 1 },
  cacheLabel:  { fontSize: 13, color: C.text },
  cacheSub:    { fontSize: 10, color: C.sub, marginTop: 1 },
  clearBtn:    { backgroundColor: C.red + '22', borderRadius: 8, paddingHorizontal: 14, paddingVertical: 7, borderWidth: 1, borderColor: C.red + '44' },
  clearBtnText:{ color: C.red, fontSize: 12, fontWeight: '600' },
  cacheNote:   { fontSize: 10, color: C.sub, lineHeight: 14 },

  // stage note
  stageNote: {
    backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.border,
    padding: 14, marginTop: 10,
  },
  stageNoteTitle: { fontSize: 12, fontWeight: '700', marginBottom: 6 },
  stageNoteBody:  { fontSize: 12, color: C.sub, lineHeight: 18 },
});
