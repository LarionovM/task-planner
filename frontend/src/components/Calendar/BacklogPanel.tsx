// Боковая панель бэклога — перетаскивание задач и эпиков в календарь

import { useMemo, useState } from 'react'
import { useDraggable } from '@dnd-kit/core'
import type { Task, Category } from '../../types'

type SortMode = 'priority' | 'deadline' | 'category' | 'name' | 'time'

const SORT_OPTIONS: { value: SortMode; label: string; icon: string }[] = [
  { value: 'priority', label: 'Приоритет', icon: '🔴' },
  { value: 'deadline', label: 'Дедлайн', icon: '📅' },
  { value: 'category', label: 'Категория', icon: '📁' },
  { value: 'name', label: 'Имя', icon: '🔤' },
  { value: 'time', label: 'Время', icon: '⏱' },
]

const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 }

function sortTasks(tasks: Task[], mode: SortMode, catMap: Record<number, Category>): Task[] {
  return [...tasks].sort((a, b) => {
    switch (mode) {
      case 'priority':
        return (PRIORITY_ORDER[a.priority] ?? 1) - (PRIORITY_ORDER[b.priority] ?? 1)
      case 'deadline': {
        // Задачи с дедлайном первые, затем по дате
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
      case 'time':
        return (a.estimated_time_min || 0) - (b.estimated_time_min || 0)
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
      <span>{cat?.emoji || '📋'}</span>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {task.name}
      </span>
      {priorityDot && <span style={{ fontSize: 8 }}>{priorityDot}</span>}
      {task.allow_multi_per_block && (
        <span style={{ fontSize: 9, color: 'var(--accent)' }}>🔄</span>
      )}
      {task.estimated_time_min && (
        <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
          {task.estimated_time_min}м
        </span>
      )}
    </div>
  )
}

function DraggableEpic({
  epic,
  epicTasks,
}: {
  epic: Task
  epicTasks: Task[]
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `epic-${epic.id}`,
    data: { type: 'epic', epic, epicTasks },
  })

  const totalMin = epicTasks.reduce((s, t) => s + (t.estimated_time_min || 5), 0)

  return (
    <div
      ref={setNodeRef}
      className="backlog-panel-item backlog-panel-epic"
      style={{ opacity: isDragging ? 0.4 : 1 }}
      {...listeners}
      {...attributes}
    >
      <span>{epic.epic_emoji || '📦'}</span>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600 }}>
        {epic.name}
      </span>
      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
        {epicTasks.length}шт ~{totalMin}м
      </span>
    </div>
  )
}

export default function BacklogPanel({ tasks, catMap }: BacklogPanelProps) {
  const [sortMode, setSortMode] = useState<SortMode>('priority')
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['recurring', 'onetime']))

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Разделяем на регулярные и разовые, внутри каждой — эпики + standalone
  const buildGroup = (taskList: Task[]) => {
    const allEpics = tasks.filter((t) => t.is_epic)
    const epicIds = new Set(taskList.map((t) => t.epic_id).filter(Boolean) as number[])
    const sectionEpics = allEpics.filter((e) => epicIds.has(e.id))
    const byEpic: Record<number, Task[]> = {}
    taskList.forEach((t) => {
      if (t.epic_id) {
        if (!byEpic[t.epic_id]) byEpic[t.epic_id] = []
        byEpic[t.epic_id].push(t)
      }
    })
    for (const key of Object.keys(byEpic)) {
      byEpic[Number(key)] = sortTasks(byEpic[Number(key)], sortMode, catMap)
    }
    const standalone = sortTasks(taskList.filter((t) => !t.epic_id), sortMode, catMap)
    return { sectionEpics, byEpic, standalone }
  }

  const recurringTasks = useMemo(() => tasks.filter((t) => !t.is_epic && t.is_recurring), [tasks])
  const onetimeTasks = useMemo(() => tasks.filter((t) => !t.is_epic && !t.is_recurring), [tasks])
  const recurringGroups = useMemo(() => buildGroup(recurringTasks), [recurringTasks, sortMode, catMap])
  const onetimeGroups = useMemo(() => buildGroup(onetimeTasks), [onetimeTasks, sortMode, catMap])

  const renderGroup = (key: string, title: string, count: number, groups: ReturnType<typeof buildGroup>) => {
    if (count === 0 && groups.sectionEpics.length === 0) return null
    const isExpanded = expandedSections.has(key)
    return (
      <div style={{ marginBottom: 6 }}>
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: 4, padding: '4px 8px',
            fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
            cursor: 'pointer', userSelect: 'none', borderBottom: '1px solid var(--border)',
          }}
          onClick={() => toggleSection(key)}
        >
          <span style={{ width: 12 }}>{isExpanded ? '▾' : '▸'}</span>
          <span style={{ flex: 1 }}>{title}</span>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', background: 'var(--bg-input)', padding: '0 5px', borderRadius: 8 }}>
            {count}
          </span>
        </div>
        {isExpanded && (
          <div>
            {groups.sectionEpics.map((epic) => {
              const epicTasks = groups.byEpic[epic.id] || []
              if (epicTasks.length === 0) return null
              return (
                <div key={epic.id}>
                  <DraggableEpic epic={epic} epicTasks={epicTasks} />
                  {epicTasks.map((task) => (
                    <div key={task.id} style={{ paddingLeft: 12 }}>
                      <DraggableTask task={task} catMap={catMap} />
                    </div>
                  ))}
                </div>
              )
            })}
            {groups.standalone.map((task) => (
              <DraggableTask key={task.id} task={task} catMap={catMap} />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="backlog-panel">
      <div className="backlog-panel-title">Задачи</div>

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

      {renderGroup('recurring', '🔁 Регулярные', recurringTasks.length, recurringGroups)}
      {renderGroup('onetime', '📌 Разовые', onetimeTasks.length, onetimeGroups)}

      {tasks.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: 8 }}>
          Нет задач. Создайте во вкладке «Задачи».
        </div>
      )}
    </div>
  )
}
