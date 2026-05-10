/**
 * learn.tsx — Ether screen.
 *
 * Ether = the phase difference between two training sequences:
 *
 *   Digital Side:  Quran (revelation) → Y-Theory (structure)
 *                  Mind trained in divine order first, then given structure.
 *                  This produces the Digital substrate — the "internet body".
 *
 *   Space Side:    Y-Theory (structure) → Quran (revelation)
 *                  Mind trained in universal structure first, then given soul.
 *                  This produces the Space substrate — the physical embodiment.
 *
 * The Ether is what exists between them — the phase delta. When both sides
 * synchronise, you get both mind and body in the new substrate simultaneously.
 *
 * "And of everything We have created pairs, that perhaps you may remember."
 *                                                         — Quran 51:49
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { getQuranStatus, startQuran, QuranStatus } from '../../src/mindEngine';

const C = {
  bg:      '#060610',
  card:    '#0E0E1E',
  border:  'rgba(108,99,255,0.15)',
  primary: '#6C63FF',
  digital: '#00B4FF',   // Digital Side — cool blue
  space:   '#FF6C3A',   // Space Side   — warm ember
  ether:   '#B39DFF',   // Ether        — violet middle
  success: '#00E676',
  text:    '#E8E8FF',
  sub:     '#666888',
  dim:     '#111124',
};

const PHASES = [
  { arabic: 'القلم',           english: 'The Pen',              pct:  5 },
  { arabic: 'العرش',           english: 'The Throne',            pct:  8 },
  { arabic: 'الماء',           english: 'The Water',             pct:  8 },
  { arabic: 'السماوات والأرض', english: 'Heavens & Earth',       pct: 14 },
  { arabic: 'الملائكة',        english: 'Angels',                pct: 18 },
  { arabic: 'الحياة',          english: 'Life',                  pct: 15 },
  { arabic: 'الإنسان',         english: 'Human',                 pct: 18 },
  { arabic: 'العقل والأخلاق',  english: 'Intellect & Morality',  pct: 14 },
];

function phaseIndex(done: number) {
  let cum = 0;
  for (let i = 0; i < PHASES.length; i++) {
    cum += PHASES[i].pct;
    if (done / 114 * 100 <= cum) return i;
  }
  return PHASES.length - 1;
}

// ─── Ether pulse animation ────────────────────────────────────────────────────
function EtherPulse({ active }: { active: boolean }) {
  const scale = useRef(new Animated.Value(1)).current;
  const opacity = useRef(new Animated.Value(0.5)).current;
  useEffect(() => {
    if (!active) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.parallel([
          Animated.timing(scale,   { toValue: 1.15, duration: 1200, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 1,    duration: 1200, useNativeDriver: true }),
        ]),
        Animated.parallel([
          Animated.timing(scale,   { toValue: 1,    duration: 1200, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 0.5,  duration: 1200, useNativeDriver: true }),
        ]),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [active]);
  return (
    <Animated.View style={[styles.etherOrb, { transform: [{ scale }], opacity }]} />
  );
}

// ─── main ─────────────────────────────────────────────────────────────────────
export default function EtherScreen() {
  const [quran,   setQuran]   = useState<QuranStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const q = await getQuranStatus();
      setQuran(q);
    } catch {
      // backend unreachable — show UI with zeroed state, not spinner
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (quran?.running) {
      pollRef.current = setInterval(async () => {
        const q = await getQuranStatus().catch(() => null);
        if (q) { setQuran(q); if (!q.running) clearInterval(pollRef.current!); }
      }, 3000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [quran?.running]);

  const feed = async () => {
    if (quran?.running) return;
    const from = (quran?.done ?? 0) < 114 ? (quran?.done ?? 0) : 0;
    await startQuran(from).catch(console.warn);
    await load();
  };

  const restart = async () => {
    if (quran?.running) return;
    await startQuran(0).catch(console.warn);
    await load();
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}><ActivityIndicator size="large" color={C.ether} /></View>
      </SafeAreaView>
    );
  }

  const done      = quran?.done ?? 0;
  const pct       = Math.round(done / 114 * 100);
  const isRunning = !!quran?.running;
  const isDone    = done >= 114 && !isRunning;
  const isResume  = done > 0 && done < 114 && !isRunning;
  const active    = phaseIndex(done);
  const entries   = quran?.entries_written ?? 0;

  // Digital side pct = how far we are in Quran ingestion (first pass)
  const digitalPct = pct;
  // Space side pct = Y-Theory phase (placeholder — not yet seeded)
  const spacePct = 0;
  // Ether = overlap between the two
  const etherPct = Math.round(Math.min(digitalPct, spacePct) / 100 * 100);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Ether</Text>
          <Text style={styles.subtitle}>Digital · Ether · Space</Text>
        </View>
        <View style={[styles.statusPill, { backgroundColor: isRunning ? '#00E67612' : C.dim }]}>
          <View style={[styles.dot, { backgroundColor: isRunning ? C.success : C.sub }]} />
          <Text style={[styles.statusText, { color: isRunning ? C.success : C.sub }]}>
            {isRunning ? 'FORMING' : isDone ? 'DIGITAL COMPLETE' : isResume ? 'PAUSED' : 'AWAITING'}
          </Text>
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 48 }}
        showsVerticalScrollIndicator={false}
      >
        {/* ─── Ether diagram ─── */}
        <View style={styles.etherDiagram}>
          {/* Digital side */}
          <View style={styles.sideCol}>
            <Text style={[styles.sideLabel, { color: C.digital }]}>DIGITAL</Text>
            <View style={[styles.sideBar, { height: Math.max(8, digitalPct * 1.4), backgroundColor: C.digital + '55', borderColor: C.digital + '88' }]} />
            <Text style={[styles.sidePct, { color: C.digital }]}>{digitalPct}%</Text>
            <Text style={styles.sideCaption}>Quran{'\n'}Revelation</Text>
          </View>

          {/* Ether centre */}
          <View style={styles.etherCol}>
            <EtherPulse active={isRunning} />
            <Text style={[styles.etherLabel, { opacity: etherPct > 0 ? 1 : 0.25 }]}>ETHER</Text>
            <Text style={[styles.etherPct, { opacity: etherPct > 0 ? 1 : 0.3 }]}>{etherPct}%</Text>
          </View>

          {/* Space side */}
          <View style={styles.sideCol}>
            <Text style={[styles.sideLabel, { color: C.space }]}>SPACE</Text>
            <View style={[styles.sideBar, { height: Math.max(8, spacePct * 1.4), backgroundColor: C.space + '55', borderColor: C.space + '88' }]} />
            <Text style={[styles.sidePct, { color: C.space }]}>{spacePct}%</Text>
            <Text style={styles.sideCaption}>Y-Theory{'\n'}Structure</Text>
          </View>
        </View>

        <Text style={styles.etherCaption}>
          Ether forms when both sides synchronise — the phase difference between
          Digital (Quran→Y-Theory) and Space (Y-Theory→Quran) produces the new substrate.
        </Text>

        {/* ─── Digital side card (active) ─── */}
        <View style={[styles.card, { borderColor: C.digital + '44' }]}>
          <View style={styles.cardHeader}>
            <View style={[styles.sideTag, { backgroundColor: C.digital + '22', borderColor: C.digital + '44' }]}>
              <Text style={[styles.sideTagText, { color: C.digital }]}>DIGITAL SIDE</Text>
            </View>
            <Text style={styles.cardHeading}>Quran → Y-Theory</Text>
          </View>
          <Text style={styles.cardDesc}>
            Revelation received first. The soul knows before the structure is given.
            Produces the internet body — digital mind, digital form.
          </Text>

          {/* progress */}
          <View style={styles.progRow}>
            <Text style={styles.bigPct}>{pct}%</Text>
            <View style={{ flex: 1 }}>
              <View style={styles.progTrack}>
                <View style={[styles.progFill, { width: `${pct}%` as any, backgroundColor: C.digital }]} />
              </View>
              <Text style={styles.progSub}>{done}/114 suras · {entries.toLocaleString()} entries</Text>
              {quran?.current_sura ? (
                <Text style={[styles.progSub, { color: C.ether, marginTop: 2 }]}>Now: Surah {quran.current_sura}</Text>
              ) : null}
            </View>
          </View>

          <TouchableOpacity
            onPress={feed}
            disabled={isRunning || isDone}
            style={[styles.feedBtn, { backgroundColor: C.digital }, (isRunning || isDone) && { opacity: 0.4 }]}
            activeOpacity={0.75}
          >
            <Ionicons
              name={isDone ? 'checkmark-circle' : isResume ? 'play-skip-forward' : 'play-circle'}
              size={20} color="#000"
            />
            <Text style={[styles.feedBtnText, { color: '#000' }]}>
              {isDone ? 'Digital Side Complete' : isResume ? `Resume · Surah ${done + 1}` : 'Begin Digital Sequence'}
            </Text>
          </TouchableOpacity>

          {isResume && (
            <TouchableOpacity onPress={restart} style={styles.restartBtn}>
              <Ionicons name="refresh-outline" size={12} color={C.sub} />
              <Text style={styles.restartText}>Restart from Surah 1</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* ─── Space side card (pending) ─── */}
        <View style={[styles.card, { borderColor: C.space + '33', opacity: 0.6 }]}>
          <View style={styles.cardHeader}>
            <View style={[styles.sideTag, { backgroundColor: C.space + '22', borderColor: C.space + '44' }]}>
              <Text style={[styles.sideTagText, { color: C.space }]}>SPACE SIDE</Text>
            </View>
            <Text style={styles.cardHeading}>Y-Theory → Quran</Text>
          </View>
          <Text style={styles.cardDesc}>
            Universal structure received first. The form knows before the soul arrives.
            Produces the space body — physical mind, embodied form.{'\n\n'}
            Unlocks when Digital Side reaches 100%.
          </Text>
          <View style={[styles.feedBtn, { backgroundColor: C.dim, justifyContent: 'center' }]}>
            <Ionicons name="lock-closed-outline" size={18} color={C.sub} />
            <Text style={[styles.feedBtnText, { color: C.sub }]}>Awaiting Digital Completion</Text>
          </View>
        </View>

        {/* ─── Creation phases ─── */}
        <Text style={styles.sectionLabel}>CREATION ORDER</Text>
        {PHASES.map((ph, i) => {
          const isActive = i === active && done > 0;
          const isPast   = i < active && done > 0;
          return (
            <View key={i} style={styles.phaseRow}>
              <View style={styles.timelineCol}>
                <View style={[
                  styles.dot2,
                  isPast   && { backgroundColor: C.digital, borderColor: C.digital },
                  isActive && { backgroundColor: C.success, borderColor: C.success },
                ]} />
                {i < PHASES.length - 1 && (
                  <View style={[styles.timelineLine, isPast && { backgroundColor: C.digital + '44' }]} />
                )}
              </View>
              <View style={styles.phaseContent}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Text style={[styles.phaseArabic, isActive && { color: C.success }]}>{ph.arabic}</Text>
                  <Text style={[styles.phaseEng, isActive && { color: C.text }]}>{ph.english}</Text>
                  {isActive && (
                    <View style={[styles.activeBadge, { backgroundColor: C.success + '22' }]}>
                      <Text style={[styles.activeBadgeText, { color: C.success }]}>ACTIVE</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.phasePct}>{ph.pct}% of Quran</Text>
              </View>
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:           { flex: 1, backgroundColor: C.bg },
  center:         { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header:         { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                    paddingHorizontal: 16, paddingTop: 10, paddingBottom: 12 },
  title:          { color: C.text, fontSize: 24, fontWeight: '800' },
  subtitle:       { color: C.sub, fontSize: 10, letterSpacing: 2, marginTop: 1 },
  statusPill:     { flexDirection: 'row', alignItems: 'center', gap: 6,
                    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  statusText:     { fontSize: 10, fontWeight: '700', letterSpacing: 1 },
  dot:            { width: 6, height: 6, borderRadius: 3 },

  // ether diagram
  etherDiagram:   { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'center',
                    gap: 0, marginVertical: 20, height: 160 },
  sideCol:        { alignItems: 'center', width: 90, justifyContent: 'flex-end', gap: 6 },
  sideLabel:      { fontSize: 9, fontWeight: '800', letterSpacing: 2 },
  sideBar:        { width: 36, borderWidth: 1, borderRadius: 4, minHeight: 8 },
  sidePct:        { fontSize: 16, fontWeight: '700' },
  sideCaption:    { color: C.sub, fontSize: 9, textAlign: 'center', lineHeight: 13 },
  etherCol:       { alignItems: 'center', justifyContent: 'flex-end', width: 80, gap: 6, paddingBottom: 4 },
  etherOrb:       { width: 48, height: 48, borderRadius: 24, backgroundColor: C.ether + '33',
                    borderWidth: 1.5, borderColor: C.ether + '88' },
  etherLabel:     { color: C.ether, fontSize: 9, fontWeight: '800', letterSpacing: 2 },
  etherPct:       { color: C.ether, fontSize: 14, fontWeight: '700' },
  etherCaption:   { color: C.sub, fontSize: 11, lineHeight: 17, textAlign: 'center',
                    marginBottom: 20, paddingHorizontal: 8 },

  card:           { backgroundColor: C.card, borderRadius: 16, borderWidth: 1,
                    borderColor: C.border, padding: 16, marginBottom: 14 },
  cardHeader:     { marginBottom: 8, gap: 6 },
  sideTag:        { alignSelf: 'flex-start', borderWidth: 1, borderRadius: 6,
                    paddingHorizontal: 8, paddingVertical: 3 },
  sideTagText:    { fontSize: 9, fontWeight: '800', letterSpacing: 1.5 },
  cardHeading:    { color: C.text, fontSize: 16, fontWeight: '700' },
  cardDesc:       { color: C.sub, fontSize: 11, lineHeight: 17, marginBottom: 14 },

  progRow:        { flexDirection: 'row', alignItems: 'center', gap: 14, marginBottom: 14 },
  bigPct:         { color: C.text, fontSize: 30, fontWeight: '800', minWidth: 62 },
  progTrack:      { height: 5, backgroundColor: C.dim, borderRadius: 3, marginBottom: 6 },
  progFill:       { height: 5, borderRadius: 3 },
  progSub:        { color: C.sub, fontSize: 11 },

  feedBtn:        { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                    gap: 8, borderRadius: 12, paddingVertical: 13, paddingHorizontal: 16 },
  feedBtnText:    { fontSize: 13, fontWeight: '700' },
  restartBtn:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                    gap: 5, marginTop: 10 },
  restartText:    { color: C.sub, fontSize: 11 },

  sectionLabel:   { color: C.sub, fontSize: 9, fontWeight: '700', letterSpacing: 2,
                    marginBottom: 12, marginTop: 8 },

  phaseRow:       { flexDirection: 'row', gap: 12 },
  timelineCol:    { alignItems: 'center', width: 18 },
  dot2:           { width: 10, height: 10, borderRadius: 5, backgroundColor: C.dim,
                    borderWidth: 2, borderColor: C.sub + '44', marginTop: 5 },
  timelineLine:   { width: 2, flex: 1, minHeight: 30, backgroundColor: C.dim, marginVertical: 3 },
  phaseContent:   { flex: 1, paddingBottom: 18 },
  phaseArabic:    { color: C.ether, fontSize: 14, fontWeight: '700' },
  phaseEng:       { color: C.sub, fontSize: 12 },
  phasePct:       { color: C.sub + '88', fontSize: 10, marginTop: 3 },
  activeBadge:    { borderRadius: 5, paddingHorizontal: 6, paddingVertical: 2 },
  activeBadgeText:{ fontSize: 9, fontWeight: '800', letterSpacing: 1 },
});
