// Нижняя навигация — 5 вкладок

import { useStore } from '../../store'
import type { Screen } from '../../types'
import './BottomNav.css'

interface NavItem {
  screen: Screen
  icon: string
  label: string
}

const items: NavItem[] = [
  { screen: 'backlog', icon: '📋', label: 'Задачи' },
  { screen: 'calendar', icon: '📅', label: 'Календарь' },
  { screen: 'summary', icon: '📊', label: 'Итоги' },
  { screen: 'settings', icon: '⚙️', label: 'Настройки' },
]

export default function BottomNav() {
  const { screen, setScreen } = useStore()

  return (
    <nav className="bottom-nav">
      {items.map((item) => (
        <button
          key={item.screen}
          className={`nav-item ${screen === item.screen ? 'active' : ''}`}
          onClick={() => setScreen(item.screen)}
        >
          <span className="icon">{item.icon}</span>
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  )
}
