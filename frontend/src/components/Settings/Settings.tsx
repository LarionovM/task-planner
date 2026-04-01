// Настройки — 4 вкладки: Общее, Бот, Таймер, Категории (v1.4.0)

import { useState, useEffect, useMemo, useRef } from 'react'
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors, type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useStore } from '../../store'
import { api } from '../../api/client'
import type { Category, WeeklyScheduleItem, WeeklyGoal, SpamConfig } from '../../types'
import EmojiPicker from '../EmojiPicker'
import ThemeToggle from '../ThemeToggle'
import './Settings.css'

type SettingsTab = 'general' | 'bot' | 'timer' | 'categories'

// === Вспомогательные ===

const TIME_SLOTS: string[] = []
for (let h = 0; h < 24; h++) {
  for (let m = 0; m < 60; m += 30) {
    TIME_SLOTS.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
  }
}

const DAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

const TIMEZONE_DATA: { tz: string; cities: string; hasDST?: boolean }[] = [
  { tz: 'Pacific/Honolulu', cities: 'Гонолулу' },
  { tz: 'America/Anchorage', cities: 'Анкоридж', hasDST: true },
  { tz: 'America/Los_Angeles', cities: 'Лос-Анджелес, Ванкувер', hasDST: true },
  { tz: 'America/Denver', cities: 'Денвер, Калгари', hasDST: true },
  { tz: 'America/Chicago', cities: 'Чикаго, Хьюстон', hasDST: true },
  { tz: 'America/New_York', cities: 'Нью-Йорк, Торонто, Майами', hasDST: true },
  { tz: 'America/Sao_Paulo', cities: 'Сан-Паулу, Буэнос-Айрес' },
  { tz: 'Europe/London', cities: 'Лондон, Лиссабон, Дублин', hasDST: true },
  { tz: 'Europe/Berlin', cities: 'Берлин, Париж, Мадрид, Варшава', hasDST: true },
  { tz: 'Europe/Kiev', cities: 'Киев, Бухарест, Хельсинки, Афины', hasDST: true },
  { tz: 'Europe/Kaliningrad', cities: 'Калининград, Кейптаун' },
  { tz: 'Africa/Cairo', cities: 'Каир', hasDST: true },
  { tz: 'Europe/Moscow', cities: 'Москва, Стамбул, Минск, Найроби' },
  { tz: 'Asia/Dubai', cities: 'Дубай, Баку, Тбилиси, Самара' },
  { tz: 'Asia/Kolkata', cities: 'Дели, Мумбаи, Калькутта' },
  { tz: 'Asia/Yekaterinburg', cities: 'Екатеринбург, Ташкент, Алматы' },
  { tz: 'Asia/Omsk', cities: 'Омск, Бишкек' },
  { tz: 'Asia/Krasnoyarsk', cities: 'Красноярск, Новосибирск, Бангкок, Ханой' },
  { tz: 'Asia/Shanghai', cities: 'Пекин, Шанхай, Сингапур, Иркутск' },
  { tz: 'Asia/Tokyo', cities: 'Токио, Сеул, Осака' },
  { tz: 'Asia/Vladivostok', cities: 'Владивосток, Хабаровск' },
  { tz: 'Australia/Sydney', cities: 'Сидней, Мельбурн', hasDST: true },
  { tz: 'Asia/Kamchatka', cities: 'Петропавловск-Камчатский' },
  { tz: 'Pacific/Auckland', cities: 'Окленд, Веллингтон', hasDST: true },
]

function getUtcOffset(tz: string): string {
  try {
    const now = new Date()
    const formatter = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'shortOffset' })
    const parts = formatter.formatToParts(now)
    const offsetPart = parts.find((p) => p.type === 'timeZoneName')
    return offsetPart?.value?.replace('GMT', 'UTC') || 'UTC'
  } catch { return 'UTC' }
}

function getOffsetMinutes(tz: string): number {
  try {
    const now = new Date()
    const utcStr = now.toLocaleString('en-US', { timeZone: 'UTC' })
    const tzStr = now.toLocaleString('en-US', { timeZone: tz })
    return (new Date(tzStr).getTime() - new Date(utcStr).getTime()) / 60000
  } catch { return 0 }
}

function formatTimezone(tz: string): string {
  const data = TIMEZONE_DATA.find((t) => t.tz === tz)
  const offset = getUtcOffset(tz)
  if (data) return `${offset} (${data.cities})`
  const parts = tz.split('/')
  return `${offset} (${parts[parts.length - 1].replace(/_/g, ' ')})`
}


// =============================================================
// ВКЛАДКА 1: Общее (расписание + рабочие часы + часовой пояс)
// =============================================================

function GeneralTab() {
  const { user, loadUser, schedule, loadSchedule, setHasUnsavedChanges } = useStore()
  const [days, setDays] = useState<WeeklyScheduleItem[]>([])
  const [dayStartTime, setDayStartTime] = useState('08:00')
  const [dayEndTime, setDayEndTime] = useState('23:50')
  const [timezone, setTimezone] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [initialDays, setInitialDays] = useState('')
  const [initialVals, setInitialVals] = useState('')

  const [tzOpen, setTzOpen] = useState(false)
  const [tzSearch, setTzSearch] = useState('')
  const tzRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (schedule.length > 0) {
      const sorted = [...schedule].sort((a, b) => a.day_of_week - b.day_of_week)
      setDays(sorted)
      setInitialDays(JSON.stringify(sorted))
    }
  }, [schedule])

  useEffect(() => {
    if (user) {
      setDayStartTime(user.day_start_time || '08:00')
      setDayEndTime(user.day_end_time || '23:50')
      setTimezone(user.timezone)
      setInitialVals(JSON.stringify({ s: user.day_start_time || '08:00', e: user.day_end_time || '23:50', tz: user.timezone }))
    }
  }, [user])

  useEffect(() => {
    const daysChanged = initialDays !== '' && JSON.stringify(days) !== initialDays
    const valsChanged = initialVals !== '' && JSON.stringify({ s: dayStartTime, e: dayEndTime, tz: timezone }) !== initialVals
    const changed = daysChanged || valsChanged
    setHasChanges(changed)
    setHasUnsavedChanges(changed)
  }, [days, dayStartTime, dayEndTime, timezone, initialDays, initialVals])

  useEffect(() => { return () => { setHasUnsavedChanges(false) } }, [])

  useEffect(() => {
    if (!tzOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (tzRef.current && !tzRef.current.contains(e.target as Node)) { setTzOpen(false); setTzSearch('') }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [tzOpen])

  useEffect(() => { if (tzOpen && searchRef.current) searchRef.current.focus() }, [tzOpen])

  const detectedTz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, [])
  const detectedMatch = useMemo(() => {
    const exact = TIMEZONE_DATA.find((t) => t.tz === detectedTz)
    if (exact) return exact.tz
    const detectedOffset = getOffsetMinutes(detectedTz)
    const match = TIMEZONE_DATA.find((t) => getOffsetMinutes(t.tz) === detectedOffset)
    return match?.tz || detectedTz
  }, [detectedTz])
  const sortedTimezones = useMemo(() => [...TIMEZONE_DATA].sort((a, b) => getOffsetMinutes(a.tz) - getOffsetMinutes(b.tz)), [])
  const filteredTimezones = useMemo(() => {
    if (!tzSearch.trim()) return sortedTimezones
    const q = tzSearch.toLowerCase()
    return sortedTimezones.filter((t) => t.tz.toLowerCase().includes(q) || t.cities.toLowerCase().includes(q) || getUtcOffset(t.tz).toLowerCase().includes(q))
  }, [tzSearch, sortedTimezones])

  const updateDay = (idx: number, updates: Partial<WeeklyScheduleItem>) => {
    const newDays = [...days]
    newDays[idx] = { ...newDays[idx], ...updates }
    setDays(newDays)
  }

  const handleSave = async () => {
    if (dayStartTime >= dayEndTime) { alert('Начало дня должно быть раньше конца'); return }
    setSaving(true)
    try {
      await api.updateSchedule(days)
      await api.updateSettings({ day_start_time: dayStartTime, day_end_time: dayEndTime, timezone })
      await loadSchedule()
      await loadUser()
      setInitialDays(JSON.stringify(days))
      setInitialVals(JSON.stringify({ s: dayStartTime, e: dayEndTime, tz: timezone }))
      setHasChanges(false)
      setHasUnsavedChanges(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  const handleTzSelect = (tz: string) => { setTimezone(tz); setTzOpen(false); setTzSearch('') }

  return (
    <>
      {hasChanges && (
        <div style={{ padding: '8px 0', textAlign: 'right' }}>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {saving ? '...' : '💾 Сохранить'}
          </button>
        </div>
      )}
      {saved && <div style={{ textAlign: 'center', color: 'var(--success)', padding: 4, fontSize: 13 }}>✅ Сохранено</div>}

      {/* Рабочие часы */}
      <div className="settings-section card">
        <h3>🕐 Рабочий день</h3>
        <p className="hint" style={{ marginBottom: 8 }}>
          Определяет часы для помодоро-циклов и слотов в календаре
        </p>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label className="label">Начало</label>
            <select className="input" value={dayStartTime} onChange={(e) => setDayStartTime(e.target.value)}>
              {TIME_SLOTS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">Конец</label>
            <select className="input" value={dayEndTime} onChange={(e) => setDayEndTime(e.target.value)}>
              {TIME_SLOTS.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>
        {dayStartTime >= dayEndTime && (
          <p className="hint" style={{ color: 'var(--danger)', marginTop: 4 }}>⚠️ Начало дня должно быть раньше конца</p>
        )}
      </div>

      {/* Дни недели */}
      <div className="settings-section card">
        <h3>📅 Дни недели</h3>
        <p className="hint" style={{ marginBottom: 8 }}>В выходные бот не отправляет помодоро</p>
        <div>
          {days.map((day, idx) => (
            <div key={day.day_of_week} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: idx < days.length - 1 ? '1px solid var(--border)' : 'none' }}>
              <span style={{ fontSize: 13 }}>{DAY_NAMES[day.day_of_week]}</span>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer' }}>
                <input type="checkbox" checked={day.is_day_off} onChange={(e) => updateDay(idx, { is_day_off: e.target.checked })} />
                Выходной
              </label>
            </div>
          ))}
        </div>
      </div>

      {/* Часовой пояс */}
      <div className="settings-section card">
        <h3>🌍 Часовой пояс</h3>
        <div className="tz-picker" ref={tzRef}>
          <button className="tz-picker-trigger input" onClick={() => setTzOpen(!tzOpen)} type="button">
            <span className="tz-picker-value">{formatTimezone(timezone)}</span>
            <span className={`tz-picker-arrow ${tzOpen ? 'open' : ''}`}>▾</span>
          </button>
          {tzOpen && (
            <div className="tz-picker-dropdown">
              <input ref={searchRef} className="tz-picker-search" type="text" placeholder="Поиск: город, UTC..." value={tzSearch} onChange={(e) => setTzSearch(e.target.value)} />
              <div className="tz-picker-list">
                {!tzSearch && (
                  <button className={`tz-picker-item tz-picker-item-detected ${timezone === detectedMatch ? 'selected' : ''}`} onClick={() => handleTzSelect(detectedMatch)}>
                    <span className="tz-picker-item-label">🎯 Авто: {getUtcOffset(detectedTz)} ({detectedTz.split('/').pop()?.replace(/_/g, ' ')})</span>
                  </button>
                )}
                {filteredTimezones.map((t) => (
                  <button key={t.tz} className={`tz-picker-item ${timezone === t.tz ? 'selected' : ''}`} onClick={() => handleTzSelect(t.tz)}>
                    <span className="tz-picker-item-offset">{getUtcOffset(t.tz)}</span>
                    <span className="tz-picker-item-cities">{t.cities}</span>
                    {t.hasDST && <span className="tz-picker-item-dst" title="Переводят часы">🔄</span>}
                  </button>
                ))}
                {filteredTimezones.length === 0 && <div className="tz-picker-empty">Ничего не найдено</div>}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}


// =============================================================
// ВКЛАДКА 2: Бот (спам-напоминания + пустые слоты)
// =============================================================

function BotTab() {
  const { spamConfig, loadSpamConfig, setHasUnsavedChanges } = useStore()
  const [spam, setSpam] = useState<Partial<SpamConfig>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [initialSpam, setInitialSpam] = useState('')

  useEffect(() => { loadSpamConfig() }, [])

  useEffect(() => {
    if (spamConfig) { setSpam(spamConfig); setInitialSpam(JSON.stringify(spamConfig)) }
  }, [spamConfig])

  useEffect(() => {
    const changed = initialSpam !== '' && JSON.stringify(spam) !== initialSpam
    setHasChanges(changed)
    setHasUnsavedChanges(changed)
  }, [spam, initialSpam])

  useEffect(() => { return () => { setHasUnsavedChanges(false) } }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.updateSpamConfig(spam)
      await loadSpamConfig()
      setInitialSpam(JSON.stringify(spam))
      setHasChanges(false)
      setHasUnsavedChanges(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  return (
    <>
      {hasChanges && (
        <div style={{ padding: '8px 0', textAlign: 'right' }}>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {saving ? '...' : '💾 Сохранить'}
          </button>
        </div>
      )}
      {saved && <div style={{ textAlign: 'center', color: 'var(--success)', padding: 4, fontSize: 13 }}>✅ Сохранено</div>}

      {/* Спам */}
      <div className="settings-section card">
        <h3>📢 Напоминания</h3>
        <p className="hint" style={{ marginBottom: 8 }}>
          Если проигноришь завершение — бот напомнит с нарастающим интервалом
        </p>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', marginBottom: 8 }}>
          <input type="checkbox" checked={spam.enabled ?? true} onChange={(e) => setSpam({ ...spam, enabled: e.target.checked })} />
          Включить
        </label>
        {spam.enabled && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            <div>
              <label className="label">Старт (сек)</label>
              <input className="input" type="number" min={5} max={120} value={spam.initial_interval_sec ?? 10} onChange={(e) => setSpam({ ...spam, initial_interval_sec: parseInt(e.target.value) || 10 })} />
            </div>
            <div>
              <label className="label">Множитель</label>
              <input className="input" type="number" min={1} max={5} step={0.1} value={spam.multiplier ?? 1.5} onChange={(e) => setSpam({ ...spam, multiplier: parseFloat(e.target.value) || 1.5 })} />
            </div>
            <div>
              <label className="label">Макс (сек)</label>
              <input className="input" type="number" min={60} max={3600} value={spam.max_interval_sec ?? 600} onChange={(e) => setSpam({ ...spam, max_interval_sec: parseInt(e.target.value) || 600 })} />
            </div>
          </div>
        )}
      </div>

      {/* Пустые слоты */}
      <div className="settings-section card">
        <h3>📋 Пустые слоты</h3>
        <p className="hint" style={{ marginBottom: 8 }}>
          Напоминание заполнить план, если есть задачи и свободные слоты
        </p>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', marginBottom: 8 }}>
          <input type="checkbox" checked={spam.empty_slots_enabled ?? true} onChange={(e) => setSpam({ ...spam, empty_slots_enabled: e.target.checked })} />
          Включить
        </label>
        {spam.empty_slots_enabled && (
          <div>
            <label className="label">Интервал повтора утром (мин)</label>
            <input className="input" type="number" min={10} max={120} value={spam.empty_slots_interval_min ?? 30} onChange={(e) => setSpam({ ...spam, empty_slots_interval_min: parseInt(e.target.value) || 30 })} style={{ maxWidth: 120 }} />
          </div>
        )}
      </div>
    </>
  )
}


// =============================================================
// ВКЛАДКА 3: Таймер (помодоро)
// =============================================================

function TimerTab() {
  const { user, loadUser, setHasUnsavedChanges } = useStore()
  // Строковые состояния для числовых полей — избегаем "04" при вводе (У10)
  const [pomodoroWork, setPomodoroWork] = useState('25')
  const [pomodoroShortBreak, setPomodoroShortBreak] = useState('5')
  const [pomodoroLongBreak, setPomodoroLongBreak] = useState('30')
  const [pomodoroCycles, setPomodoroCycles] = useState('4')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [initial, setInitial] = useState('')

  useEffect(() => {
    if (user) {
      setPomodoroWork(String(user.pomodoro_work_min || 25))
      setPomodoroShortBreak(String(user.pomodoro_short_break_min || 5))
      setPomodoroLongBreak(String(user.pomodoro_long_break_min || 30))
      setPomodoroCycles(String(user.pomodoro_cycles_before_long || 4))
      setInitial(JSON.stringify({
        w: user.pomodoro_work_min || 25, sb: user.pomodoro_short_break_min || 5,
        lb: user.pomodoro_long_break_min || 30, c: user.pomodoro_cycles_before_long || 4,
      }))
    }
  }, [user])

  useEffect(() => {
    const w = parseInt(pomodoroWork) || 0
    const sb = parseInt(pomodoroShortBreak) || 0
    const lb = parseInt(pomodoroLongBreak) || 0
    const c = parseInt(pomodoroCycles) || 0
    const changed = initial !== '' && JSON.stringify({ w, sb, lb, c }) !== initial
    setHasChanges(changed)
    setHasUnsavedChanges(changed)
  }, [pomodoroWork, pomodoroShortBreak, pomodoroLongBreak, pomodoroCycles, initial])

  useEffect(() => { return () => { setHasUnsavedChanges(false) } }, [])

  const handleSave = async () => {
    const w = parseInt(pomodoroWork)
    const sb = parseInt(pomodoroShortBreak)
    const lb = parseInt(pomodoroLongBreak)
    const c = parseInt(pomodoroCycles)
    if (!w || !sb || !lb || !c) { alert('Все поля должны быть заполнены и больше 0'); return }
    setSaving(true)
    try {
      await api.updateSettings({
        pomodoro_work_min: w,
        pomodoro_short_break_min: sb,
        pomodoro_long_break_min: lb,
        pomodoro_cycles_before_long: c,
      })
      await loadUser()
      setInitial(JSON.stringify({ w, sb, lb, c }))
      setHasChanges(false)
      setHasUnsavedChanges(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally { setSaving(false) }
  }

  return (
    <>
      {hasChanges && (
        <div style={{ padding: '8px 0', textAlign: 'right' }}>
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {saving ? '...' : '💾 Сохранить'}
          </button>
        </div>
      )}
      {saved && <div style={{ textAlign: 'center', color: 'var(--success)', padding: 4, fontSize: 13 }}>✅ Сохранено</div>}

      <div className="settings-section card">
        <h3>🍅 Помодоро-цикл</h3>
        <p className="hint" style={{ marginBottom: 8 }}>Автоматические циклы фокусировки в течение рабочего дня</p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label className="label">Работа (мин)</label>
            <input type="number" className="input" min={5} max={120} step={5} value={pomodoroWork} onChange={(e) => setPomodoroWork(e.target.value)} />
          </div>
          <div>
            <label className="label">Короткий перерыв</label>
            <input type="number" className="input" min={1} max={30} step={1} value={pomodoroShortBreak} onChange={(e) => setPomodoroShortBreak(e.target.value)} />
          </div>
          <div>
            <label className="label">Длинный перерыв</label>
            <input type="number" className="input" min={5} max={60} step={5} value={pomodoroLongBreak} onChange={(e) => setPomodoroLongBreak(e.target.value)} />
          </div>
          <div>
            <label className="label">Циклов до длинного</label>
            <input type="number" className="input" min={2} max={10} step={1} value={pomodoroCycles} onChange={(e) => setPomodoroCycles(e.target.value)} />
          </div>
        </div>
        <p className="hint" style={{ marginTop: 8 }}>
          {parseInt(pomodoroWork) || '?'}мин работа → {parseInt(pomodoroShortBreak) || '?'}мин перерыв. Каждый {parseInt(pomodoroCycles) || '?'}-й — {parseInt(pomodoroLongBreak) || '?'}мин.
        </p>
      </div>
    </>
  )
}


// =============================================================
// ВКЛАДКА 4: Категории (CRUD + цели)
// =============================================================

function SortableCategory({
  cat, goal, onEdit, onDelete, onGoalChange,
}: {
  cat: Category; goal: number; onEdit: (c: Category) => void; onDelete: (c: Category) => void
  onGoalChange: (catId: number, hours: number) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: cat.id })
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }

  return (
    <div ref={setNodeRef} style={style} className="cat-item card">
      <div className="cat-drag" {...attributes} {...listeners}>☰</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ fontSize: 16 }}>{cat.emoji || '📁'}</span>
          <span style={{ fontSize: 13, fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cat.name}</span>
          <span style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 600, minWidth: 28, textAlign: 'right' }}>{goal}ч</span>
          <button className="btn-icon" onClick={() => onEdit(cat)} title="Редактировать" style={{ fontSize: 12 }}>✏️</button>
          <button className="btn-icon" onClick={() => onDelete(cat)} title="Удалить" style={{ fontSize: 12 }}>🗑</button>
        </div>
        <input
          type="range" min={0} max={40} step={0.5} value={goal}
          onChange={(e) => onGoalChange(cat.id, parseFloat(e.target.value))}
          style={{ width: '100%', margin: 0 }}
          className="goal-slider"
        />
      </div>
    </div>
  )
}

function CategoriesTab() {
  const { categories, loadCategories, goals, loadGoals, setHasUnsavedChanges } = useStore()
  const [items, setItems] = useState<Category[]>([])
  const [localGoals, setLocalGoals] = useState<Record<number, number>>({})
  const [showForm, setShowForm] = useState(false)
  const [editCat, setEditCat] = useState<Category | null>(null)
  const [deleteCat, setDeleteCat] = useState<Category | null>(null)
  const [formName, setFormName] = useState('')
  const [formEmoji, setFormEmoji] = useState('')
  const [formColor, setFormColor] = useState('#6366f1')
  const [saving, setSaving] = useState(false)
  const [goalsSaving, setGoalsSaving] = useState(false)
  const [goalsSaved, setGoalsSaved] = useState(false)
  const [goalsChanged, setGoalsChanged] = useState(false)
  const [initialGoals, setInitialGoals] = useState('')

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  useEffect(() => { setItems(categories) }, [categories])

  useEffect(() => {
    const map: Record<number, number> = {}
    goals.forEach((g) => { map[g.category_id] = g.target_hours })
    categories.forEach((c) => { if (!(c.id in map)) map[c.id] = 0 })
    setLocalGoals(map)
    setInitialGoals(JSON.stringify(map))
  }, [goals, categories])

  useEffect(() => {
    if (!initialGoals) return
    const changed = JSON.stringify(localGoals) !== initialGoals
    setGoalsChanged(changed)
    setHasUnsavedChanges(changed)
  }, [localGoals, initialGoals])

  useEffect(() => { return () => { setHasUnsavedChanges(false) } }, [])

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = items.findIndex((c) => c.id === active.id)
    const newIndex = items.findIndex((c) => c.id === over.id)
    const newItems = arrayMove(items, oldIndex, newIndex)
    setItems(newItems)
    await api.reorderCategories(newItems.map((c) => c.id))
    await loadCategories()
  }

  const handleAdd = () => { setEditCat(null); setFormName(''); setFormEmoji(''); setFormColor('#6366f1'); setShowForm(true) }
  const handleEdit = (cat: Category) => { setEditCat(cat); setFormName(cat.name); setFormEmoji(cat.emoji || ''); setFormColor(cat.color || '#6366f1'); setShowForm(true) }

  const handleSaveCat = async () => {
    if (!formName.trim()) return
    setSaving(true)
    try {
      if (editCat) {
        await api.updateCategory(editCat.id, { name: formName.trim(), emoji: formEmoji || null, color: formColor })
      } else {
        await api.createCategory({ name: formName.trim(), emoji: formEmoji || null, color: formColor })
      }
      await loadCategories()
      setShowForm(false)
    } finally { setSaving(false) }
  }

  const handleDeleteCat = async () => {
    if (!deleteCat) return
    setSaving(true)
    try { await api.deleteCategory(deleteCat.id); await loadCategories(); setDeleteCat(null) }
    finally { setSaving(false) }
  }

  const handleGoalChange = (catId: number, hours: number) => {
    setLocalGoals((prev) => ({ ...prev, [catId]: hours }))
  }

  const handleSaveGoals = async () => {
    setGoalsSaving(true)
    try {
      const goalsArr: WeeklyGoal[] = Object.entries(localGoals).map(([catId, hours]) => ({
        category_id: parseInt(catId), target_hours: hours,
      }))
      await api.updateGoals(goalsArr)
      await loadGoals()
      setInitialGoals(JSON.stringify(localGoals))
      setGoalsChanged(false)
      setHasUnsavedChanges(false)
      setGoalsSaved(true)
      setTimeout(() => setGoalsSaved(false), 2000)
    } finally { setGoalsSaving(false) }
  }

  const totalHours = Object.values(localGoals).reduce((sum, h) => sum + h, 0)

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <p className="hint">Перетащите для сортировки. Слайдер — цель ч/нед.</p>
        <button className="btn btn-primary btn-sm" onClick={handleAdd}>+ Добавить</button>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={items.map((c) => c.id)} strategy={verticalListSortingStrategy}>
          <div className="cat-list">
            {items.map((cat) => (
              <SortableCategory
                key={cat.id} cat={cat} goal={localGoals[cat.id] ?? 0}
                onEdit={handleEdit} onDelete={(c) => setDeleteCat(c)}
                onGoalChange={handleGoalChange}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      {items.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Нет категорий. Нажмите «Добавить».</div>
      )}

      {items.length > 0 && (
        <div className="card" style={{ marginTop: 12, padding: '10px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 13 }}>Всего: <strong>{totalHours}ч/нед</strong></span>
          {goalsChanged ? (
            <button className="btn btn-primary btn-sm" onClick={handleSaveGoals} disabled={goalsSaving}>
              {goalsSaving ? '...' : '💾 Сохранить цели'}
            </button>
          ) : goalsSaved ? (
            <span style={{ color: 'var(--success)', fontSize: 13 }}>✅</span>
          ) : null}
        </div>
      )}

      {showForm && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setShowForm(false) }}>
          <div className="dialog" onMouseDown={(e) => e.stopPropagation()}>
            <h3>{editCat ? 'Редактировать' : 'Новая категория'}</h3>
            <label className="label">Название</label>
            <input className="input" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Например: Работа" autoFocus />
            <label className="label" style={{ marginTop: 12 }}>Иконка</label>
            <EmojiPicker selected={formEmoji} onSelect={setFormEmoji} />
            {formEmoji && (
              <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
                Выбрано: {formEmoji}
                <button className="btn-icon" style={{ marginLeft: 4, fontSize: 11 }} onClick={() => setFormEmoji('')}>✕</button>
              </div>
            )}
            <label className="label" style={{ marginTop: 12 }}>Цвет</label>
            <div className="cat-colors">
              {['#6366f1', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ef4444', '#06b6d4'].map((c) => (
                <button key={c} className={`cat-color-btn ${formColor === c ? 'active' : ''}`} style={{ background: c }} onClick={() => setFormColor(c)} />
              ))}
            </div>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={handleSaveCat} disabled={saving || !formName.trim()}>{saving ? '...' : 'Сохранить'}</button>
            </div>
          </div>
        </div>
      )}

      {deleteCat && (
        <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) setDeleteCat(null) }}>
          <div className="dialog" onMouseDown={(e) => e.stopPropagation()}>
            <h3>Удалить категорию?</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>«{deleteCat.emoji} {deleteCat.name}» будет удалена.</p>
            <div className="dialog-actions">
              <button className="btn btn-secondary" onClick={() => setDeleteCat(null)}>Отмена</button>
              <button className="btn btn-danger" onClick={handleDeleteCat} disabled={saving}>{saving ? '...' : 'Удалить'}</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}


// =============================================================
// ГЛАВНЫЙ КОМПОНЕНТ
// =============================================================

export default function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general')

  const tabs: { key: SettingsTab; label: string; icon: string }[] = [
    { key: 'general', label: 'Общее', icon: '⚙️' },
    { key: 'bot', label: 'Бот', icon: '🔔' },
    { key: 'timer', label: 'Таймер', icon: '🍅' },
    { key: 'categories', label: 'Категории', icon: '📁' },
  ]

  return (
    <div className="settings-screen">
      <div className="header">
        <h1>⚙️ Настройки</h1>
        <ThemeToggle />
      </div>

      <div className="settings-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`settings-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      <div className="settings-tab-content">
        {activeTab === 'general' && <GeneralTab />}
        {activeTab === 'bot' && <BotTab />}
        {activeTab === 'timer' && <TimerTab />}
        {activeTab === 'categories' && <CategoriesTab />}
      </div>

      <div style={{ height: 80 }} />
    </div>
  )
}
