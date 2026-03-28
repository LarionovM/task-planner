// Настройки из шапки Web App — TZ, тихое время, начало/конец дня

import { useState, useEffect, useMemo, useRef } from 'react'
import { useStore } from '../../store'
import { api } from '../../api/client'
import './Settings.css'

const TIME_SLOTS: string[] = []
for (let h = 0; h < 24; h++) {
  for (let m = 0; m < 60; m += 30) {
    TIME_SLOTS.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
  }
}

// Часовые пояса — один на каждый уникальный offset+DST комбинацию
// Города с разными правилами DST ОБЯЗАТЕЛЬНО в отдельных строках (иначе время будет неправильным)
// hasDST помечает строки с переводом часов
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

/** Получить UTC смещение для часового пояса */
function getUtcOffset(tz: string): string {
  try {
    const now = new Date()
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'shortOffset',
    })
    const parts = formatter.formatToParts(now)
    const offsetPart = parts.find((p) => p.type === 'timeZoneName')
    return offsetPart?.value?.replace('GMT', 'UTC') || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** Получить числовое смещение для сортировки */
function getOffsetMinutes(tz: string): number {
  try {
    const now = new Date()
    const utcStr = now.toLocaleString('en-US', { timeZone: 'UTC' })
    const tzStr = now.toLocaleString('en-US', { timeZone: tz })
    return (new Date(tzStr).getTime() - new Date(utcStr).getTime()) / 60000
  } catch {
    return 0
  }
}

/** Дружественное отображение для таймзоны */
function formatTimezone(tz: string): string {
  const data = TIMEZONE_DATA.find((t) => t.tz === tz)
  const offset = getUtcOffset(tz)
  if (data) {
    return `${offset} (${data.cities})`
  }
  // Если нет в нашем списке — показываем IANA имя
  const parts = tz.split('/')
  const city = parts[parts.length - 1].replace(/_/g, ' ')
  return `${offset} (${city})`
}

export default function Settings() {
  const { user, loadUser, setScreen, setHasUnsavedChanges } = useStore()
  const [timezone, setTimezone] = useState('')
  const [quietStart, setQuietStart] = useState('23:00')
  const [quietEnd, setQuietEnd] = useState('08:00')
  const [dayStartTime, setDayStartTime] = useState('08:00')
  const [dayEndTime, setDayEndTime] = useState('23:50')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [initial, setInitial] = useState<Record<string, string> | null>(null)

  // Timezone picker state
  const [tzOpen, setTzOpen] = useState(false)
  const [tzSearch, setTzSearch] = useState('')
  const tzRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (user) {
      setTimezone(user.timezone)
      setQuietStart(user.quiet_start)
      setQuietEnd(user.quiet_end)
      setDayStartTime(user.day_start_time || '08:00')
      setDayEndTime(user.day_end_time)
      setInitial({
        timezone: user.timezone,
        quiet_start: user.quiet_start,
        quiet_end: user.quiet_end,
        day_start_time: user.day_start_time || '08:00',
        day_end_time: user.day_end_time,
      })
    }
  }, [user])

  // Отслеживание изменений
  useEffect(() => {
    if (!initial) return
    const changed =
      timezone !== initial.timezone ||
      quietStart !== initial.quiet_start ||
      quietEnd !== initial.quiet_end ||
      dayStartTime !== initial.day_start_time ||
      dayEndTime !== initial.day_end_time
    setHasChanges(changed)
    setHasUnsavedChanges(changed)
  }, [timezone, quietStart, quietEnd, dayStartTime, dayEndTime, initial])

  // Сброс флага при размонтировании
  useEffect(() => {
    return () => { setHasUnsavedChanges(false) }
  }, [])

  // Закрытие dropdown при клике вне
  useEffect(() => {
    if (!tzOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (tzRef.current && !tzRef.current.contains(e.target as Node)) {
        setTzOpen(false)
        setTzSearch('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [tzOpen])

  // Автофокус на поиск при открытии
  useEffect(() => {
    if (tzOpen && searchRef.current) {
      searchRef.current.focus()
    }
  }, [tzOpen])

  // Сортировка и фильтрация таймзон
  const detectedTz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, [])

  // Найти tz из списка с таким же offset как у detected (для автовыбора)
  const detectedMatch = useMemo(() => {
    const exact = TIMEZONE_DATA.find((t) => t.tz === detectedTz)
    if (exact) return exact.tz
    // Ищем по совпадению offset
    const detectedOffset = getOffsetMinutes(detectedTz)
    const match = TIMEZONE_DATA.find((t) => getOffsetMinutes(t.tz) === detectedOffset)
    return match?.tz || detectedTz
  }, [detectedTz])

  const sortedTimezones = useMemo(() => {
    return [...TIMEZONE_DATA].sort((a, b) => getOffsetMinutes(a.tz) - getOffsetMinutes(b.tz))
  }, [])

  const filteredTimezones = useMemo(() => {
    if (!tzSearch.trim()) return sortedTimezones
    const q = tzSearch.toLowerCase()
    return sortedTimezones.filter((t) =>
      t.tz.toLowerCase().includes(q) ||
      t.cities.toLowerCase().includes(q) ||
      getUtcOffset(t.tz).toLowerCase().includes(q)
    )
  }, [tzSearch, sortedTimezones])

  const handleSave = async () => {
    if (dayStartTime >= dayEndTime) {
      alert('Начало дня должно быть раньше конца дня')
      return
    }
    setSaving(true)
    try {
      await api.updateSettings({
        timezone,
        quiet_start: quietStart,
        quiet_end: quietEnd,
        day_start_time: dayStartTime,
        day_end_time: dayEndTime,
      })
      await loadUser()
      setHasChanges(false)
      setHasUnsavedChanges(false)
      setInitial({
        timezone, quiet_start: quietStart, quiet_end: quietEnd,
        day_start_time: dayStartTime, day_end_time: dayEndTime,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  const handleTzSelect = (tz: string) => {
    setTimezone(tz)
    setTzOpen(false)
    setTzSearch('')
  }

  return (
    <div className="settings-screen">
      <div className="header">
        <h1>⚙️ Настройки</h1>
        {hasChanges ? (
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {saving ? '...' : '💾 Сохранить'}
          </button>
        ) : saved ? (
          <span style={{ color: 'var(--success)', fontSize: 13 }}>✅ Сохранено</span>
        ) : null}
      </div>

      {/* Быстрый доступ к экранам настройки */}
      <div className="settings-nav">
        <button className="btn btn-secondary settings-nav-btn" onClick={() => setScreen('categories')}>
          📁 Категории
        </button>
        <button className="btn btn-secondary settings-nav-btn" onClick={() => setScreen('schedule')}>
          📅 Расписание
        </button>
        <button className="btn btn-secondary settings-nav-btn" onClick={() => setScreen('goals')}>
          🎯 Цели
        </button>
      </div>

      <div className="settings-section card">
        <h3>🌍 Часовой пояс</h3>
        <div className="tz-picker" ref={tzRef}>
          <button
            className="tz-picker-trigger input"
            onClick={() => setTzOpen(!tzOpen)}
            type="button"
          >
            <span className="tz-picker-value">
              {formatTimezone(timezone)}
            </span>
            <span className={`tz-picker-arrow ${tzOpen ? 'open' : ''}`}>▾</span>
          </button>

          {tzOpen && (
            <div className="tz-picker-dropdown">
              <input
                ref={searchRef}
                className="tz-picker-search"
                type="text"
                placeholder="Поиск: город, страна, UTC..."
                value={tzSearch}
                onChange={(e) => setTzSearch(e.target.value)}
              />
              <div className="tz-picker-list">
                {/* Автоопределённый */}
                {!tzSearch && (
                  <button
                    className={`tz-picker-item tz-picker-item-detected ${timezone === detectedMatch ? 'selected' : ''}`}
                    onClick={() => handleTzSelect(detectedMatch)}
                  >
                    <span className="tz-picker-item-label">
                      🎯 Автоопределённый: {getUtcOffset(detectedTz)} ({detectedTz.split('/').pop()?.replace(/_/g, ' ')})
                    </span>
                  </button>
                )}

                {filteredTimezones.map((t) => (
                  <button
                    key={t.tz}
                    className={`tz-picker-item ${timezone === t.tz ? 'selected' : ''}`}
                    onClick={() => handleTzSelect(t.tz)}
                  >
                    <span className="tz-picker-item-offset">{getUtcOffset(t.tz)}</span>
                    <span className="tz-picker-item-cities">{t.cities}</span>
                    {t.hasDST && <span className="tz-picker-item-dst" title="Переводят часы">🔄</span>}
                  </button>
                ))}

                {filteredTimezones.length === 0 && (
                  <div className="tz-picker-empty">
                    Ничего не найдено
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
        <p className="hint" style={{ marginTop: 6 }}>
          Автоопределён: {getUtcOffset(detectedTz)} ({detectedTz.split('/').pop()?.replace(/_/g, ' ')})
        </p>
      </div>

      <div className="settings-section card">
        <h3>🕐 Начало и конец дня</h3>
        <p className="hint" style={{ marginBottom: 8 }}>
          Определяет диапазон слотов в календаре
        </p>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label className="label">Начало</label>
            <select className="input" value={dayStartTime} onChange={(e) => setDayStartTime(e.target.value)}>
              {TIME_SLOTS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">Конец</label>
            <select className="input" value={dayEndTime} onChange={(e) => setDayEndTime(e.target.value)}>
              {TIME_SLOTS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>
        {dayStartTime >= dayEndTime && (
          <p className="hint" style={{ color: 'var(--danger)', marginTop: 4 }}>
            ⚠️ Начало дня должно быть раньше конца
          </p>
        )}
      </div>

      <div className="settings-section card">
        <h3>🔇 Тихое время</h3>
        <p className="hint" style={{ marginBottom: 8 }}>
          Бот не будет спамить в это время
        </p>
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label className="label">С</label>
            <select className="input" value={quietStart} onChange={(e) => setQuietStart(e.target.value)}>
              {TIME_SLOTS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label className="label">До</label>
            <select className="input" value={quietEnd} onChange={(e) => setQuietEnd(e.target.value)}>
              {TIME_SLOTS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {saved && (
        <div style={{ textAlign: 'center', color: 'var(--success)', padding: 8, fontSize: 14 }}>
          ✅ Настройки сохранены
        </div>
      )}

      <div style={{ height: 80 }} />
    </div>
  )
}
