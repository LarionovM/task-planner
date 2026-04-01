// Экран 6: Саммари — аналитика по периодам с recharts (v1.4.0)

import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { api } from '../../api/client'
import type { PeriodStatsResponse } from '../../types'
import ThemeToggle from '../ThemeToggle'
import './Summary.css'

type Period = 'day' | 'week' | 'month'

const PERIOD_LABELS: Record<Period, string> = {
  day: 'День',
  week: 'Неделя',
  month: 'Месяц',
}

// Цвета для pie-chart по категориям (циклически)
const CAT_COLORS = [
  '#6C63FF', '#FF6B6B', '#4ECDC4', '#FFD93D',
  '#95E1D3', '#F38181', '#AA96DA', '#FCBAD3',
]

function fmtMin(min: number): string {
  if (min < 60) return `${min}м`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}ч ${m}м` : `${h}ч`
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

// Форматирование дня для оси X
function fmtDay(dateStr: string, period: Period): string {
  const d = new Date(dateStr + 'T00:00:00')
  if (period === 'day') return dateStr
  if (period === 'week') {
    const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    return days[d.getDay() === 0 ? 6 : d.getDay() - 1]
  }
  // month — день месяца
  return String(d.getDate())
}

export default function Summary() {
  const [period, setPeriod] = useState<Period>('week')
  const [refDate, setRefDate] = useState(todayStr())
  const [stats, setStats] = useState<PeriodStatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadStats()
  }, [period, refDate])

  const loadStats = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getPeriodStats(period, refDate)
      setStats(data)
    } catch (e: any) {
      setError(e.message || 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }

  // Навигация периодов
  const navigate = (dir: -1 | 1) => {
    const d = new Date(refDate + 'T00:00:00')
    if (period === 'day') d.setDate(d.getDate() + dir)
    else if (period === 'week') d.setDate(d.getDate() + dir * 7)
    else d.setMonth(d.getMonth() + dir)
    setRefDate(d.toISOString().slice(0, 10))
  }

  const periodLabel = (): string => {
    if (!stats) return ''
    if (stats.date_from === stats.date_to) return stats.date_from
    return `${stats.date_from} — ${stats.date_to}`
  }

  // Данные для bar-chart
  const barData = stats?.by_day.map((d) => ({
    name: fmtDay(d.date, period),
    Выполнено: d.pomodoros_done,
    Всего: d.pomodoros_total - d.pomodoros_done,
  })) ?? []

  // Данные для pie-chart (только категории с временем > 0)
  const pieData = stats?.categories
    .filter((c) => c.actual_min > 0)
    .map((c) => ({
      name: `${c.category_emoji || ''} ${c.category_name}`,
      value: c.actual_min,
    })) ?? []

  return (
    <div className="summary-screen">
      <div className="header">
        <h1>📊 Аналитика</h1>
        <ThemeToggle />
      </div>

      {/* Переключатель периода */}
      <div className="summary-period-tabs">
        {(['day', 'week', 'month'] as Period[]).map((p) => (
          <button
            key={p}
            className={`summary-period-tab ${period === p ? 'active' : ''}`}
            onClick={() => { setPeriod(p); setRefDate(todayStr()) }}
          >
            {PERIOD_LABELS[p]}
          </button>
        ))}
      </div>

      {/* Навигация */}
      <div className="summary-nav">
        <button className="summary-nav-btn" onClick={() => navigate(-1)}>‹</button>
        <span className="summary-nav-label">{periodLabel()}</span>
        <button className="summary-nav-btn" onClick={() => navigate(1)}>›</button>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          Загрузка...
        </div>
      )}

      {error && (
        <div style={{ textAlign: 'center', padding: 20, color: 'var(--danger)' }}>
          {error}
        </div>
      )}

      {!loading && !error && stats && (
        <>
          {/* Карточки помодоро */}
          <div className="summary-cards">
            <div className="summary-card card">
              <span className="summary-card-value">{stats.pomodoros_done}</span>
              <span className="summary-card-label">✅ Выполнено</span>
            </div>
            <div className="summary-card card">
              <span className="summary-card-value">{stats.pomodoros_partial}</span>
              <span className="summary-card-label">⚡ Частично</span>
            </div>
            <div className="summary-card card">
              <span className="summary-card-value">{stats.pomodoros_failed}</span>
              <span className="summary-card-label">❌ Провалено</span>
            </div>
            <div className="summary-card card">
              <span className="summary-card-value">{stats.pomodoros_skipped}</span>
              <span className="summary-card-label">⏭ Пропущено</span>
            </div>
          </div>

          {/* Дополнительные метрики */}
          <div className="summary-metrics card">
            <div className="summary-metric-row">
              <span>⏱ Суммарный фокус</span>
              <strong>{fmtMin(stats.focus_min)}</strong>
            </div>
            <div className="summary-metric-row">
              <span>🔥 Стрик</span>
              <strong>{stats.streak_days} дн.</strong>
            </div>
            <div className="summary-metric-row">
              <span>📈 Среднее в день</span>
              <strong>{stats.avg_per_day} помодоро</strong>
            </div>
            <div className="summary-metric-row">
              <span>🍅 Всего помодоро</span>
              <strong>{stats.pomodoros_total}</strong>
            </div>
          </div>

          {/* Bar chart — помодоро по дням */}
          {barData.length > 1 && (
            <div className="summary-section">
              <h3 className="summary-section-title">📅 По дням</h3>
              <div className="summary-chart-wrap">
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={barData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                      labelStyle={{ color: 'var(--text-primary)' }}
                    />
                    <Bar dataKey="Выполнено" stackId="a" fill="var(--success)" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="Всего" stackId="a" fill="var(--bg-input)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Pie chart — по категориям */}
          {pieData.length > 0 && (
            <div className="summary-section">
              <h3 className="summary-section-title">📁 По категориям</h3>
              <div className="summary-chart-wrap">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="45%"
                      innerRadius={50}
                      outerRadius={80}
                      paddingAngle={2}
                      dataKey="value"
                      label={({ percent }: { percent?: number }) =>
                        (percent ?? 0) > 0.08 ? `${Math.round((percent ?? 0) * 100)}%` : ''
                      }
                      labelLine={false}
                    >
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(v: number | string) => fmtMin(Number(v))}
                      contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                    />
                    <Legend
                      iconSize={10}
                      wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Детализация по категориям */}
              <div className="summary-cat-list">
                {stats.categories
                  .filter((c) => c.actual_min > 0)
                  .sort((a, b) => b.actual_min - a.actual_min)
                  .map((c, i) => {
                    const goalMin = c.target_hours * 60
                    const pct = goalMin > 0 ? Math.min(100, Math.round(c.actual_min / goalMin * 100)) : null
                    return (
                      <div key={c.category_id} className="summary-cat-row">
                        <span
                          className="summary-cat-dot"
                          style={{ background: CAT_COLORS[i % CAT_COLORS.length] }}
                        />
                        <span className="summary-cat-name">
                          {c.category_emoji || '📁'} {c.category_name}
                        </span>
                        <span className="summary-cat-actual">{fmtMin(c.actual_min)}</span>
                        {pct !== null && (
                          <span className={`summary-cat-pct ${pct >= 100 ? 'met' : ''}`}>
                            {pct}% {pct >= 100 ? '✅' : `/ цель ${c.target_hours}ч`}
                          </span>
                        )}
                      </div>
                    )
                  })}
              </div>
            </div>
          )}

          {/* Задачи */}
          {stats.tasks_total > 0 && (
            <div className="summary-section">
              <h3 className="summary-section-title">📋 Задачи</h3>
              <div className="summary-metrics card">
                <div className="summary-metric-row">
                  <span>Всего задач</span>
                  <strong>{stats.tasks_total}</strong>
                </div>
                <div className="summary-metric-row">
                  <span>✅ Завершено</span>
                  <strong>{stats.tasks_done}</strong>
                </div>
                <div className="summary-metric-row">
                  <span>🔵 В работе</span>
                  <strong>{stats.tasks_in_progress}</strong>
                </div>
              </div>
            </div>
          )}

          {/* Дедлайны */}
          {stats.upcoming_deadlines.length > 0 && (
            <div className="summary-section">
              <h3 className="summary-section-title">⚠️ Дедлайны в периоде</h3>
              <div className="card" style={{ padding: '8px 12px' }}>
                {stats.upcoming_deadlines.map((d) => (
                  <div key={d.task_id} className="summary-deadline-row">
                    <span>{d.task_name}</span>
                    <span className="summary-deadline-date">{d.deadline}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Пусто */}
          {stats.pomodoros_total === 0 && (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
              За этот период помодоро не было.<br />
              <small>Завершайте блоки в календаре — здесь появится статистика.</small>
            </div>
          )}
        </>
      )}

      <div style={{ height: 80 }} />
    </div>
  )
}
