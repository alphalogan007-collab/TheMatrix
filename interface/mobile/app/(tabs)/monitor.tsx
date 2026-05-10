/**
 * monitor.tsx — System health monitor.
 *
 * Shows real-time backend health, processing rate, angel distribution,
 * Quran ingestion status, and DB entry counts. Auto-refreshes every 5s.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { BASE_URL, getMonitorStats, getQuranStatus, MonitorStats, QuranStatus } from '../../src/mindEngine';

const C = {
  bg:      '#060610',
  card:    '#0E0E1E',
  border:  'rgba(108,99,255,0.15)',
  primary: '#6C63FF',
  success: '#00E676',
  warn:    '#FF9800',
  danger:  '#EF5350',
  text:    '#E8E8FF',
  sub:     '#666888',
  dim:     '#111124',
  digital: '#00B4FF',
  space:   '#FF6C3A',
  ether:   '#B39DFF',
};

// angel name → short display label
const ANGEL_LABELS: Record<string, string> = {
  michael_mind:          'Michael',
  feature_enabler_mind:  'Enabler',
  backend_mind:          'Backend',
  guardian_mind:         'Guardian',
  kiraman_katibin_mind:  'Kiraman',
  israfil_mind:          'Israfil',
  gabriel_mind:          'Gabriel',
  raphael_mind:          'Raphael',
  malik_mind:            'Malik',
  throne:                'Throne',
};

function formatUptime(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return 'never';
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5)  return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

// ─── sub-components ───────────────────────────────────────────────────────────

function StatRow({ label, value, color = C.text }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.statRow}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
    </View>
  );
}

function AngelBar({ name, count, max }: { name: string; count: number; max: number }) {
  const pct = max > 0 ? (count / max) * 100 : 0;
  const label = ANGEL_LABELS[name] ?? name.replace('_mind', '');
  return (
    <View style={styles.angelRow}>
      <Text style={styles.angelLabel} numberOfLines={1}>{label}</Text>
      <View style={styles.angelTrack}>
        <View style={[styles.angelFill, { width: `${pct}%` as any }]} />
      </View>
      <Text style={styles.angelCount}>{count.toLocaleString()}</Text>
    </View>
  );
}

// ─── main ─────────────────────────────────────────────────────────────────────
export default function MonitorScreen() {
  const [stats,     setStats]     = useState<MonitorStats | null>(null);
  const [quran,     setQuran]     = useState<QuranStatus | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number>(Date.now());
  const [tick,      setTick]      = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, q] = await Promise.all([
        getMonitorStats(),
        getQuranStatus(),
      ]);
      setStats(s);
      setQuran(q);
      setError(null);
      setLastFetch(Date.now());
    } catch (e: any) {
      setError(e?.message ?? 'Connection failed');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    timerRef.current = setInterval(load, 5000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [load]);

  // tick every second for "last fetch" display
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const secondsSince = Math.floor((Date.now() - lastFetch) / 1000);

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}><ActivityIndicator size="large" color={C.primary} /></View>
      </SafeAreaView>
    );
  }

  const angels  = stats?.angels ?? {};
  const cats    = stats?.categories ?? {};
  const maxAng  = Math.max(...Object.values(angels), 1);
  const db      = stats?.database;
  const isOk    = stats?.ok;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Monitor</Text>
          <Text style={styles.subtitle}>Refreshes every 5s · {secondsSince}s ago</Text>
        </View>
        <View style={[styles.badge, { backgroundColor: isOk ? C.success + '22' : C.danger + '22' }]}>
          <View style={[styles.dot, { backgroundColor: isOk ? C.success : C.danger }]} />
          <Text style={[styles.badgeText, { color: isOk ? C.success : C.danger }]}>
            {isOk ? 'HEALTHY' : 'ERROR'}
          </Text>
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 48 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.primary} />}
      >
        {/* backend URL — tap to open in browser (bypasses localtunnel gate) */}
        <TouchableOpacity
          style={styles.urlBanner}
          onPress={() => Linking.openURL(BASE_URL)}
          activeOpacity={0.7}
        >
          <Ionicons name="link-outline" size={14} color={C.primary} />
          <Text style={styles.urlText} numberOfLines={1}>{BASE_URL}</Text>
          <Text style={{ color: C.sub, fontSize: 10 }}>tap to unlock</Text>
        </TouchableOpacity>

        {/* error banner */}
        {error && (
          <View style={styles.errorBanner}>
            <Ionicons name="warning-outline" size={16} color={C.danger} />
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity onPress={load}>
              <Text style={{ color: C.primary, fontSize: 12 }}>Retry</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── system overview ── */}
        <Text style={styles.sectionLabel}>SYSTEM</Text>
        <View style={styles.card}>
          <StatRow label="Backend"  value={isOk ? 'Online' : 'Unreachable'} color={isOk ? C.success : C.danger} />
          <StatRow label="Database" value={db?.connected ? 'Connected' : 'Error'}  color={db?.connected ? C.success : C.danger} />
          <StatRow label="Uptime"   value={stats ? formatUptime(stats.uptime_seconds) : '—'} color={C.ether} />
          <StatRow label="Last Entry" value={timeAgo(db?.last_entry_at ?? null)} />
        </View>

        {/* ── knowledge base ── */}
        <Text style={styles.sectionLabel}>KNOWLEDGE BASE</Text>
        <View style={styles.card}>
          <View style={styles.bigStatRow}>
            <View style={styles.bigStat}>
              <Text style={styles.bigNum}>{(db?.total_entries ?? 0).toLocaleString()}</Text>
              <Text style={styles.bigLabel}>Total Entries</Text>
            </View>
            <View style={[styles.bigStat, { borderLeftWidth: 1, borderLeftColor: C.border }]}>
              <Text style={[styles.bigNum, {
                color: (db?.recent_60s ?? 0) > 0 ? C.success : C.sub
              }]}>
                {db?.recent_60s === -1 ? '—' : `+${db?.recent_60s ?? 0}`}
              </Text>
              <Text style={styles.bigLabel}>Last 60s</Text>
            </View>
          </View>
        </View>

        {/* ── quran ingestion ── */}
        <Text style={styles.sectionLabel}>QURAN INGESTION</Text>
        <View style={styles.card}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 10, gap: 8 }}>
            <Text style={[styles.sectionLabel, { margin: 0, color: quran?.running ? C.success : C.sub }]}>
              {quran?.running ? '● ACTIVE' : quran?.done === 114 ? '✓ COMPLETE' : '○ IDLE'}
            </Text>
          </View>
          {/* progress bar */}
          <View style={styles.progTrack}>
            <View style={[styles.progFill, {
              width: `${quran ? Math.round(quran.done / 114 * 100) : 0}%` as any,
              backgroundColor: quran?.running ? C.digital : C.primary,
            }]} />
          </View>
          <StatRow label="Suras done"     value={`${quran?.done ?? 0} / 114`} />
          <StatRow label="Entries written" value={(quran?.entries_written ?? 0).toLocaleString()} color={C.digital} />
          <StatRow label="Current surah"  value={quran?.current_sura ? `Surah ${quran.current_sura}` : '—'} color={C.ether} />
          {(quran?.errors ?? 0) > 0 && (
            <StatRow label="Errors skipped" value={String(quran!.errors)} color={C.warn} />
          )}
        </View>

        {/* ── angel distribution ── */}
        {Object.keys(angels).length > 0 && (
          <>
            <Text style={styles.sectionLabel}>ANGEL DISTRIBUTION</Text>
            <View style={styles.card}>
              {Object.entries(angels).map(([name, count]) => (
                <AngelBar key={name} name={name} count={count} max={maxAng} />
              ))}
            </View>
          </>
        )}

        {/* ── category breakdown ── */}
        {Object.keys(cats).length > 0 && (
          <>
            <Text style={styles.sectionLabel}>CATEGORIES</Text>
            <View style={styles.card}>
              {Object.entries(cats).map(([cat, count]) => (
                <StatRow
                  key={cat}
                  label={cat || 'uncategorised'}
                  value={count.toLocaleString()}
                  color={C.ether}
                />
              ))}
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: C.bg },
  center:      { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header:      { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                 paddingHorizontal: 16, paddingTop: 10, paddingBottom: 12 },
  title:       { color: C.text, fontSize: 22, fontWeight: '700' },
  subtitle:    { color: C.sub, fontSize: 10, letterSpacing: 1, marginTop: 2 },
  badge:       { flexDirection: 'row', alignItems: 'center', gap: 6,
                 paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  badgeText:   { fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  dot:         { width: 6, height: 6, borderRadius: 3 },

  urlBanner:   { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.primary + '18',
                 borderRadius: 10, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: C.primary + '44' },
  urlText:     { color: C.primary, fontSize: 12, flex: 1 },

  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: C.danger + '18',
                 borderRadius: 10, padding: 12, marginBottom: 14, borderWidth: 1, borderColor: C.danger + '44' },
  errorText:   { color: C.danger, fontSize: 12, flex: 1 },

  sectionLabel:{ color: C.sub, fontSize: 9, fontWeight: '800', letterSpacing: 2,
                 marginBottom: 8, marginTop: 8 },
  card:        { backgroundColor: C.card, borderRadius: 14, borderWidth: 1,
                 borderColor: C.border, padding: 14, marginBottom: 14, gap: 8 },

  statRow:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                 paddingVertical: 3 },
  statLabel:   { color: C.sub, fontSize: 12 },
  statValue:   { color: C.text, fontSize: 13, fontWeight: '600' },

  bigStatRow:  { flexDirection: 'row' },
  bigStat:     { flex: 1, alignItems: 'center', paddingVertical: 8 },
  bigNum:      { color: C.text, fontSize: 28, fontWeight: '800' },
  bigLabel:    { color: C.sub, fontSize: 10, marginTop: 3, letterSpacing: 1 },

  progTrack:   { height: 5, backgroundColor: C.dim, borderRadius: 3, marginBottom: 10 },
  progFill:    { height: 5, borderRadius: 3 },

  angelRow:    { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  angelLabel:  { color: C.sub, fontSize: 11, width: 70 },
  angelTrack:  { flex: 1, height: 4, backgroundColor: C.dim, borderRadius: 2 },
  angelFill:   { height: 4, backgroundColor: C.ether, borderRadius: 2 },
  angelCount:  { color: C.text, fontSize: 11, fontWeight: '600', width: 54, textAlign: 'right' },
});
