/**
 * my-mind.tsx — Universal Mind Interface
 *
 * Chat-first command center. Ask anything, give commands to anyone.
 * loop_depth badge on each mind response shows network convergence depth.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { apiClient } from '../../src/services/apiClient';
import { streamConversationMessage, type LoopStep } from '../../src/services/mindaiApi';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserMindName {
  mind_name: string;
}

interface ChatMsg {
  id: string;
  role: 'user' | 'mind';
  content: string;
  loop_depth?: number;
  mind_name?: string;   // which mind in the ring spoke this
  step?: number;        // ring position (1, 2, 3…)
  total?: number;       // total minds in ring
  ts: number;
}

// ---------------------------------------------------------------------------
// DepthBadge
// ---------------------------------------------------------------------------

function DepthBadge({ depth }: { depth: number }) {
  const color = depth === 1 ? '#33AA55' : depth === 2 ? '#FFB055' : '#9B55FF';
  const label = depth === 1 ? 'instant' : depth === 2 ? 'deep' : 'boundary';
  return (
    <View style={[db.wrap, { borderColor: color + '55' }]}>
      <Text style={[db.text, { color }]}>◎ {label}</Text>
    </View>
  );
}

const db = StyleSheet.create({
  wrap: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginTop: 4,
    marginLeft: 36,
  },
  text: {
    fontSize: 9,
    letterSpacing: 1,
    fontFamily: 'monospace',
    textTransform: 'uppercase',
  },
});

// ---------------------------------------------------------------------------
// MindOrb
// ---------------------------------------------------------------------------

function MindOrb({ size = 40, speaking = false }: { size?: number; speaking?: boolean }) {
  const pulse = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: speaking ? 1.2 : 1.07,
          duration: speaking ? 300 : 2000,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: speaking ? 300 : 2000,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ])
    );
    anim.start();
    return () => anim.stop();
  }, [speaking]);

  return (
    <Animated.View
      style={[
        orb.base,
        { width: size, height: size, borderRadius: size / 2, transform: [{ scale: pulse }] },
      ]}
    >
      <Text style={{ fontSize: size * 0.42 }}>✦</Text>
    </Animated.View>
  );
}

const orb = StyleSheet.create({
  base: {
    backgroundColor: '#6C63FF',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#6C63FF',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.9,
    shadowRadius: 12,
    elevation: 10,
  },
});

// ---------------------------------------------------------------------------
// Chat Bubble
// ---------------------------------------------------------------------------

function Bubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === 'user';
  const sourceName = msg.mind_name
    ? msg.mind_name.replace(/_mind$/, '').replace(/_/g, ' ')
    : null;
  return (
    <View style={{ marginBottom: 2 }}>
      {!isUser && sourceName && msg.total && msg.total > 1 && (
        <Text style={bbl.sourceLabel}>
          {sourceName} · {msg.step}/{msg.total}
        </Text>
      )}
      <View style={[bbl.row, isUser && bbl.rowUser]}>
        {!isUser && <MindOrb size={26} />}
        <View style={[bbl.bubble, isUser ? bbl.bubbleUser : bbl.bubbleMind]}>
          <Text style={[bbl.text, isUser && bbl.textUser]}>{msg.content}</Text>
        </View>
      </View>
      {!isUser && msg.loop_depth != null && <DepthBadge depth={msg.loop_depth} />}
    </View>
  );
}

const bbl = StyleSheet.create({
  row:        { flexDirection: 'row', alignItems: 'flex-end', gap: 8, paddingHorizontal: 14, marginBottom: 2 },
  rowUser:    { justifyContent: 'flex-end' },
  bubble:     { maxWidth: '78%', borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
  bubbleMind: { backgroundColor: 'rgba(108,99,255,0.14)', borderColor: 'rgba(108,99,255,0.25)', borderWidth: 1, borderBottomLeftRadius: 4 },
  bubbleUser: { backgroundColor: '#6C63FF', borderBottomRightRadius: 4 },
  text:       { color: '#D0D0F0', fontSize: 15, lineHeight: 22 },
  textUser:   { color: '#fff' },
  sourceLabel:{ fontSize: 10, color: 'rgba(108,99,255,0.7)', marginLeft: 50, marginBottom: 2, fontFamily: 'monospace', letterSpacing: 0.5 },
});

// ---------------------------------------------------------------------------
// Quick command chips
// ---------------------------------------------------------------------------

const QUICK_COMMANDS = [
  'What do you know about me?',
  'What am I missing?',
  'What should I focus on?',
  'Tell me my open questions',
];

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export default function MyMindScreen() {
  const [mindName, setMindName] = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput]       = useState('');
  const [sending, setSending]   = useState(false);
  const [avgDepth, setAvgDepth] = useState<number>(1);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    apiClient.get<UserMindName>('/users/me/mind')
      .then(r => { setMindName(r.data.mind_name); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || sending || !mindName) return;
    setInput('');
    setSending(true);

    const userMsg: ChatMsg = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text.trim(),
      ts: Date.now(),
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      // Build history from current messages for context
      const history = messages.slice(-8).map(m => ({
        role: m.role === 'user' ? 'founder' : 'mind',
        content: m.content,
      }));

      await streamConversationMessage(mindName, text.trim(), (step: LoopStep) => {
        if (step.error) {
          setMessages(prev => [
            ...prev,
            { id: `err-${Date.now()}`, role: 'mind', content: `Error: ${step.error}`, ts: Date.now() },
          ]);
          return;
        }
        setAvgDepth(prev => Math.round((prev + step.loop_depth) / 2));
        setMessages(prev => [
          ...prev,
          {
            id: `m-${step.step}-${Date.now()}`,
            role: 'mind',
            content: step.response || '…',
            loop_depth: step.loop_depth,
            mind_name: step.mind_name,
            step: step.step,
            total: step.total,
            ts: Date.now(),
          },
        ]);
      });

      // Fire-and-forget signal
      apiClient.post('/users/me/mind/signal', {
        signal_title: 'conversation',
        signal_content: text.trim().slice(0, 400),
        tags: 'conversation,talk_to_mind',
      }).catch(() => {});
    } catch (err: any) {
      const isTimeout = err?.code === 'ECONNABORTED' || err?.message?.includes('timeout');
      const isAborted = err?.name === 'AbortError';
      const httpStatus = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'unknown error';
      const msg = isAborted
        ? 'The minds took too long to respond. Try a shorter message.'
        : isTimeout
        ? 'Mind is thinking hard (timeout). Try again or ask something simpler.'
        : httpStatus === 503
        ? 'Mind is busy — too many requests. Try again in a moment.'
        : httpStatus
        ? `Error ${httpStatus}: ${detail}`
        : `Connection lost — ${detail}`;
      setMessages(prev => [
        ...prev,
        { id: `err-${Date.now()}`, role: 'mind', content: msg, ts: Date.now() },
      ]);
    } finally {
      setSending(false);
    }
  }, [mindName, sending, messages]);

  if (loading) {
    return (
      <SafeAreaView style={s.safe} edges={['top']}>
        <View style={s.center}>
          <MindOrb size={64} speaking />
          <Text style={s.hint}>Connecting to your mind…</Text>
        </View>
      </SafeAreaView>
    );
  }

  const router = useRouter();
  const depthColor = avgDepth === 1 ? '#33AA55' : avgDepth === 2 ? '#FFB055' : '#9B55FF';

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <MindOrb size={38} speaking={sending} />
        <View style={s.headerText}>
          <Text style={s.headerTitle}>My Mind</Text>
          <Text style={s.headerSub} numberOfLines={1}>
            {mindName?.replace('user_', '').slice(0, 20) ?? 'loading…'}
          </Text>
        </View>
        <View style={[s.depthPill, { borderColor: depthColor + '55' }]}>
          <Text style={[s.depthLabel, { color: depthColor }]}>avg depth {avgDepth}</Text>
        </View>
        <TouchableOpacity style={s.prayersBtn} onPress={() => router.push('/(tabs)/prayers')}>
          <Text style={s.prayersIcon}>◎</Text>
        </TouchableOpacity>
      </View>

      {/* Chat + input */}
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          ref={scrollRef}
          style={s.scroll}
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {messages.length === 0 && (
            <View style={s.empty}>
              <MindOrb size={56} />
              <Text style={s.emptyTitle}>Your mind is ready</Text>
              <Text style={s.emptyHint}>
                Ask anything. Give a command. Your mind routes to the network
                and returns with the answer — depth shows how hard it thought.
              </Text>
            </View>
          )}
          {messages.map(m => <Bubble key={m.id} msg={m} />)}
          {sending && (
            <View style={[bbl.row, { paddingHorizontal: 14 }]}>
              <MindOrb size={26} speaking />
              <View style={[bbl.bubble, bbl.bubbleMind]}>
                <Text style={[bbl.text, { color: '#6C63FF', letterSpacing: 4 }]}>···</Text>
              </View>
            </View>
          )}
        </ScrollView>

        {/* Quick command chips — shown only when chat is empty */}
        {messages.length === 0 && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={s.chipsScroll}
            contentContainerStyle={s.chipsContent}
          >
            {QUICK_COMMANDS.map(cmd => (
              <TouchableOpacity key={cmd} style={s.chip} onPress={() => send(cmd)}>
                <Text style={s.chipText}>{cmd}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}

        {/* Input bar */}
        <View style={s.inputBar}>
          <TextInput
            style={s.input}
            value={input}
            onChangeText={setInput}
            placeholder="Ask or command your mind…"
            placeholderTextColor="rgba(180,180,220,0.3)"
            multiline
            maxLength={2000}
            returnKeyType="send"
            onSubmitEditing={() => send(input)}
            blurOnSubmit={false}
          />
          <TouchableOpacity
            style={[s.sendBtn, (!input.trim() || sending) && s.sendBtnDisabled]}
            onPress={() => send(input)}
            disabled={!input.trim() || sending}
          >
            <Text style={s.sendIcon}>↑</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:           { flex: 1, backgroundColor: '#08080F' },
  flex:           { flex: 1 },
  center:         { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16 },
  hint:           { color: 'rgba(180,180,220,0.5)', fontSize: 14 },

  header:         { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(108,99,255,0.12)' },
  headerText:     { flex: 1 },
  headerTitle:    { color: '#D0D0F0', fontSize: 17, fontWeight: '700' },
  headerSub:      { color: 'rgba(180,180,220,0.4)', fontSize: 11, fontFamily: 'monospace' },
  depthPill:      { borderWidth: 1, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 3 },
  depthLabel:     { fontSize: 10, letterSpacing: 1, fontFamily: 'monospace', textTransform: 'uppercase' },
  prayersBtn:     { width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(155,85,255,0.12)', borderWidth: 1, borderColor: 'rgba(155,85,255,0.35)', alignItems: 'center', justifyContent: 'center', marginLeft: 4 },
  prayersIcon:    { fontSize: 16, color: '#9B55FF' },

  scroll:         { flex: 1 },
  scrollContent:  { paddingTop: 16, paddingBottom: 16, gap: 10 },

  empty:          { alignItems: 'center', paddingTop: 60, paddingHorizontal: 32, gap: 16 },
  emptyTitle:     { color: '#D0D0F0', fontSize: 18, fontWeight: '700', textAlign: 'center' },
  emptyHint:      { color: 'rgba(180,180,220,0.45)', fontSize: 14, textAlign: 'center', lineHeight: 22 },

  chipsScroll:    { flexGrow: 0 },
  chipsContent:   { paddingHorizontal: 14, paddingVertical: 8, gap: 8 },
  chip:           { backgroundColor: 'rgba(108,99,255,0.12)', borderWidth: 1, borderColor: 'rgba(108,99,255,0.3)', borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8 },
  chipText:       { color: '#9B90FF', fontSize: 13 },

  inputBar:       { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: 12, paddingVertical: 10, gap: 10, borderTopWidth: 1, borderTopColor: 'rgba(108,99,255,0.15)', backgroundColor: '#0A0A14' },
  input:          { flex: 1, backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: 'rgba(108,99,255,0.2)', borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10, color: '#D0D0F0', fontSize: 15, maxHeight: 120 },
  sendBtn:        { width: 42, height: 42, borderRadius: 21, backgroundColor: '#6C63FF', alignItems: 'center', justifyContent: 'center' },
  sendBtnDisabled:{ backgroundColor: 'rgba(108,99,255,0.25)' },
  sendIcon:       { color: '#fff', fontSize: 18, fontWeight: '700' },
});
