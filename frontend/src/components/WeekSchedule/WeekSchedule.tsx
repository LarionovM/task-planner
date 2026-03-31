// Экран 2: Расписание недели — выходные + спам-настройки (ручное сохранение)

import { useState, useEffect } from 'react'
import { useStore } from '../../store'
import { api } from '../../api/client'
import type { WeeklyScheduleItem, SpamConfig } from '../../types'
import ThemeToggle from '../ThemeToggle'
import './WeekSchedule.css'

const DAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

export default function WeekSchedule() {
  const { schedule, loadSchedule, spamConfig, loadSpamConfig, setScreen, setHasUnsavedChanges } = useStore()
  const [days, setDays] = useState<WeeklyScheduleItem[]>([])
  const [spam, setSpam] = useState<Partial<SpamConfig>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [initialDays, setInitialDays] = useState('')
  const [initialSpam, setInitialSpam] = useState('')

  useEffect(() => { loadSpamConfig() }, [])

  useEffect(() => {
    if (schedule.length > 0) {
      const sorted = [...schedule].sort((a, b) => a.day_of_week - b.day_of_week)
      setDays(sorted)
      setInitialDays(JSON.stringify(sorted))
    }
  }, [schedule])

  useEffect(() => {
    if (spamConfig) {
      setSpam(spamConfig)
      setInitialSpam(JSON.stringify(spamConfig))
    }
  }, [spamConfig])

  // Отслеживание изменений
  useEffect(() => {
    const daysChanged = initialDays !== '' && JSON.stringify(days) !== initialDays
    const spamChanged = initialSpam !== '' && JSON.stringify(spam) !== initialSpam
    const changed = daysChanged || spamChanged
    setHasChanges(changed)
    setHasUnsavedChanges(changed)
  }, [days, spam, initialDays, initialSpam])

  // Сброс флага при размонтировании
  useEffect(() => {
    return () => { setHasUnsavedChanges(false) }
  }, [])

  const updateDay = (idx: number, updates: Partial<WeeklyScheduleItem>) => {
    const newDays = [...days]
    newDays[idx] = { ...newDays[idx], ...updates }
    setDays(newDays)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.updateSchedule(days)
      if (Object.keys(spam).length > 0) await api.updateSpamConfig(spam)
      await loadSchedule()
      await loadSpamConfig()
      setInitialDays(JSON.stringify(days))
      setInitialSpam(JSON.stringify(spam))
      setHasChanges(false)
      setHasUnsavedChanges(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error('Ошибка сохранения:', e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="schedule-screen">
      <div className="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn-icon" onClick={() => setScreen('settings')}>←</button>
          <h1>📅 Расписание</h1>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {hasChanges ? (
            <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
              {saving ? '...' : '💾 Сохранить'}
            </button>
          ) : saved ? (
            <span style={{ color: 'var(--success)', fontSize: 13 }}>✅ Сохранено</span>
          ) : null}
          <ThemeToggle />
        </div>
      </div>

      <p className="hint" style={{ marginBottom: 16 }}>
        Отметьте выходные дни. В выходные бот не будет спамить напоминаниями.
      </p>

      {/* Дни недели — чекбоксы выходных */}
      <div className="schedule-days">
        {days.map((day, idx) => (
          <div key={day.day_of_week} className={`schedule-day-simple card ${day.is_day_off ? 'day-off' : ''}`}>
            <span className="schedule-day-name">{DAY_NAMES[day.day_of_week]}</span>
            <label className="schedule-toggle">
              <input
                type="checkbox"
                checked={day.is_day_off}
                onChange={(e) => updateDay(idx, { is_day_off: e.target.checked })}
              />
              <span className="schedule-toggle-label">Выходной</span>
            </label>
          </div>
        ))}
      </div>

      {/* Спам */}
      <div className="schedule-section">
        <h2 className="screen-title" style={{ fontSize: 16 }}>📢 Настойчивые напоминания</h2>
        <p className="hint" style={{ marginBottom: 12 }}>
          Если проигноришь завершение блока — бот начнёт напоминать.
          Интервал между сообщениями нарастает от начального до максимального.
        </p>

        <label className="schedule-toggle" style={{ marginBottom: 12 }}>
          <input type="checkbox" checked={spam.enabled ?? true} onChange={(e) => setSpam({ ...spam, enabled: e.target.checked })} />
          <span className="schedule-toggle-label">Включить</span>
        </label>

        {spam.enabled && (
          <div className="spam-settings">
            <div className="spam-field">
              <label className="label">Начальный интервал (сек)</label>
              <input className="input" type="number" min={5} max={120} value={spam.initial_interval_sec ?? 10} onChange={(e) => setSpam({ ...spam, initial_interval_sec: parseInt(e.target.value) || 10 })} />
            </div>
            <div className="spam-field">
              <label className="label">Множитель нарастания</label>
              <input className="input" type="number" min={1} max={5} step={0.1} value={spam.multiplier ?? 1.5} onChange={(e) => setSpam({ ...spam, multiplier: parseFloat(e.target.value) || 1.5 })} />
              <span className="hint">
                Каждое следующее напоминание приходит в {spam.multiplier ?? 1.5}x позже предыдущего.
                Пример: {spam.initial_interval_sec ?? 10}с → {Math.round((spam.initial_interval_sec ?? 10) * (spam.multiplier ?? 1.5))}с → {Math.round((spam.initial_interval_sec ?? 10) * (spam.multiplier ?? 1.5) ** 2)}с → ...
              </span>
            </div>
            <div className="spam-field">
              <label className="label">Макс. интервал (сек)</label>
              <input className="input" type="number" min={60} max={3600} value={spam.max_interval_sec ?? 600} onChange={(e) => setSpam({ ...spam, max_interval_sec: parseInt(e.target.value) || 600 })} />
            </div>
          </div>
        )}
      </div>

      {/* Напоминания о пустых слотах */}
      <div className="schedule-section">
        <h2 className="screen-title" style={{ fontSize: 16 }}>📋 Напоминания о пустых слотах</h2>
        <p className="hint" style={{ marginBottom: 12 }}>
          Бот напомнит заполнить план, если в бэклоге есть задачи, а в расписании — свободные слоты.
          Вечером — мягкое напоминание, утром — настойчивое с повторами.
        </p>

        <label className="schedule-toggle" style={{ marginBottom: 12 }}>
          <input type="checkbox" checked={spam.empty_slots_enabled ?? true} onChange={(e) => setSpam({ ...spam, empty_slots_enabled: e.target.checked })} />
          <span className="schedule-toggle-label">Включить</span>
        </label>

        {spam.empty_slots_enabled && (
          <div className="spam-settings">
            <div className="spam-field">
              <label className="label">Интервал повтора утром (мин)</label>
              <input className="input" type="number" min={10} max={120} value={spam.empty_slots_interval_min ?? 30} onChange={(e) => setSpam({ ...spam, empty_slots_interval_min: parseInt(e.target.value) || 30 })} />
              <p className="hint" style={{ marginTop: 4 }}>Как часто напоминать утром, пока не заполнишь план</p>
            </div>
          </div>
        )}
      </div>

      <div style={{ height: 80 }} />
    </div>
  )
}
