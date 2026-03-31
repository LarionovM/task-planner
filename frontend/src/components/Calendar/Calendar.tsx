// Экран 5: Календарь недели — события на временной шкале + задачи на день
// v1.2.0: помодоро-центричная модель

import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  closestCenter,
  type DragStartEvent,
  type DragEndEvent,
  type CollisionDetection,
} from '@dnd-kit/core'

// Гибридная коллизия: сначала по курсору, потом по центру
const hybridCollision: CollisionDetection = (args) => {
  const pointerHits = pointerWithin(args)
  if (pointerHits.length > 0) return pointerHits
  return closestCenter(args)
}

import { useStore } from '../../store'
import { api } from '../../api/client'
import type { Task, Event, Category } from '../../types'
import DayColumn from './DayColumn'
import BacklogPanel from './BacklogPanel'
import EventForm from './EventForm'
import ThemeToggle from '../ThemeToggle'
import './Calendar.css'

const DAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

type ViewMode = 'week' | 'day'

export default function Calendar() {
  const {
    events, tasks, categories, schedule, weekStart, setWeekStart,
    loadEvents, loadTasks, user,
  } = useStore()

  const [viewMode, setViewMode] = useState<ViewMode>(() =>
    window.innerWidth <= 600 ? 'day' : 'week'
  )
  const [selectedDayIndex, setSelectedDayIndex] = useState(() => {
    const today = new Date().getDay()
    return today === 0 ? 6 : today - 1
  })
  const [showBacklog, setShowBacklog] = useState(false)
  const [showEventForm, setShowEventForm] = useState(false)
  const [editEvent, setEditEvent] = useState<Event | null>(null)
  const [dragTask, setDragTask] = useState<Task | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dropDay, setDropDay] = useState<string>('')
  const [dropTime, setDropTime] = useState<string>('')
  const [assignDay, setAssignDay] = useState<string>('')  // день для назначения задачи

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  useEffect(() => { loadEvents(); loadTasks() }, [weekStart])

  const weekDays = useMemo(() => {
    const start = new Date(weekStart + 'T00:00:00')
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(start); d.setDate(d.getDate() + i)
      return formatLocalDate(d)
    })
  }, [weekStart])

  // События по дням
  const eventsByDay = useMemo(() => {
    const map: Record<string, Event[]> = {}
    weekDays.forEach((d) => (map[d] = []))
    events.forEach((e) => { if (map[e.day]) map[e.day].push(e) })
    return map
  }, [events, weekDays])

  // Задачи назначенные на конкретные дни
  const tasksByDay = useMemo(() => {
    const map: Record<string, Task[]> = {}
    weekDays.forEach((d) => (map[d] = []))
    tasks.forEach((t) => {
      if (t.scheduled_date && map[t.scheduled_date] && t.status !== 'done') {
        map[t.scheduled_date].push(t)
      }
    })
    return map
  }, [tasks, weekDays])

  const catMap = useMemo(() => {
    const m: Record<number, Category> = {}
    categories.forEach((c) => (m[c.id] = c))
    return m
  }, [categories])

  // Расширение временных рамок если есть события за пределами дня
  const [effectiveStart, effectiveEnd] = useMemo(() => {
    let startMin = user?.day_start_time || '08:00'
    let endMin = user?.day_end_time || '23:50'

    for (const ev of events) {
      if (ev.start_time < startMin) {
        const [h, m] = ev.start_time.split(':').map(Number)
        const rounded = Math.floor(m / 30) * 30
        startMin = `${String(h).padStart(2, '0')}:${String(rounded).padStart(2, '0')}`
      }
      if (ev.end_time > endMin) {
        const [h, m] = ev.end_time.split(':').map(Number)
        const rounded = Math.ceil(m / 30) * 30
        const endH = rounded >= 60 ? h + 1 : h
        const endM = rounded >= 60 ? 0 : rounded
        endMin = `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`
      }
    }

    return [startMin, endMin]
  }, [events, user?.day_start_time, user?.day_end_time])

  const prevWeek = () => {
    const d = new Date(weekStart + 'T00:00:00'); d.setDate(d.getDate() - 7)
    setWeekStart(formatLocalDate(d))
  }
  const nextWeek = () => {
    const d = new Date(weekStart + 'T00:00:00'); d.setDate(d.getDate() + 7)
    setWeekStart(formatLocalDate(d))
  }
  const toCurrentWeek = () => {
    const d = new Date(); const day = d.getDay()
    const diff = d.getDate() - day + (day === 0 ? -6 : 1)
    const monday = new Date(d.setDate(diff))
    setWeekStart(formatLocalDate(monday))
    const today = new Date().getDay()
    setSelectedDayIndex(today === 0 ? 6 : today - 1)
  }

  const prevDay = useCallback(() => {
    if (selectedDayIndex > 0) {
      setSelectedDayIndex(selectedDayIndex - 1)
    } else {
      const d = new Date(weekStart + 'T00:00:00'); d.setDate(d.getDate() - 7)
      setWeekStart(formatLocalDate(d))
      setSelectedDayIndex(6)
    }
  }, [selectedDayIndex, weekStart])

  const nextDay = useCallback(() => {
    if (selectedDayIndex < 6) {
      setSelectedDayIndex(selectedDayIndex + 1)
    } else {
      const d = new Date(weekStart + 'T00:00:00'); d.setDate(d.getDate() + 7)
      setWeekStart(formatLocalDate(d))
      setSelectedDayIndex(0)
    }
  }, [selectedDayIndex, weekStart])

  const toToday = useCallback(() => {
    const d = new Date(); const day = d.getDay()
    const diff = d.getDate() - day + (day === 0 ? -6 : 1)
    const monday = new Date(d); monday.setDate(diff)
    setWeekStart(formatLocalDate(monday))
    const todayIdx = d.getDay()
    setSelectedDayIndex(todayIdx === 0 ? 6 : todayIdx - 1)
  }, [])

  const handleDragStart = (event: DragStartEvent) => {
    const { active } = event
    setDragTask(null)
    if (active.data.current?.type === 'task') {
      setDragTask(active.data.current.task)
      setIsDragging(true)
    }
  }

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event
    const droppedTask = dragTask
    setDragTask(null)
    setIsDragging(false)

    if (!over || !droppedTask) return
    const overData = over.data.current

    // Задача из бэклога -> день (назначить scheduled_date)
    if (active.data.current?.type === 'task' && overData?.type === 'day-drop') {
      const targetDay = overData.day as string
      try {
        await api.updateTask(droppedTask.id, { scheduled_date: targetDay })
        await loadTasks()
      } catch (e: any) {
        alert(e.message || 'Ошибка назначения задачи')
      }
    }

    // Задача из бэклога -> слот (создать событие)
    if (active.data.current?.type === 'task' && overData?.type === 'slot') {
      setDropDay(overData.day as string)
      setDropTime(overData.time as string)
      setEditEvent(null)
      setShowEventForm(true)
    }
  }

  const handleEventClick = (event: Event) => {
    setEditEvent(event)
    setShowEventForm(true)
  }

  const handleDeleteEvent = async (eventId: number) => {
    if (!confirm('Удалить событие?')) return
    await api.deleteEvent(eventId)
    await loadEvents()
  }

  const handleAddEvent = (day: string, time: string) => {
    setDropDay(day)
    setDropTime(time)
    setEditEvent(null)
    setShowEventForm(true)
  }

  // Снять задачу с дня (убрать scheduled_date)
  const handleUnscheduleTask = async (taskId: number) => {
    try {
      await api.updateTask(taskId, { scheduled_date: null })
      await loadTasks()
    } catch (e: any) {
      alert(e.message || 'Ошибка')
    }
  }

  // Назначить задачу на день (из кнопки "+")
  const handleAssignTask = (day: string) => setAssignDay(day)

  const handleAssignConfirm = async (taskId: number) => {
    try {
      await api.updateTask(taskId, { scheduled_date: assignDay })
      await loadTasks()
      setAssignDay('')
    } catch (e: any) {
      alert(e.message || 'Ошибка')
    }
  }

  // Незапланированные задачи для диалога назначения
  const unscheduledTasks = useMemo(
    () => tasks.filter((t) => !t.is_epic && !t.scheduled_date && t.status !== 'done'),
    [tasks]
  )

  // Сменить статус задачи
  const handleTaskStatusChange = async (taskId: number, status: string) => {
    try {
      await api.updateTask(taskId, { status })
      await loadTasks()
    } catch (e: any) {
      alert(e.message || 'Ошибка')
    }
  }

  const formatWeekRange = () => {
    const start = new Date(weekStart + 'T00:00:00')
    const end = new Date(start); end.setDate(end.getDate() + 6)
    const opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }
    return `${start.toLocaleDateString('ru', opts)} — ${end.toLocaleDateString('ru', opts)}`
  }

  const formatDayLabel = (dayStr: string) => {
    const d = new Date(dayStr + 'T00:00:00')
    const opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long', weekday: 'long' }
    return d.toLocaleDateString('ru', opts)
  }

  return (
    <div className={`calendar-screen ${isDragging ? 'is-dragging' : ''}`}>
      <div className="calendar-header">
        <div className="calendar-nav">
          {viewMode === 'week' ? (
            <>
              <button className="btn-icon" onClick={prevWeek}>◀</button>
              <button className="calendar-week-label" onClick={toCurrentWeek}>{formatWeekRange()}</button>
              <button className="btn-icon" onClick={nextWeek}>▶</button>
            </>
          ) : (
            <>
              <button className="btn-icon" onClick={prevDay}>◀</button>
              <button className="calendar-week-label" onClick={toToday}>
                {weekDays[selectedDayIndex] && formatDayLabel(weekDays[selectedDayIndex])}
              </button>
              <button className="btn-icon" onClick={nextDay}>▶</button>
            </>
          )}
        </div>
        <div className="calendar-actions">
          <button
            className={`btn btn-sm ${viewMode === 'day' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode(viewMode === 'week' ? 'day' : 'week')}
            title={viewMode === 'week' ? 'Дневной вид' : 'Недельный вид'}
          >
            {viewMode === 'week' ? '📅' : '📆'}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setShowBacklog(!showBacklog)} title="Панель задач для перетаскивания">
            {showBacklog ? '✕' : '📋'}
          </button>
          <ThemeToggle />
        </div>
      </div>

      <DndContext sensors={sensors} collisionDetection={hybridCollision} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="calendar-body">
          {showBacklog && <BacklogPanel tasks={tasks} catMap={catMap} />}

          {viewMode === 'week' ? (
            <div className="calendar-grid">
              <div className="calendar-day-headers">
                {weekDays.map((day, i) => {
                  const d = new Date(day + 'T00:00:00')
                  const isToday = day === formatLocalDate(new Date())
                  const scheduleDay = schedule.find((s) => s.day_of_week === i)
                  return (
                    <div key={day} className={`calendar-day-header ${isToday ? 'today' : ''}`}>
                      <span className="calendar-day-name">{DAY_SHORT[i]}</span>
                      <span className="calendar-day-date">{d.getDate()}</span>
                      {scheduleDay?.is_day_off && <span className="calendar-day-off">вых</span>}
                    </div>
                  )
                })}
              </div>

              <div className="calendar-columns">
                {weekDays.map((day, i) => (
                  <DayColumn
                    key={day} day={day}
                    events={eventsByDay[day] || []}
                    dayTasks={tasksByDay[day] || []}
                    schedule={schedule.find((s) => s.day_of_week === i)}
                    catMap={catMap}
                    dayStartTime={effectiveStart}
                    dayEndTime={effectiveEnd}
                    onEventClick={handleEventClick}
                    onAddEvent={handleAddEvent}
                    onDeleteEvent={handleDeleteEvent}
                    onUnscheduleTask={handleUnscheduleTask}
                    onTaskStatusChange={handleTaskStatusChange}
                    onAssignTask={handleAssignTask}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="calendar-day-view">
              <div className="day-view-strip">
                {weekDays.map((day, i) => {
                  const d = new Date(day + 'T00:00:00')
                  const isToday = day === formatLocalDate(new Date())
                  const isSelected = i === selectedDayIndex
                  const hasEvents = (eventsByDay[day] || []).length > 0
                  const hasTasks = (tasksByDay[day] || []).length > 0
                  const scheduleDay = schedule.find((s) => s.day_of_week === i)
                  return (
                    <button
                      key={day}
                      className={`day-view-strip-item ${isSelected ? 'selected' : ''} ${isToday ? 'today' : ''}`}
                      onClick={() => setSelectedDayIndex(i)}
                    >
                      <span className="strip-day-name">{DAY_SHORT[i]}</span>
                      <span className="strip-day-date">{d.getDate()}</span>
                      {(hasEvents || hasTasks) && <span className="strip-dot">●</span>}
                      {scheduleDay?.is_day_off && <span className="strip-off">вых</span>}
                    </button>
                  )
                })}
              </div>

              <div className="day-view-column">
                <DayColumn
                  key={weekDays[selectedDayIndex]}
                  day={weekDays[selectedDayIndex]}
                  events={eventsByDay[weekDays[selectedDayIndex]] || []}
                  dayTasks={tasksByDay[weekDays[selectedDayIndex]] || []}
                  schedule={schedule.find((s) => s.day_of_week === selectedDayIndex)}
                  catMap={catMap}
                  dayStartTime={effectiveStart}
                  dayEndTime={effectiveEnd}
                  onEventClick={handleEventClick}
                  onAddEvent={handleAddEvent}
                  onDeleteEvent={handleDeleteEvent}
                  onUnscheduleTask={handleUnscheduleTask}
                  onTaskStatusChange={handleTaskStatusChange}
                />
              </div>
            </div>
          )}
        </div>

        <DragOverlay dropAnimation={null}>
          {dragTask && (
            <div className="backlog-drag-preview">
              {catMap[dragTask.category_id]?.emoji || '📋'} {dragTask.name}
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {showEventForm && (
        <EventForm
          day={dropDay}
          time={dropTime}
          editEvent={editEvent}
          catMap={catMap}
          onClose={() => setShowEventForm(false)}
          onSaved={() => { setShowEventForm(false); loadEvents() }}
        />
      )}

      {/* Диалог назначения задачи на день */}
      {assignDay && (
        <div className="overlay" onClick={() => setAssignDay('')}>
          <div className="dialog" onClick={(e) => e.stopPropagation()} style={{ maxHeight: '70vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <h3>📋 Назначить задачу на {assignDay}</h3>
            {unscheduledTasks.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Нет незапланированных задач</p>
            ) : (
              <div style={{ overflowY: 'auto', flex: 1 }}>
                {unscheduledTasks.map((t) => {
                  const cat = catMap[t.category_id]
                  return (
                    <button
                      key={t.id}
                      onClick={() => handleAssignConfirm(t.id)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        width: '100%', padding: '8px 10px', marginBottom: 4,
                        background: 'var(--bg-input)', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)', cursor: 'pointer',
                        color: 'var(--text-primary)', fontSize: 13, textAlign: 'left',
                      }}
                    >
                      <span>{cat?.emoji || '📋'}</span>
                      <span style={{ flex: 1 }}>{t.name}</span>
                      {t.estimated_time_min && (
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>⏱{t.estimated_time_min}м</span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
            <div className="dialog-actions" style={{ marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setAssignDay('')}>Закрыть</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ height: 80 }} />
    </div>
  )
}
