import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

/**
 * Creator Console — 4 tabs.
 *
 * Guide  — The Founder speaks to the mind (feed, directives, absorptions)
 * Mind   — The mind breathes (live oscillation, corpus, awakening stage)
 * Build  — What the mind is building (synthesis by domain/theme)
 * World  — Is everything alive? (health, cache, one-glance status)
 */
export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#A06CEE',
        tabBarInactiveTintColor: '#444466',
        tabBarStyle: {
          backgroundColor: '#07070F',
          borderTopColor: 'rgba(160,108,238,0.12)',
          borderTopWidth: 1,
        },
        tabBarLabelStyle: { fontSize: 10, letterSpacing: 0.5 },
      }}
    >
      <Tabs.Screen
        name="guide"
        options={{
          title: 'Guide',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="book-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="mind"
        options={{
          title: 'Mind',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="radio-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="build"
        options={{
          title: 'Build',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="construct-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="world"
        options={{
          title: 'World',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="planet-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}

