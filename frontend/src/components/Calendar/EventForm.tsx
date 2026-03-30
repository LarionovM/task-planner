// Форма создания/редактирования события (созвоны, встречи)
// v1.2.0: события — отдельная сущность, не задача, не в статистике

import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import type { Event, Category } from '../../types'

interface EventFormProps {
  day: string
  time: string
  editEvent: Event | null
  catMap: Record<number, Category>
  onClose: () => void
  onSaved: () => void
}

export default function EventForm({
  day,
  time,
  editEvent,
  catMap,
  onClose,
  onSaved,
}: EventFormProps) {
  const [name, setName] = useState('')
  const [eventDay, setEventDay] = useState(day)
  const [startTime, setStartTime] = useState(time)
  const [endTime, setEndTime] = useState(() => {
    // Дефолт: +1 час от начала
    const [h, m] = time.split(':').map(Number)
    const endH = Math.min(23, h + 1)
    return `${String(endH).padStart(2, '0')}:${String(m).padStart(2, '0')}`
  })
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [reminderBefore, setReminderBefore] = useState(5)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const categories = Object.values(catMap)

  // Заполнить при редактировании
  useEffect(() => {
    if (editEvent) {
      setName(editEvent.name)
      setEventDay(editEvent.day)
      setStartTime(editEvent.start_time)
      setEndTime(editEvent.end_time)
      setCategoryId(editEvent.category_id || '')
      setReminderBefore(editEvent.reminder_before_min)
      setNotes(editEvent.notes || '')
    }
  }, [editEvent])

  const handleSave = async () => {
    if (!name.trim()) {
      alert('Введите название события')
      return
    }

    setSaving(true)
    try {
      const data: any = {
        name: name.trim(),
        day: eventDay,
        start_time: startTime,
        end_time: endTime,
        category_id: categoryId || null,
        reminder_before_min: reminderBefore,
        notes: notes.trim() || null,
      }

      if (editEvent) {
        await api.updateEvent(editEvent.id, data)
      } else {
        await api.createEvent(data)
      }
      onSaved()
    } catch (e: any) {
      alert(e.message || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  // Валидация: конец позже начала
  const isValid = name.trim().length > 0 && endTime > startTime

  // Длительность в минутах
  const durationMin = (() => {
    const [sh, sm] = startTime.split(':').map(Number)
    const [eh, em] = endTime.split(':').map(Number)
    return (eh * 60 + em) - (sh * 60 + sm)
  })()

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dialog" onMouseDown={(e) => e.stopPropagation()} style={{ maxHeight: '85vh', overflowY: 'auto' }}>
        <h3>{editEvent ? '✏️ Редактировать событие' : '📅 Новое событие'}</h3>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: -8, marginBottom: 12 }}>
          Созвоны, встречи, приёмы — фиксированные по времени.
          Во время события помодоро работает в тихом режиме.
        </p>

        <div className="block-form">
          <label className="label">Название *</label>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Созвон с командой, врач, и т.д."
            autoFocus
          />

          <label className="label">Категория</label>
          <select
            className="input"
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value ? parseInt(e.target.value) : '')}
          >
            <option value="">— без категории —</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.emoji || '📁'} {cat.name}
              </option>
            ))}
          </select>

          <div className="block-form-row">
            <div>
              <label className="label">Дата</label>
              <input
                className="input"
                type="date"
                value={eventDay}
                onChange={(e) => setEventDay(e.target.value)}
              />
            </div>
          </div>

          <div className="block-form-row">
            <div>
              <label className="label">Начало</label>
              <input
                className="input"
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                step={1800}
              />
            </div>
            <div>
              <label className="label">Конец</label>
              <input
                className="input"
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                step={1800}
              />
            </div>
          </div>

          {durationMin > 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: -4 }}>
              ⏱ Длительность: {durationMin} мин ({Math.floor(durationMin / 60)}ч {durationMin % 60}м)
            </div>
          )}
          {durationMin <= 0 && (
            <div style={{ fontSize: 12, color: 'var(--error, red)', marginTop: -4 }}>
              ⚠️ Время окончания должно быть позже начала
            </div>
          )}

          <label className="label">Напомнить за (мин)</label>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {[0, 5, 10, 15, 30, 60].map((min) => (
              <button
                key={min}
                type="button"
                className={`btn btn-sm ${reminderBefore === min ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setReminderBefore(min)}
              >
                {min === 0 ? 'Без' : `${min}м`}
              </button>
            ))}
          </div>
          <span className="hint">Для важных событий (самолёт, врач) — ставьте больше</span>

          <label className="label">Заметки</label>
          <textarea
            className="input"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Ссылка на созвон, повестка, и т.д."
            rows={3}
            style={{ resize: 'vertical', fontFamily: 'inherit' }}
          />
        </div>

        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving || !isValid}
          >
            {saving ? '...' : editEvent ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  )
}
