// Боковая панель бэклога — перетаскивание задач на дни в календаре
// v1.2.0: задачи назначаются на день (scheduled_date), без конкретного времени

import { useMemo, useState } from 'react'
import { useDraggable } from '@dnd-kit/core'
import type { Task, Category } from '../../types'

type SortMode = 'priority' | 'deadline' | 'category' | 'name' | 'status'

const SORT_OPTIONS: { value: SortMode; label: string; icon: string }[] = [
  { value: 'priority', label: 'Приоритет', icon: '🔴' },
  { value: 'status', label: 'Статус', icon: '📊' },
  { value: 'deadline', label: 'Дедлайн', icon: '📅' },
  { value: 'category', label: 'Категория', icon: '📁' },
  { value: 'name', label: 'Имя', icon: '🔤' },
]

const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 }
const STATUS_ORDER: Record<string, number> = { in_progress: 0, grooming: 1, blocked: 2, done: 3 }
const STATUS_ICONS: Record<string, string> = {
  grooming: '📝',
  in_progress: '🔄',
  blocked: '🚫',
  done: '✅',
}

function sortTasks(tasks: Task[], mode: SortMode, catMap: Record<number, Category>): Task[] {
  return [...tasks].sort((a, b) => {
    switch (mode) {
      case 'priority':
        return (PRIORITY_ORDER[a.priority] ?? 1) - (PRIORITY_ORDER[b.priority] ?? 1)
      case 'status':
        return (STATUS_ORDER[a.status] ?? 1) - (STATUS_ORDER[b.status] ?? 1)
      case 'deadline': {
        if (!a.deadline && !b.deadline) return 0
        if (!a.deadline) return 1
        if (!b.deadline) return -1
        return a.deadline.localeCompare(b.deadline)
      }
      case 'category': {
        const catA = catMap[a.category_id]?.name || ''
        const catB = catMap[b.category_id]?.name || ''
        return catA.localeCompare(catB)
      }
      case 'name':
        return a.name.localeCompare(b.name)
      default:
        return 0
    }
  })
}

interface BacklogPanelProps {
  tasks: Task[]
  catMap: Record<number, Category>
}

function DraggableTask({
  task,
  catMap,
}: {
  task: Task
  catMap: Record<number, Category>
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `task-${task.id}`,
    data: { type: 'task', task },
  })

  const cat = catMap[task.category_id]
  const priorityDot = task.priority === 'high' ? '🔴' : task.priority === 'low' ? '🟢' : ''

  return (
    <div
      ref={setNodeRef}
      className="backlog-panel-item"
      style={{ opacity: isDragging ? 0.4 : 1 }}
      {...listeners}
      {...attributes}
    >
      <span>{STATUS_ICONS[task.status] || '📝'}</span>
      <span>{cat?.emoji || '📋'}</span>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {task.name}
      </span>
      {priorityDot && <span style={{ fontSize: 8 }}>{priorityDot}</span>}
      {task.scheduled_date && (
        <span style={{ fontSize: 9, color: 'var(--accent)' }} title={`Назначено: ${task.scheduled_date}`}>
          📅
        </span>
      )}
      {task.estimated_time_min && (
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          {task.estimated_time_min}м
        </span>
      )}
    </div>
  )
}

export default function BacklogPanel({ tasks, catMap }: BacklogPanelProps) {
  const [sortMode, setSortMode] = useState<SortMode>('priority')
  const [showDone, setShowDone] = useState(false)
  const [showScheduled, setShowScheduled] = useState(false)

  // Фильтрация: по умолчанию только незавершённые и ненаназначенные
  const filteredTasks = useMemo(() => {
    let result = tasks.filter((t) => !t.is_epic)
    if (!showDone) {
      result = result.filter((t) => t.status !== 'done')
    }
    if (!showScheduled) {
      result = result.filter((t) => !t.scheduled_date)
    }
    return result
  }, [tasks, showDone, showScheduled])

  const sortedTasks = useMemo(
    () => sortTasks(filteredTasks, sortMode, catMap),
    [filteredTasks, sortMode, catMap]
  )

  const unscheduledCount = tasks.filter((t) => !t.is_epic && !t.scheduled_date && t.status !== 'done').length
  const totalActive = tasks.filter((t) => !t.is_epic && t.status !== 'done').length

  return (
    <div className="backlog-panel">
      <div className="backlog-panel-title">
        📋 Задачи ({unscheduledCount}/{totalActive})
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', padding: '0 8px 4px', lineHeight: 1.3 }}>
        Перетащите задачу на день чтобы назначить
      </div>

      {/* Фильтры */}
      <div style={{ display: 'flex', gap: 4, padding: '0 8px 4px', flexWrap: 'wrap' }}>
        <label style={{ fontSize: 10, display: 'flex', alignItems: 'center', gap: 3, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showScheduled}
            onChange={() => setShowScheduled(!showScheduled)}
            style={{ accentColor: 'var(--accent)' }}
          />
          Назначенные
        </label>
        <label style={{ fontSize: 10, display: 'flex', alignItems: 'center', gap: 3, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showDone}
            onChange={() => setShowDone(!showDone)}
            style={{ accentColor: 'var(--accent)' }}
          />
          Готовые
        </label>
      </div>

      {/* Сортировка */}
      <div className="backlog-sort-bar">
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            className={`backlog-sort-btn${sortMode === opt.value ? ' active' : ''}`}
            onClick={() => setSortMode(opt.value)}
            title={opt.label}
          >
            {opt.icon}
          </button>
        ))}
      </div>

      {/* Список задач */}
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {sortedTasks.map((task) => (
          <DraggableTask key={task.id} task={task} catMap={catMap} />
        ))}
      </div>

      {sortedTasks.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: 8, textAlign: 'center' }}>
          {filteredTasks.length === 0 && unscheduledCount === 0
            ? 'Все задачи назначены или завершены!'
            : 'Нет задач. Создайте во вкладке «Задачи».'}
        </div>
      )}
    </div>
  )
}
