// Часовые пояса — общие константы для TimezoneSelect и Settings

export const TIMEZONE_DATA: { tz: string; cities: string; hasDST?: boolean }[] = [
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
export function getUtcOffset(tz: string): string {
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
export function getOffsetMinutes(tz: string): number {
  try {
    const now = new Date()
    const utcStr = now.toLocaleString('en-US', { timeZone: 'UTC' })
    const tzStr = now.toLocaleString('en-US', { timeZone: tz })
    return (new Date(tzStr).getTime() - new Date(utcStr).getTime()) / 60000
  } catch {
    return 0
  }
}

/** Форматировать часовой пояс для отображения */
export function formatTimezone(tz: string): string {
  const data = TIMEZONE_DATA.find((t) => t.tz === tz)
  const offset = getUtcOffset(tz)
  if (data) return `${offset} (${data.cities})`
  return `${offset} (${tz.split('/').pop()?.replace(/_/g, ' ') || tz})`
}
