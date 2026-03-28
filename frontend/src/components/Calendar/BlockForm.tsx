// Форма создания/редактирования блока в календаре

import { useState, useEffect, useMemo } from 'react'
import { api } from '../../api/client'
import type { TaskBlock, Task, Category } from '../../types'

const PRIORITY_WEIGHTS: Record<string, number> = { high: 3, medium: 2, low: 1 }
const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 }

type TaskSortField = 'priority' | 'category' | 'name' | 'time'
const TASK_SORT_OPTIONS: { value: TaskSortField; icon: string; label: string }[] = [
  { value: 'priority', icon: '🔴', label: 'Приоритет' },
  { value: 'category', icon: '📁', label: 'Категория' },
  { value: 'name', icon: '🔤', label: 'Имя' },
  { value: 'time', icon: '⏱', label: 'Время' },
]

interface BlockFormProps {
  day: string
  time: string
  editBlock: TaskBlock | null
  tasks: Task[]
  taskMap: Record<number, Task>
  catMap: Record<number, Category>
  preselectedTaskIds?: number[]
  onClose: () => void
  onSaved: () => void
}

export default function BlockForm({
  day,
  time,
  editBlock,
  tasks,
  taskMap,
  catMap,
  preselectedTaskIds = [],
  onClose,
  onSaved,
}: BlockFormProps) {
  const [taskIds, setTaskIds] = useState<number[]>(preselectedTaskIds)
  const [blockName, setBlockName] = useState('')
  const [startTime, setStartTime] = useState(time)
  const [blockDay, setBlockDay] = useState(day)
  const [durationType, setDurationType] = useState<'fixed' | 'open' | 'range'>('fixed')
  const [durationMin, setDurationMin] = useState<number | ''>(30)
  const [minDurationMin, setMinDurationMin] = useState<number | ''>(15)
  const [maxDurationMin, setMaxDurationMin] = useState<number | ''>(60)
  const [saving, setSaving] = useState(false)

  // Локальная копия задач (для inline-редактирования свойств)
  const [localTasks, setLocalTasks] = useState<Task[]>(tasks)
  useEffect(() => { setLocalTasks(tasks) }, [tasks])

  const localTaskMap = useMemo(() => {
    const m: Record<number, Task> = {}
    for (const t of localTasks) m[t.id] = t
    return m
  }, [localTasks])

  // Сортировка и секции в списке задач
  const [taskSortField, setTaskSortField] = useState<TaskSortField>('priority')
  // Все секции по умолчанию раскрыты (используем «закрытые» вместо «открытых»)
  const [closedSections, setClosedSections] = useState<Set<string>>(new Set())

  const toggleTaskSection = (key: string) => {
    setClosedSections((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const sortTasksList = (list: Task[]): Task[] => {
    return [...list].sort((a, b) => {
      switch (taskSortField) {
        case 'priority':
          return (PRIORITY_ORDER[a.priority] ?? 1) - (PRIORITY_ORDER[b.priority] ?? 1)
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

  const [groupMode, setGroupMode] = useState<'type' | 'category' | 'epic'>('type')

  // Группировка задач для списка выбора
  const nonEpicTasks = useMemo(() => localTasks.filter((t) => !t.is_epic), [localTasks])
  const allEpics = useMemo(() => localTasks.filter((t) => t.is_epic), [localTasks])
  const recurringTaskList = useMemo(() => sortTasksList(nonEpicTasks.filter((t) => t.is_recurring)), [nonEpicTasks, taskSortField, catMap])
  const onetimeTaskList = useMemo(() => sortTasksList(nonEpicTasks.filter((t) => !t.is_recurring)), [nonEpicTasks, taskSortField, catMap])

  // Группировка по категориям
  const tasksByCategory = useMemo(() => {
    const groups: { cat: Category | null; catId: number; tasks: Task[] }[] = []
    const catIds = [...new Set(nonEpicTasks.map((t) => t.category_id))]
    for (const cid of catIds) {
      groups.push({
        cat: catMap[cid] || null,
        catId: cid,
        tasks: sortTasksList(nonEpicTasks.filter((t) => t.category_id === cid)),
      })
    }
    // Сортируем группы по имени категории
    groups.sort((a, b) => (a.cat?.name || '').localeCompare(b.cat?.name || ''))
    return groups
  }, [nonEpicTasks, taskSortField, catMap])

  // Группировка по эпикам
  const tasksByEpic = useMemo(() => {
    const groups: { epic: Task | null; label: string; tasks: Task[] }[] = []
    const epicIds = [...new Set(nonEpicTasks.map((t) => t.epic_id).filter(Boolean))] as number[]
    for (const eid of epicIds) {
      const epic = allEpics.find((e) => e.id === eid) || null
      groups.push({
        epic,
        label: epic ? `${epic.epic_emoji || '📦'} ${epic.name}` : `Группа #${eid}`,
        tasks: sortTasksList(nonEpicTasks.filter((t) => t.epic_id === eid)),
      })
    }
    const standalone = sortTasksList(nonEpicTasks.filter((t) => !t.epic_id))
    if (standalone.length > 0) {
      groups.push({ epic: null, label: '📋 Без группы', tasks: standalone })
    }
    return groups
  }, [nonEpicTasks, allEpics, taskSortField, catMap])

  // Массовый выбор/снятие группы задач
  const toggleGroupTasks = (groupTasks: Task[]) => {
    const groupIds = groupTasks.map((t) => t.id)
    const allSelected = groupIds.every((id) => taskIds.includes(id))
    if (allSelected) {
      // Убрать все
      setTaskIds((prev) => prev.filter((id) => !groupIds.includes(id)))
      setMultiCounts((mc) => {
        const next = { ...mc }
        groupIds.forEach((id) => delete next[id])
        return next
      })
    } else {
      // Добавить недостающие
      setTaskIds((prev) => {
        const existing = new Set(prev)
        const toAdd = groupIds.filter((id) => !existing.has(id))
        return [...prev, ...toAdd]
      })
    }
  }

  // Мульти-задача: количество повторов для каждой задачи
  const [multiCounts, setMultiCounts] = useState<Record<number, number>>({})

  // Уникальные выбранные задачи
  const selectedTasks = useMemo(() => {
    const unique = [...new Set(taskIds)]
    return unique.map((id) => localTaskMap[id]).filter(Boolean)
  }, [taskIds, localTaskMap])

  // Есть ли мульти-задачи среди выбранных
  const hasMultiTasks = useMemo(
    () => selectedTasks.some((t) => t.allow_multi_per_block),
    [selectedTasks]
  )

  // Проверка совместимости device_type
  const deviceTypeWarning = useMemo(() => {
    const types = new Set(selectedTasks.map((t) => t.device_type))
    if (types.size > 1) {
      return 'Задачи имеют разный тип устройства — не рекомендуется объединять'
    }
    return null
  }, [selectedTasks])

  // preferred_time предупреждение
  const preferredTimeWarnings = useMemo(() => {
    const warnings: string[] = []
    for (const t of selectedTasks) {
      if (t.preferred_time && startTime) {
        const [pH, pM] = t.preferred_time.split(':').map(Number)
        const [sH, sM] = startTime.split(':').map(Number)
        const diff = Math.abs((pH * 60 + pM) - (sH * 60 + sM))
        if (diff > 30) {
          warnings.push(`${t.name} — предпочтительное время ${t.preferred_time}`)
        }
      }
    }
    return warnings
  }, [selectedTasks, startTime])

  // Авто-расчёт мульти-распределения (рандом на основе приоритета)
  const recalcDistribution = () => {
    if (!hasMultiTasks || selectedTasks.length === 0) return
    const effectiveDuration = durationType === 'fixed' ? (durationMin || 30) : (maxDurationMin || durationMin || 30)

    if (selectedTasks.length === 1) {
      const t = selectedTasks[0]
      if (t.allow_multi_per_block && t.estimated_time_min) {
        const n = Math.max(1, Math.floor(effectiveDuration / t.estimated_time_min))
        setMultiCounts({ [t.id]: n })
      } else {
        setMultiCounts({ [t.id]: 1 })
      }
      return
    }

    // Несколько задач: рандомное распределение по весу приоритета
    const multi = selectedTasks.filter((t) => t.allow_multi_per_block)
    const single = selectedTasks.filter((t) => !t.allow_multi_per_block)
    const singleTime = single.reduce((s, t) => s + (t.estimated_time_min || 5), 0)
    let remaining = effectiveDuration - singleTime

    const result: Record<number, number> = {}
    single.forEach((t) => { result[t.id] = 1 })

    if (remaining > 0 && multi.length > 0) {
      // Каждой мульти-задаче — минимум 1
      multi.forEach((t) => {
        result[t.id] = 1
        remaining -= (t.estimated_time_min || 5)
      })
      // Оставшееся время раздаём рандомно с весом приоритета
      const weights = multi.map((t) => PRIORITY_WEIGHTS[t.priority] || 2)
      const totalWeight = weights.reduce((s, w) => s + w, 0)
      while (remaining > 0) {
        // Взвешенный рандом
        let r = Math.random() * totalWeight
        let picked = 0
        for (let i = 0; i < multi.length; i++) {
          r -= weights[i]
          if (r <= 0) { picked = i; break }
        }
        const task = multi[picked]
        const dur = task.estimated_time_min || 5
        if (dur <= remaining) {
          result[task.id] = (result[task.id] || 0) + 1
          remaining -= dur
        } else {
          break
        }
      }
    } else {
      multi.forEach((t) => { result[t.id] = 1 })
    }

    setMultiCounts(result)
  }

  // Пересчёт при изменении длительности или задач
  useEffect(() => {
    if (hasMultiTasks && selectedTasks.length > 0 && !editBlock) {
      recalcDistribution()
    }
  }, [hasMultiTasks, selectedTasks.length, durationMin, maxDurationMin, durationType])

  // Заполнить при редактировании
  useEffect(() => {
    if (editBlock) {
      setTaskIds(editBlock.task_ids || [])
      setBlockName(editBlock.block_name || '')
      setStartTime(editBlock.start_time)
      setBlockDay(editBlock.day)
      setDurationType(editBlock.duration_type)
      setDurationMin(editBlock.duration_min || 30)
      setMinDurationMin(editBlock.min_duration_min || 15)
      setMaxDurationMin(editBlock.max_duration_min || 60)
      // Восстановить multiCounts из дубликатов в task_ids
      const counts: Record<number, number> = {}
      for (const id of editBlock.task_ids || []) {
        counts[id] = (counts[id] || 0) + 1
      }
      setMultiCounts(counts)
    } else if (preselectedTaskIds.length > 0) {
      const task = taskMap[preselectedTaskIds[0]]
      if (task?.estimated_time_min) {
        setDurationMin(task.estimated_time_min)
      }
    }
  }, [editBlock])

  // Сохранить
  const handleSave = async () => {
    setSaving(true)
    try {
      // Построить финальный task_ids с дубликатами для мульти-задач
      const finalTaskIds: number[] = []
      const uniqueIds = [...new Set(taskIds)]
      for (const tid of uniqueIds) {
        const t = taskMap[tid]
        const count = (t?.allow_multi_per_block && multiCounts[tid] > 1) ? multiCounts[tid] : 1
        for (let i = 0; i < count; i++) {
          finalTaskIds.push(tid)
        }
      }

      const data: any = {
        task_ids: finalTaskIds,
        block_name: blockName || null,
        day: blockDay,
        start_time: startTime,
        duration_type: durationType,
      }

      if (durationType === 'fixed') {
        data.duration_min = durationMin || 30
      } else if (durationType === 'range') {
        data.min_duration_min = minDurationMin || 15
        data.max_duration_min = maxDurationMin || 60
      } else {
        data.max_duration_min = maxDurationMin || null
      }

      if (editBlock) {
        await api.updateBlock(editBlock.id, data)
      } else {
        await api.createBlock(data)
      }
      onSaved()
    } catch (e: any) {
      alert(e.message || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  // Выбор задачи
  const toggleTask = (taskId: number) => {
    setTaskIds((prev) => {
      if (prev.includes(taskId)) {
        setMultiCounts((mc) => {
          const next = { ...mc }
          delete next[taskId]
          return next
        })
        return prev.filter((id) => id !== taskId)
      }
      return [...prev, taskId]
    })
  }

  // Превью распределения
  const distributionPreview = useMemo(() => {
    if (!hasMultiTasks) return null
    const uniqueIds = [...new Set(taskIds)]
    const parts: string[] = []
    for (const tid of uniqueIds) {
      const t = taskMap[tid]
      if (!t) continue
      const count = (t.allow_multi_per_block && multiCounts[tid] > 1) ? multiCounts[tid] : 1
      parts.push(count > 1 ? `${t.name} x${count}` : t.name)
    }
    return parts.join(', ')
  }, [taskIds, multiCounts, hasMultiTasks, taskMap])

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dialog" onMouseDown={(e) => e.stopPropagation()} style={{ maxHeight: '85vh', overflowY: 'auto' }}>
        <h3>{editBlock ? 'Редактировать блок' : 'Новый блок'}</h3>

        <div className="block-form">
          <label className="label">Название блока (опционально)</label>
          <input
            className="input"
            value={blockName}
            onChange={(e) => setBlockName(e.target.value)}
            placeholder="Если не указано — название задачи"
          />

          <label className="label">Задачи</label>
          {/* Сортировка + группировка */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 4, alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 2, flex: 1 }}>
              {TASK_SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`backlog-sort-btn${taskSortField === opt.value ? ' active' : ''}`}
                  onClick={() => setTaskSortField(opt.value)}
                  title={opt.label}
                  style={{ flex: 1, padding: '3px 0', fontSize: 11 }}
                >
                  {opt.icon}
                </button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 2, background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', padding: 2 }}>
              {([['type', '🔁'], ['category', '📁'], ['epic', '📦']] as const).map(([mode, icon]) => (
                <button
                  key={mode}
                  type="button"
                  style={{
                    padding: '2px 6px', fontSize: 11, border: 'none', borderRadius: 4, cursor: 'pointer',
                    background: groupMode === mode ? 'var(--bg-card)' : 'transparent',
                    opacity: groupMode === mode ? 1 : 0.5,
                  }}
                  onClick={() => setGroupMode(mode)}
                  title={mode === 'type' ? 'По типу' : mode === 'category' ? 'По категории' : 'По группе'}
                >
                  {icon}
                </button>
              ))}
            </div>
          </div>
          <div style={{ maxHeight: 200, overflowY: 'auto', background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', padding: 4 }}>
            {(() => {
              // Определяем группы в зависимости от режима
              const groups: { key: string; label: string; tasks: Task[] }[] =
                groupMode === 'type'
                  ? [
                      ...(recurringTaskList.length > 0 ? [{ key: 'recurring', label: '🔁 Регулярные', tasks: recurringTaskList }] : []),
                      ...(onetimeTaskList.length > 0 ? [{ key: 'onetime', label: '📌 Разовые', tasks: onetimeTaskList }] : []),
                    ]
                  : groupMode === 'category'
                    ? tasksByCategory.map((g) => ({
                        key: `cat-${g.catId}`,
                        label: `${g.cat?.emoji || '📁'} ${g.cat?.name || 'Без категории'}`,
                        tasks: g.tasks,
                      }))
                    : tasksByEpic.map((g) => ({
                        key: `epic-${g.epic?.id || 'none'}`,
                        label: g.label,
                        tasks: g.tasks,
                      }))

              return groups.map((group) => {
                const isOpen = !closedSections.has(group.key)
                const allSelected = group.tasks.length > 0 && group.tasks.every((t) => taskIds.includes(t.id))
                const someSelected = group.tasks.some((t) => taskIds.includes(t.id))
                return (
                  <div key={group.key}>
                    <div
                      style={{
                        display: 'flex', alignItems: 'center', gap: 4, padding: '3px 6px',
                        fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)',
                        cursor: 'pointer', userSelect: 'none', borderBottom: '1px solid var(--border)',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={allSelected}
                        ref={(el) => { if (el) el.indeterminate = someSelected && !allSelected }}
                        onChange={() => toggleGroupTasks(group.tasks)}
                        onClick={(e) => e.stopPropagation()}
                        style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
                      />
                      <span style={{ width: 12 }} onClick={() => toggleTaskSection(group.key)}>{isOpen ? '▾' : '▸'}</span>
                      <span style={{ flex: 1 }} onClick={() => toggleTaskSection(group.key)}>{group.label}</span>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', background: 'var(--bg-card)', padding: '0 5px', borderRadius: 8 }}>
                        {group.tasks.length}
                      </span>
                    </div>
                    {isOpen && group.tasks.map((task) => {
                      const cat = catMap[task.category_id]
                      return (
                        <label key={task.id} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 6px 4px 28px', fontSize: 13, cursor: 'pointer' }}>
                          <input type="checkbox" checked={taskIds.includes(task.id)} onChange={() => toggleTask(task.id)} style={{ accentColor: 'var(--accent)' }} />
                          <span>{cat?.emoji || '📋'}</span>
                          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{task.name}</span>
                          {task.priority === 'high' && <span style={{ fontSize: 8 }}>🔴</span>}
                          {task.priority === 'low' && <span style={{ fontSize: 8 }}>🟢</span>}
                          {task.allow_multi_per_block && <span style={{ fontSize: 10, color: 'var(--accent)' }}>🔄</span>}
                          {task.estimated_time_min && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>~{task.estimated_time_min}м</span>}
                        </label>
                      )
                    })}
                  </div>
                )
              })
            })()}
            {nonEpicTasks.length === 0 && (
              <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 8 }}>
                Нет задач. Создайте во вкладке «Задачи».
              </div>
            )}
          </div>

          {/* Предупреждения */}
          {deviceTypeWarning && (
            <div style={{ fontSize: 12, color: 'var(--warning)', marginTop: 4 }}>
              ⚠️ {deviceTypeWarning}
            </div>
          )}
          {preferredTimeWarnings.length > 0 && (
            <div style={{ fontSize: 12, color: 'var(--warning)', marginTop: 4 }}>
              ⚠️ Не совпадает preferred_time:
              {preferredTimeWarnings.map((w, i) => <div key={i} style={{ marginLeft: 16 }}>{w}</div>)}
            </div>
          )}

          {/* Мульти-задачи: количество повторов */}
          {hasMultiTasks && selectedTasks.length > 0 && (() => {
            const effectiveDur = durationType === 'fixed' ? (durationMin || 30) : (maxDurationMin || durationMin || 30)
            const totalEstimated = selectedTasks.reduce((s, t) => s + (t.estimated_time_min || 5), 0)
            const canDistributeMore = typeof effectiveDur === 'number' && effectiveDur > totalEstimated
            return (
              <div style={{ marginTop: 8, padding: 8, background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <label className="label" style={{ fontSize: 12, margin: 0 }}>🔄 Повторы мульти-задач</label>
                  {canDistributeMore && (
                    <button className="btn btn-sm btn-secondary" onClick={recalcDistribution} type="button" style={{ fontSize: 11, padding: '2px 8px' }}>
                      🎲 Перемешать
                    </button>
                  )}
                </div>
                {selectedTasks.filter((t) => t.allow_multi_per_block).map((task) => (
                  <div key={task.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                    <span style={{ flex: 1, fontSize: 12 }}>{task.name}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>x</span>
                    <input
                      className="input"
                      type="number"
                      min={1}
                      max={99}
                      value={multiCounts[task.id] || 1}
                      onChange={(e) => {
                        const val = Math.max(1, parseInt(e.target.value) || 1)
                        setMultiCounts((prev) => ({ ...prev, [task.id]: val }))
                      }}
                      style={{ width: 70, textAlign: 'center', fontSize: 13 }}
                    />
                  </div>
                ))}
                {!canDistributeMore && (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                    💡 Увеличьте длительность блока чтобы добавить больше повторов
                  </div>
                )}
                {distributionPreview && canDistributeMore && (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
                    Превью: {distributionPreview}
                  </div>
                )}
              </div>
            )
          })()}

          <div className="block-form-row">
            <div>
              <label className="label">Дата</label>
              <input
                className="input"
                type="date"
                value={blockDay}
                onChange={(e) => setBlockDay(e.target.value)}
              />
            </div>
            <div>
              <label className="label">Время</label>
              <input
                className="input"
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                step={1800}
              />
            </div>
          </div>

          <label className="label">Тип длительности</label>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              className={`btn btn-sm ${durationType === 'fixed' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setDurationType('fixed')}
            >
              Фиксированный
            </button>
            <button
              className={`btn btn-sm ${durationType === 'open' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setDurationType('open')}
            >
              🔓 Открытый
            </button>
            <button
              className={`btn btn-sm ${durationType === 'range' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setDurationType('range')}
            >
              ↔️ Диапазон
            </button>
          </div>

          {/* Редактируемые свойства задач в блоке: спам, повторы, pomodoro */}
          {selectedTasks.length > 0 && (
            <div style={{ marginTop: 8, padding: 8, background: 'var(--bg-input)', borderRadius: 'var(--radius-sm)', fontSize: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--text-muted)' }}>⚙️ Настройки задач</div>
              {selectedTasks.map((task) => {
                const cat = catMap[task.category_id]
                const dayNames = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
                return (
                  <div key={task.id} style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                    <div style={{ fontWeight: 500, marginBottom: 4 }}>{cat?.emoji || '📋'} {task.name}
                      {task.priority === 'high' && ' 🔴'}
                      {task.priority === 'low' && ' 🟢'}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={task.spam_enabled}
                          onChange={async () => {
                            const newVal = !task.spam_enabled
                            setLocalTasks(prev => prev.map(t => t.id === task.id ? { ...t, spam_enabled: newVal } : t))
                            try { await api.updateTask(task.id, { spam_enabled: newVal }) } catch {}
                          }}
                          style={{ accentColor: 'var(--accent)' }}
                        />
                        📢 Спам
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={task.use_pomodoro}
                          onChange={async () => {
                            const newVal = !task.use_pomodoro
                            setLocalTasks(prev => prev.map(t => t.id === task.id ? { ...t, use_pomodoro: newVal } : t))
                            try { await api.updateTask(task.id, { use_pomodoro: newVal }) } catch {}
                          }}
                          style={{ accentColor: 'var(--accent)' }}
                        />
                        🍅 Pomodoro
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={task.is_recurring}
                          onChange={async () => {
                            const newVal = !task.is_recurring
                            const newDays = newVal ? [0, 1, 2, 3, 4] : []
                            setLocalTasks(prev => prev.map(t => t.id === task.id ? { ...t, is_recurring: newVal, recur_days: newDays } : t))
                            try { await api.updateTask(task.id, { is_recurring: newVal, recur_days: newDays }) } catch {}
                          }}
                          style={{ accentColor: 'var(--accent)' }}
                        />
                        🔁 Повтор
                      </label>
                    </div>
                    {task.is_recurring && (
                      <div style={{ display: 'flex', gap: 2, marginTop: 4 }}>
                        {dayNames.map((name, i) => {
                          const active = task.recur_days?.includes(i)
                          return (
                            <button
                              key={i}
                              type="button"
                              onClick={async () => {
                                const days = task.recur_days || []
                                const newDays = active
                                  ? days.filter((d: number) => d !== i)
                                  : [...days, i].sort()
                                setLocalTasks(prev => prev.map(t => t.id === task.id ? { ...t, recur_days: newDays } : t))
                                try { await api.updateTask(task.id, { recur_days: newDays }) } catch {}
                              }}
                              style={{
                                padding: '2px 6px',
                                fontSize: 10,
                                borderRadius: 4,
                                border: 'none',
                                cursor: 'pointer',
                                background: active ? 'var(--accent)' : 'var(--bg-card)',
                                color: active ? '#fff' : 'var(--text-muted)',
                              }}
                            >
                              {name}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {durationType === 'fixed' && (
            <>
              <label className="label">Длительность (мин)</label>
              <input
                className="input"
                type="number"
                min={5}
                step={5}
                value={durationMin}
                onChange={(e) => setDurationMin(e.target.value === '' ? '' : parseInt(e.target.value) || 0)}
                onBlur={() => { if (durationMin === '' || durationMin < 1) setDurationMin(5) }}
                style={{ maxWidth: 120 }}
              />
            </>
          )}

          {durationType === 'open' && (
            <>
              <label className="label">Макс. длительность (мин, опционально)</label>
              <input
                className="input"
                type="number"
                min={5}
                step={5}
                value={maxDurationMin}
                onChange={(e) => setMaxDurationMin(e.target.value === '' ? '' : parseInt(e.target.value) || 0)}
                onBlur={() => { if (maxDurationMin === '' || maxDurationMin < 1) setMaxDurationMin(30) }}
                style={{ maxWidth: 120 }}
              />
              <span className="hint">Через это время бот напомнит: «Не забыл завершить?»</span>
            </>
          )}

          {durationType === 'range' && (
            <div className="block-form-row">
              <div>
                <label className="label">Минимум (мин)</label>
                <input
                  className="input"
                  type="number"
                  min={5}
                  step={5}
                  value={minDurationMin}
                  onChange={(e) => setMinDurationMin(e.target.value === '' ? '' : parseInt(e.target.value) || 0)}
                  onBlur={() => { if (minDurationMin === '' || minDurationMin < 1) setMinDurationMin(5) }}
                />
              </div>
              <div>
                <label className="label">Максимум (мин)</label>
                <input
                  className="input"
                  type="number"
                  min={5}
                  step={5}
                  value={maxDurationMin}
                  onChange={(e) => setMaxDurationMin(e.target.value === '' ? '' : parseInt(e.target.value) || 0)}
                  onBlur={() => { if (maxDurationMin === '' || maxDurationMin < 1) setMaxDurationMin(30) }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving || taskIds.length === 0}
          >
            {saving ? '...' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}
