import { useStore } from '../store'

export default function ThemeToggle() {
  const { theme, toggleTheme } = useStore()
  return (
    <button
      className="btn-icon theme-toggle-inline"
      onClick={toggleTheme}
      title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  )
}
