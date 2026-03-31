// Колонка дня в календаре — события на временной шкале + задачи дня
// v1.2.0: помодоро-центричная модель

import { useMemo } from 'react'
import { useDroppable } from '@dnd-kit/core'
import type { Event, Task, Category, WeeklyScheduleItem } from '../../types'

interface DayColumnProps {
  day: string
  events: Event[]
  dayTasks: Task[]  // задачи, назначенные на этот день
  schedule?: WeeklyScheduleItem
  catMap: Record<number, Category>
  dayStartTime: string
  dayEndTime: string
  onEventClick: (event: Event) => void
  onAddEvent: (day: string, time: string) => void
  onDeleteEvent: (eventId: number) => void
  onUnscheduleTask: (taskId: number) => void
  onTaskStatusChange: (taskId: number, status: string) => void
  onAssignTask?: (day: string) => void
}

const STATUS_ICONS: Record<string, string> = {
  grooming: '📝',
  in_progress: '🔄',
  blocked: '🚫',
  done: '✅',
}

const PRIORITY_DOTS: Record<string, string> = {
  high: '🔴',
  medium: '',
  low: '🟢',
}

const NEXT_STATUS: Record<string, string> = {
  grooming: 'in_progress',
  in_progress: 'done',
  blocked: 'in_progress',
  done: 'grooming',
}

// Генерация 30-минутных слотов
function generateSlots(dayStartTime: string, dayEndTime: string): string[] {
  const startHour = parseInt(dayStartTime.split(':')[0])
  const startMin = parseInt(dayStartTime.split(':')[1])
  const endHour = parseInt(dayEndTime.split(':')[0])
  const endMin = parseInt(dayEndTime.split(':')[1])

  const slots: string[] = []
  let h = startHour, m = startMin
  while (h < endHour || (h === endHour && m < endMin)) {
    slots.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`)
    m += 30
    if (m >= 60) { m = 0; h++ }
  }
  return slots
}

// Длительность события в минутах
function getEventDuration(event: Event): number {
  const [sh, sm] = event.start_time.split(':').map(Number)
  const [eh, em] = event.end_time.split(':').map(Number)
  return (eh * 60 + em) - (sh * 60 + sm)
}

function getEventColor(event: Event, catMap: Record<number, Category>): string {
  if (event.category_id) {
    const cat = catMap[event.category_id]
    if (cat?.color) return cat.color
  }
  return 'var(--accent)'
}

// Droppable слот для событий
function TimeSlot({
  day,
  time,
  children,
  onAdd,
}: {
  day: string
  time: string
  children?: React.ReactNode
  onAdd: () => void
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `slot-${day}-${time}`,
    data: { type: 'slot', day, time },
  })

  return (
    <div
      ref={setNodeRef}
      className={`day-slot ${isOver ? 'droppable' : ''}`}
    >
      <span className="day-slot-time">{time}</span>
      {children}
      {!children && (
        <button className="day-slot-add" onClick={onAdd}>+</button>
      )}
    </div>
  )
}

// Блок события на шкале
function EventBlock({
  event,
  color,
  slotsCount,
  catMap,
  onEventClick,
  onDeleteEvent,
}: {
  event: Event
  color: string
  slotsCount: number
  catMap: Record<number, Category>
  onEventClick: (event: Event) => void
  onDeleteEvent: (eventId: number) => void
}) {
  const cat = event.category_id ? catMap[event.category_id] : null
  const statusIcon = event.status === 'done' ? '✅' : event.status === 'active' ? '🟢' : '📅'

  return (
    <div
      className={`cal-block status-${event.status}`}
      style={{
        borderLeftColor: color,
        height: `${slotsCount * 28 - 2}px`,
        cursor: 'pointer',
      }}
      title={`${event.name}\n${event.start_time}–${event.end_time}${event.notes ? '\n' + event.notes : ''}`}
      onClick={() => onEventClick(event)}
    >
      <div className="cal-block-name">
        {statusIcon} {cat?.emoji || '📅'} {event.name}
      </div>
      <div className="cal-block-time">
        {event.start_time}–{event.end_time}
      </div>
      <button
        className="cal-block-delete"
        onClick={(e) => { e.stopPropagation(); onDeleteEvent(event.id) }}
      >
        ✕
      </button>
    </div>
  )
}

// Droppable зона для перетаскивания задач на день
function DayDropZone({ day }: { day: string }) {
  const { setNodeRef, isOver } = useDroppable({
    id: `day-drop-${day}`,
    data: { type: 'day-drop', day },
  })

  return (
    <div
      ref={setNodeRef}
      className={`day-task-drop-zone ${isOver ? 'droppable' : ''}`}
      style={{
        minHeight: 28,
        padding: '2px 4px',
        borderRadius: 4,
        border: isOver ? '2px dashed var(--accent)' : '2px dashed transparent',
        transition: 'border-color 0.15s',
        fontSize: 10,
        color: 'var(--text-muted)',
        textAlign: 'center',
      }}
    >
      {isOver ? '📥 Назначить сюда' : ''}
    </div>
  )
}

export default function DayColumn({
  day, events, dayTasks, schedule, catMap,
  dayStartTime, dayEndTime,
  onEventClick, onAddEvent, onDeleteEvent,
  onUnscheduleTask, onTaskStatusChange, onAssignTask,
}: DayColumnProps) {
  const slots = generateSlots(dayStartTime, dayEndTime)

  // Маппинг событий на слоты
  const eventAtSlot: Record<string, Event> = {}
  const occupiedSlots = new Set<string>()

  events.forEach((event) => {
    eventAtSlot[event.start_time] = event
    const duration = getEventDuration(event)
    const [bh, bm] = event.start_time.split(':').map(Number)
    const startMin = bh * 60 + bm
    const slotsCount = Math.ceil(duration / 30)
    for (let i = 1; i < slotsCount; i++) {
      const min = startMin + i * 30
      const h = Math.floor(min / 60)
      const m = min % 60
      const slotKey = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
      occupiedSlots.add(slotKey)
    }
  })

  // Задачи дня, отсортированные по приоритету
  const sortedTasks = useMemo(() => {
    const order: Record<string, number> = { high: 0, medium: 1, low: 2 }
    return [...dayTasks].sort((a, b) => (order[a.priority] ?? 1) - (order[b.priority] ?? 1))
  }, [dayTasks])

  return (
    <div className={`day-column ${schedule?.is_day_off ? 'day-off-column' : ''}`}>
      {/* Временная шкала с событиями */}
      {slots.map((time) => {
        const event = eventAtSlot[time]
        const isOccupied = occupiedSlots.has(time)
        if (isOccupied) return null

        if (event) {
          const duration = getEventDuration(event)
          const slotsCount = Math.max(1, Math.ceil(duration / 30))
          const color = getEventColor(event, catMap)

          return (
            <TimeSlot key={time} day={day} time={time} onAdd={() => onAddEvent(day, time)}>
              <EventBlock
                event={event}
                color={color}
                slotsCount={slotsCount}
                catMap={catMap}
                onEventClick={onEventClick}
                onDeleteEvent={onDeleteEvent}
              />
            </TimeSlot>
          )
        }

        return <TimeSlot key={time} day={day} time={time} onAdd={() => onAddEvent(day, time)} />
      })}

      {/* Задачи назначенные на этот день */}
      {(sortedTasks.length > 0 || true) && (
        <div className="day-tasks-section">
          <div style={{
            fontSize: 10, fontWeight: 600, color: 'var(--text-muted)',
            padding: '6px 4px 2px', borderTop: '1px solid var(--border)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span>🍅 Задачи на день ({sortedTasks.length})</span>
            {onAssignTask && (
              <button
                onClick={() => onAssignTask(day)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontSize: 14, color: 'var(--accent)', padding: 0, lineHeight: 1,
                }}
                title="Назначить задачу на этот день"
              >+</button>
            )}
          </div>

          <DayDropZone day={day} />

          {sortedTasks.map((task) => {
            const cat = catMap[task.category_id]
            return (
              <div
                key={task.id}
                className="day-task-item"
                style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 4px', fontSize: 11,
                  borderLeft: `3px solid ${cat?.color || 'var(--accent)'}`,
                  marginBottom: 2, borderRadius: 3,
                  background: 'var(--bg-input)',
                  opacity: task.status === 'done' ? 0.5 : 1,
                }}
              >
                <button
                  onClick={() => onTaskStatusChange(task.id, NEXT_STATUS[task.status] || 'grooming')}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    padding: 0, fontSize: 12, lineHeight: 1,
                  }}
                  title={`Статус: ${task.status}. Нажмите для смены.`}
                >
                  {STATUS_ICONS[task.status] || '📝'}
                </button>
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {cat?.emoji || '📋'} {task.name}
                </span>
                {PRIORITY_DOTS[task.priority] && (
                  <span style={{ fontSize: 7 }}>{PRIORITY_DOTS[task.priority]}</span>
                )}
                {task.estimated_time_min && (
                  <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>
                    ~{task.estimated_time_min}м
                  </span>
                )}
                <button
                  onClick={() => onUnscheduleTask(task.id)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    padding: 0, fontSize: 10, color: 'var(--text-muted)',
                  }}
                  title="Убрать с этого дня"
                >
                  ✕
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
