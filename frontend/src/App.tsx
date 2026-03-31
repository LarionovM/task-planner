import { useEffect } from 'react'
import { useStore } from './store'
import BottomNav from './components/Navigation/BottomNav'
import TimezoneSelect from './components/TimezoneSelect/TimezoneSelect'
import Categories from './components/Categories/Categories'
import WeekSchedule from './components/WeekSchedule/WeekSchedule'
import Goals from './components/Goals/Goals'
import Backlog from './components/Backlog/Backlog'
import Calendar from './components/Calendar/Calendar'
import Summary from './components/Summary/Summary'
import Settings from './components/Settings/Settings'

function App() {
  const { screen, theme, user, loading, error, loadUser, loadCategories, loadSchedule, loadGoals, pendingScreen, confirmNavigation, cancelNavigation } = useStore()

  // Инициализация темы из localStorage
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [])

  // Загрузка начальных данных
  useEffect(() => {
    const init = async () => {
      useStore.setState({ loading: true })
      await loadUser()
      await loadCategories()
      await loadSchedule()
      await loadGoals()
      useStore.setState({ loading: false })
    }
    init()
  }, [])

  // После загрузки — проверяем, нужен ли экран TZ
  useEffect(() => {
    if (user && user.timezone === 'Europe/Moscow') {
      // Проверяем, совпадает ли с автоопределённым TZ
      const detectedTz = Intl.DateTimeFormat().resolvedOptions().timeZone
      if (detectedTz !== 'Europe/Moscow') {
        // Дефолтный TZ не совпадает — предлагаем настроить
        useStore.setState({ screen: 'timezone' })
      }
    }
  }, [user])

  if (loading) {
    return (
      <div className="app" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⏳</div>
          <div>Загрузка...</div>
        </div>
      </div>
    )
  }

  if (error && !user) {
    return (
      <div className="app" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: 'var(--danger)' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>😕</div>
          <div>Ошибка: {error}</div>
          <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => window.location.reload()}>
            Повторить
          </button>
        </div>
      </div>
    )
  }

  // Рендер текущего экрана
  const renderScreen = () => {
    switch (screen) {
      case 'timezone':
        return <TimezoneSelect />
      case 'categories':
        return <Categories />
      case 'schedule':
        return <WeekSchedule />
      case 'goals':
        return <Goals />
      case 'backlog':
        return <Backlog />
      case 'calendar':
        return <Calendar />
      case 'summary':
        return <Summary />
      case 'settings':
        return <Settings />
      default:
        return <Calendar />
    }
  }

  // Навбар не показываем на экране TZ
  const showNav = screen !== 'timezone'

  return (
    <div className="app">
      {renderScreen()}
      {showNav && <BottomNav />}

      {/* Диалог несохранённых изменений */}
      {pendingScreen && (
        <div className="overlay" onClick={cancelNavigation}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h3>⚠️ Несохранённые изменения</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
              У вас есть несохранённые изменения. Уйти без сохранения?
            </p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={cancelNavigation}>Остаться</button>
              <button className="btn btn-primary" onClick={confirmNavigation}>Уйти</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
