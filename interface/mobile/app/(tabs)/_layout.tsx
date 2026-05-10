import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#6C63FF',
        tabBarInactiveTintColor: '#555577',
        tabBarStyle: {
          backgroundColor: '#0A0A14',
          borderTopColor: 'rgba(108,99,255,0.15)',
        },
        tabBarLabelStyle: { fontSize: 11 },
      }}
    >
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
        name="learn"
        options={{
          title: 'Ether',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="infinite-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="monitor"
        options={{
          title: 'Monitor',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="pulse-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
