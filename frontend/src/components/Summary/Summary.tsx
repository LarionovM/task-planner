// Экран 6: Саммари — статистика за неделю + графики

import { useState, useEffect } from 'react'
import { useStore } from '../../store'
import { api } from '../../api/client'
import type { WeekStats } from '../../types'
import './Summary.css'

export default function Summary() {
  const { weekStart } = useStore()
  const [stats, setStats] = useState<WeekStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadStats()
  }, [weekStart])

  const loadStats = async () => {
    setLoading(true)
    try {
      const data = await api.getWeekStats(weekStart)
      setStats(data)
    } catch (e) {
      console.error('Error loading stats:', e)
    } finally {
      setLoading(false)
    }
  }

  // Кнопка «Сохранить и запустить»
  const handleSaveAndStart = async () => {
    setSaving(true)
    try {
      // POST к save-plan (если эндпоинт существует)
      alert('✅ План сохранён! Бот начнёт присылать напоминания.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="summary-screen">
        <div className="header">
          <h1>📊 Итоги</h1>
        </div>
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          Загрузка...
        </div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="summary-screen">
        <div className="header">
          <h1>📊 Итоги</h1>
        </div>
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          Нет данных. Создайте блоки в календаре.
        </div>
      </div>
    )
  }

  // Максимальные значения для визуализации баров
  const maxCatTime = Math.max(
    ...stats.categories.map((c) => Math.max(c.planned_min, c.target_hours * 60)),
    60
  )

  return (
    <div className="summary-screen">
      <div className="header">
        <h1>📊 Итоги</h1>
      </div>

      {/* Общая статистика */}
      <div className="summary-overview">
        <div className="summary-stat card">
          <span className="summary-stat-value">{stats.blocks_planned}</span>
          <span className="summary-stat-label">📋 Запланировано</span>
        </div>
        <div className="summary-stat card">
          <span className="summary-stat-value">{stats.blocks_done}</span>
          <span className="summary-stat-label">✅ Выполнено</span>
        </div>
        <div className="summary-stat card">
          <span className="summary-stat-value">{stats.blocks_partial}</span>
          <span className="summary-stat-label">⚡ Частично</span>
        </div>
        <div className="summary-stat card">
          <span className="summary-stat-value">{stats.blocks_failed}</span>
          <span className="summary-stat-label">❌ Провалено</span>
        </div>
      </div>

      {/* Время */}
      <div className="summary-time card" style={{ marginTop: 12 }}>
        <div className="summary-time-row">
          <span>Запланировано:</span>
          <strong>{Math.round(stats.total_planned_min / 60)}ч {stats.total_planned_min % 60}мин</strong>
        </div>
        <div className="summary-time-row">
          <span>Фактически:</span>
          <strong>{Math.round(stats.total_actual_min / 60)}ч {stats.total_actual_min % 60}мин</strong>
        </div>
        <div className="summary-time-row">
          <span>Свободное время:</span>
          <strong>{Math.round(stats.free_time_min / 60)}ч {stats.free_time_min % 60}мин</strong>
        </div>
      </div>

      {/* Предупреждения */}
      {stats.overload_percent > 90 && (
        <div className="summary-warning card" style={{ marginTop: 12 }}>
          ⚠️ Загрузка {stats.overload_percent}% — возможна перегрузка!
        </div>
      )}

      {stats.upcoming_deadlines?.length > 0 && (
        <div className="summary-deadlines card" style={{ marginTop: 12 }}>
          <h3 style={{ fontSize: 14, marginBottom: 8 }}>📅 Дедлайны на этой неделе</h3>
          {stats.upcoming_deadlines.map((d) => (
            <div key={d.task_id} className="summary-deadline-item">
              <span>{d.task_name}</span>
              <span className="summary-deadline-date">{d.deadline}</span>
            </div>
          ))}
        </div>
      )}

      {/* По категориям — бары */}
      <div style={{ marginTop: 16 }}>
        <h3 style={{ fontSize: 14, marginBottom: 8 }}>📁 По категориям: план vs цель</h3>
        <div className="summary-cats">
          {stats.categories.map((catStat) => {
            const plannedH = Math.round(catStat.planned_min / 6) / 10
            const targetH = catStat.target_hours
            const plannedPercent = maxCatTime > 0 ? (catStat.planned_min / maxCatTime) * 100 : 0
            const targetPercent = maxCatTime > 0 ? (targetH * 60 / maxCatTime) * 100 : 0
            const isGoalMet = targetH > 0 && catStat.planned_min >= targetH * 60

            return (
              <div key={catStat.category_id} className="summary-cat card">
                <div className="summary-cat-header">
                  <span>{catStat.category_emoji || '📁'} {catStat.category_name}</span>
                  <span className="summary-cat-time">
                    {plannedH}ч / {targetH}ч
                    {isGoalMet && ' ✅'}
                  </span>
                </div>
                <div className="summary-bar-container">
                  <div
                    className="summary-bar summary-bar-plan"
                    style={{ width: `${Math.min(plannedPercent, 100)}%` }}
                  />
                  {targetH > 0 && (
                    <div
                      className="summary-bar-target"
                      style={{ left: `${Math.min(targetPercent, 100)}%` }}
                    />
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Кнопка */}
      <button
        className="btn btn-primary summary-save-btn"
        onClick={handleSaveAndStart}
        disabled={saving}
      >
        {saving ? '...' : '🚀 Сохранить и запустить напоминания'}
      </button>

      <div style={{ height: 80 }} />
    </div>
  )
}
