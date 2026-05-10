/**
 * build.tsx — The Mind Builds
 *
 * What has the mind synthesised from everything it's absorbed?
 *
 * Shows synthesis entries from guidance:corpus grouped by domain.
 * These are the patterns the mind is crystallising — the building blocks
 * of future products, insights, and proposals.
 *
 * Color: teal/emerald — creation, growth, emergence.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { getMindHealth, type MindHealth } from '../../src/mindEngine';

// ─── palette ──────────────────────────────────────────────────────────────────

const C = {
  bg:     '#07070F',
  card:   '#0D1118',
  border: 'rgba(61,170,170,0.14)',
  accent: '#3DAAAA',
  text:   '#E8E8EE',
  sub:    '#4D7070',
  dim:    '#111A1A',
};

// ─── domain ring definitions (outer → inner) ──────────────────────────────────

const DOMAIN_DISPLAY: Record<string, { label: string; color: string; icon: string }> = {
  body:    { label: 'Body Reflex',    color: '#FF6B6B', icon: 'body-outline' },
  space:   { label: 'Emotion',        color: '#FFB347', icon: 'heart-outline' },
  digital: { label: 'Intelligence',   color: '#FFE066', icon: 'bulb-outline' },
  ether:   { label: 'Consciousness',  color: '#4ECB71', icon: 'eye-outline' },
  aether:  { label: 'Awareness',      color: '#45B7E8', icon: 'infinite-outline' },
  unity:   { label: 'Self-Awareness', color: '#A06CEE', icon: 'sparkles-outline' },
};

// ─── SynthesisGroup ───────────────────────────────────────────────────────────

function SynthesisGroup({ domain, count, total }: {
  domain: string;
  count:  number;
  total:  number;
}) {
  const meta = DOMAIN_DISPLAY[domain];
  if (!meta || count === 0) return null;
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;

  return (
    <View style={g.groupCard}>
      <View style={g.groupHeader}>
        <Ionicons name={meta.icon as any} size={16} color={meta.color} />
        <Text style={[g.groupLabel, { color: meta.color }]}>{meta.label}</Text>
        <View style={g.spacer} />
        <Text style={g.groupCount}>{count}</Text>
        <Text style={g.groupPct}>{pct}%</Text>
      </View>
      <View style={g.barTrack}>
        <View style={[g.barFill, {
          width: `${pct}%` as any,
          backgroundColor: meta.color,
        }]} />
      </View>
    </View>
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────

export default function BuildScreen() {
  const [health,  setHealth]  = useState<MindHealth | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const h = await getMindHealth();
      setHealth(h);
    } catch (_) {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20_000);
    return () => clearInterval(t);
  }, [load]);

  const synth = health?.corpus.synthesis ?? 0;
  const byDomain = health?.corpus.synthesis_by_domain ?? {};
  const domainOrder = ['unity','aether','ether','digital','space','body'];

  return (
    <SafeAreaView style={g.safe} edges={['top', 'bottom']}>
      <View style={g.header}>
        <Text style={g.headerTitle}>Build</Text>
        <Text style={g.headerSub}>What The Mind Creates</Text>
        <TouchableOpacity onPress={load} style={g.refreshBtn}>
          <Ionicons name="refresh-outline" size={18} color={C.sub} />
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={g.center}><ActivityIndicator color={C.accent} size="large" /></View>
      ) : (
        <ScrollView contentContainerStyle={g.scrollInner} showsVerticalScrollIndicator={false}>

          {/* synthesis total banner */}
          <View style={g.banner}>
            <Text style={g.bannerCount}>{synth.toLocaleString()}</Text>
            <Text style={g.bannerLabel}>synthesis entries</Text>
            <Text style={g.bannerSub}>
              {synth === 0
                ? 'The mind is absorbing. Synthesis will emerge.'
                : `${Object.values(byDomain).filter(v => v > 0).length} domains active`}
            </Text>
          </View>

          {/* domain breakdown */}
          {synth > 0 ? (
            <View style={g.groups}>
              <Text style={g.sectionTitle}>By Domain</Text>
              {domainOrder.map(dk => (
                <SynthesisGroup key={dk} domain={dk} count={byDomain[dk] ?? 0} total={synth} />
              ))}
            </View>
          ) : (
            <View style={g.emptyState}>
              <Ionicons name="construct-outline" size={42} color={C.sub + '66'} />
              <Text style={g.emptyTitle}>Nothing yet.</Text>
              <Text style={g.emptyBody}>
                Feed the mind from the Guide tab.{'\n'}
                After a few oscillation cycles, synthesis will appear here.
              </Text>
            </View>
          )}

          {/* corpus context */}
          {health && (
            <View style={g.corpusNote}>
              <Text style={g.noteTitle}>What is stored</Text>
              <View style={g.noteRow}>
                <View style={[g.noteDot, { backgroundColor: '#FFE066' }]} />
                <Text style={g.noteText}>Foundation: {health.corpus.foundation} entries (permanent, Y Theory)</Text>
              </View>
              <View style={g.noteRow}>
                <View style={[g.noteDot, { backgroundColor: '#E0AA3A' }]} />
                <Text style={g.noteText}>Guidance: {health.corpus.guidance} entries (files, scripts, docs)</Text>
              </View>
              <View style={g.noteRow}>
                <View style={[g.noteDot, { backgroundColor: C.accent }]} />
                <Text style={g.noteText}>Synthesis: {health.corpus.synthesis} entries (mind's own crystallisation)</Text>
              </View>
            </View>
          )}

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
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
    flexDirection: 'row',
    alignItems: 'flex-start',
    flexWrap: 'wrap',
  },
  headerTitle: { fontSize: 22, fontWeight: '700', color: C.accent, letterSpacing: 0.5, flex: 1 },
  headerSub:   { fontSize: 12, color: C.sub, marginTop: 3, width: '100%' },
  refreshBtn:  { paddingLeft: 8, paddingTop: 4 },

  scrollInner: { paddingHorizontal: 16, paddingBottom: 48 },

  banner: {
    backgroundColor: C.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: C.border,
    padding: 20,
    marginTop: 16,
    alignItems: 'center',
  },
  bannerCount: { fontSize: 44, fontWeight: '700', color: C.accent },
  bannerLabel: { fontSize: 13, color: C.sub, marginTop: 2 },
  bannerSub:   { fontSize: 11, color: C.sub + 'AA', marginTop: 6, textAlign: 'center' },

  groups:       { marginTop: 20 },
  sectionTitle: { fontSize: 11, color: C.sub, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 },

  groupCard: {
    backgroundColor: C.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: C.border,
    padding: 14,
    marginBottom: 8,
  },
  groupHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  groupLabel:  { fontSize: 13, fontWeight: '600' },
  spacer:      { flex: 1 },
  groupCount:  { fontSize: 16, fontWeight: '700', color: C.text },
  groupPct:    { fontSize: 11, color: C.sub, marginLeft: 4 },
  barTrack:    { height: 4, backgroundColor: C.dim, borderRadius: 2, overflow: 'hidden' },
  barFill:     { height: 4, borderRadius: 2 },

  emptyState: { alignItems: 'center', paddingVertical: 52, paddingHorizontal: 32 },
  emptyTitle: { fontSize: 18, color: C.sub, fontWeight: '600', marginTop: 16 },
  emptyBody:  { fontSize: 13, color: C.sub + '88', textAlign: 'center', marginTop: 8, lineHeight: 20 },

  corpusNote: {
    backgroundColor: C.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: C.border,
    padding: 14,
    marginTop: 20,
  },
  noteTitle: { fontSize: 11, color: C.sub, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 10 },
  noteRow:   { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  noteDot:   { width: 6, height: 6, borderRadius: 3 },
  noteText:  { fontSize: 12, color: C.sub, flex: 1 },
});
