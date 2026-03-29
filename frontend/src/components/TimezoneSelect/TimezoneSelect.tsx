// Экран 0: Выбор часового пояса (первый запуск)

import { useState, useMemo } from 'react'
import { useStore } from '../../store'
import './TimezoneSelect.css'

// Часовые пояса — один на каждый уникальный offset+DST комбинацию
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

/** Получить UTC смещение */
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

/** Числовое смещение для сортировки */
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

export default function TimezoneSelect() {
  const { updateSettings, setScreen } = useStore()
  const detectedTz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, [])
  const [mode, setMode] = useState<'confirm' | 'select'>('confirm')
  const [search, setSearch] = useState('')
  const [saving, setSaving] = useState(false)

  // Найти tz из списка с таким же offset как у detected (для автовыбора)
  const detectedMatch = useMemo(() => {
    const exact = TIMEZONE_DATA.find((t) => t.tz === detectedTz)
    if (exact) return exact.tz
    const detectedOffset = getOffsetMinutes(detectedTz)
    const match = TIMEZONE_DATA.find((t) => getOffsetMinutes(t.tz) === detectedOffset)
    return match?.tz || detectedTz
  }, [detectedTz])

  // Сортированный и фильтрованный список
  const sorted = useMemo(() => {
    return [...TIMEZONE_DATA].sort((a, b) => getOffsetMinutes(a.tz) - getOffsetMinutes(b.tz))
  }, [])

  const filtered = useMemo(() => {
    if (!search) return sorted
    const q = search.toLowerCase()
    return sorted.filter((t) =>
      t.tz.toLowerCase().includes(q) ||
      t.cities.toLowerCase().includes(q) ||
      getUtcOffset(t.tz).toLowerCase().includes(q)
    )
  }, [search, sorted])

  const handleConfirm = async () => {
    setSaving(true)
    await updateSettings({ timezone: detectedMatch })
    setSaving(false)
    setScreen('calendar')
  }

  const handleSelect = async (tz: string) => {
    setSaving(true)
    await updateSettings({ timezone: tz })
    setSaving(false)
    setScreen('calendar')
  }

  if (mode === 'confirm') {
    return (
      <div className="tz-screen">
        <div className="tz-card">
          <div className="tz-icon">🌍</div>
          <h2>Часовой пояс</h2>
          <p className="tz-subtitle">
            Определили автоматически:
          </p>
          <div className="tz-detected">
            {getUtcOffset(detectedTz)} ({detectedTz.split('/').pop()?.replace(/_/g, ' ')})
          </div>
          <p className="tz-hint">
            Это нужно для правильного времени напоминаний
          </p>
          <div className="tz-actions">
            <button
              className="btn btn-primary tz-btn"
              onClick={handleConfirm}
              disabled={saving}
            >
              ✅ Верно
            </button>
            <button
              className="btn btn-secondary tz-btn"
              onClick={() => setMode('select')}
              disabled={saving}
            >
              🔄 Выбрать другой
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="tz-screen">
      <div className="tz-card">
        <div className="tz-icon">🌍</div>
        <h2>Выберите часовой пояс</h2>
        <input
          className="input"
          type="text"
          placeholder="Поиск: город, UTC..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
        <div className="tz-list">
          {filtered.map((t) => (
            <button
              key={t.tz}
              className={`tz-item ${t.tz === detectedTz ? 'tz-item-detected' : ''}`}
              onClick={() => handleSelect(t.tz)}
              disabled={saving}
            >
              <span className="tz-item-offset">{getUtcOffset(t.tz)}</span>
              <span className="tz-item-cities">{t.cities}</span>
              {t.hasDST && <span className="tz-item-dst" title="Переводят часы">🔄</span>}
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="tz-empty">
              Ничего не найдено. Попробуйте другой запрос.
            </div>
          )}
        </div>
        <button
          className="btn btn-secondary"
          onClick={() => setMode('confirm')}
          style={{ marginTop: 12, width: '100%' }}
        >
          ← Назад
        </button>
      </div>
    </div>
  )
}
