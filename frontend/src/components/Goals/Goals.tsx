// Экран 3: Цели по категориям на неделю (ручное сохранение)

import { useState, useEffect } from 'react'
import { useStore } from '../../store'
import { api } from '../../api/client'
import type { WeeklyGoal } from '../../types'
import './Goals.css'

export default function Goals() {
  const { categories, goals, loadGoals, setScreen, setHasUnsavedChanges } = useStore()
  const [localGoals, setLocalGoals] = useState<Record<number, number>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [initialSnapshot, setInitialSnapshot] = useState('')

  useEffect(() => {
    const map: Record<number, number> = {}
    goals.forEach((g) => { map[g.category_id] = g.target_hours })
    categories.forEach((c) => { if (!(c.id in map)) map[c.id] = 0 })
    setLocalGoals(map)
    setInitialSnapshot(JSON.stringify(map))
  }, [goals, categories])

  // Отслеживание изменений
  useEffect(() => {
    if (!initialSnapshot) return
    const changed = JSON.stringify(localGoals) !== initialSnapshot
    setHasChanges(changed)
    setHasUnsavedChanges(changed)
  }, [localGoals, initialSnapshot])

  // Сброс флага при размонтировании
  useEffect(() => {
    return () => { setHasUnsavedChanges(false) }
  }, [])

  const handleChange = (catId: number, hours: number) => {
    setLocalGoals((prev) => ({ ...prev, [catId]: hours }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const goalsArr: WeeklyGoal[] = Object.entries(localGoals).map(([catId, hours]) => ({
        category_id: parseInt(catId), target_hours: hours,
      }))
      await api.updateGoals(goalsArr)
      await loadGoals()
      setInitialSnapshot(JSON.stringify(localGoals))
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

  const totalHours = Object.values(localGoals).reduce((sum, h) => sum + h, 0)

  return (
    <div className="goals-screen">
      <div className="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn-icon" onClick={() => setScreen('settings')}>←</button>
          <h1>🎯 Цели</h1>
        </div>
        {hasChanges ? (
          <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
            {saving ? '...' : '💾 Сохранить'}
          </button>
        ) : saved ? (
          <span style={{ color: 'var(--success)', fontSize: 13 }}>✅ Сохранено</span>
        ) : null}
      </div>

      <p className="hint" style={{ marginBottom: 16 }}>Сколько часов в неделю хотите уделять каждой категории</p>

      <div className="goals-list">
        {categories.map((cat) => {
          const hours = localGoals[cat.id] ?? 0
          return (
            <div key={cat.id} className="goal-item card">
              <div className="goal-header">
                <span className="goal-cat"><span className="goal-emoji">{cat.emoji || '📁'}</span>{cat.name}</span>
                <span className="goal-value">{hours}ч</span>
              </div>
              <input type="range" className="goal-slider" min={0} max={40} step={0.5} value={hours} onChange={(e) => handleChange(cat.id, parseFloat(e.target.value))} />
              <div className="goal-range-labels"><span>0ч</span><span>20ч</span><span>40ч</span></div>
            </div>
          )
        })}
      </div>

      <div className="goals-total card" style={{ marginTop: 16 }}>
        <span>Всего запланировано:</span>
        <strong>{totalHours}ч / неделя</strong>
      </div>

      {categories.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          Сначала создайте категории
        </div>
      )}
      <div style={{ height: 80 }} />
    </div>
  )
}
